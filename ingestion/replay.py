"""Replay the static Olist CSVs as if they were a live source system.

The raw schema always reflects the source system as of the end of the
simulated date stored in state.json.

Usage:
    uv run python ingestion/replay.py --reset    # wipe raw schema, load reference data and orders up to day 0
    uv run python ingestion/replay.py --days N   # advance the simulation by N days
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import dlt
import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
DUCKDB_PATH = REPO_ROOT / "data" / "olist.duckdb"
STATE_PATH = Path(__file__).resolve().parent / "state.json"

PIPELINE_NAME = "olist_replay"
DATASET_NAME = "raw"

# Day 0 of the simulation. 2016 has only ~330 orders spread over three months,
# so reset loads them as an initial backfill and the daily cadence starts on
# 2017-01-01, where order volume becomes steady.
START_DATE = date(2016, 12, 31)

SOURCE_FILES = {
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "product_category_name_translation": "product_category_name_translation.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
}

# Reference data: loaded once at reset, static for the whole simulation.
# Customers are deliberately not here: Olist issues a new customer_id for every
# order, so customer rows behave like order attributes and arrive with orders.
REFERENCE_TABLES = ["sellers", "products", "product_category_name_translation", "geolocation"]

# Transactional data arrives as the simulated date advances. Tables are merged
# on their primary key, so re-running a window overwrites the same rows instead
# of appending duplicates (e.g. after a crash between loading and saving state).
PRIMARY_KEYS = {
    "orders": ["order_id"],
    "customers": ["customer_id"],
    "order_items": ["order_id", "order_item_id"],
    "order_payments": ["order_id", "payment_sequential"],
    "order_reviews": ["review_id", "order_id"],
}

# Each query returns the rows that become visible in the source system during
# the window [$window_start, $window_end).
PLACED_IN_WINDOW = """
    o.order_purchase_timestamp::timestamp >= $window_start
    and o.order_purchase_timestamp::timestamp < $window_end
"""

TRANSACTIONAL_QUERIES = {
    # At purchase time an order is only 'created': approval, carrier pickup and
    # delivery have not happened yet, so those timestamps must not leak in.
    # The estimated delivery date is promised at checkout, so it is kept.
    "orders": f"""
        select
            o.order_id,
            o.customer_id,
            'created' as order_status,
            o.order_purchase_timestamp,
            null::varchar as order_approved_at,
            null::varchar as order_delivered_carrier_date,
            null::varchar as order_delivered_customer_date,
            o.order_estimated_delivery_date
        from orders as o
        where {PLACED_IN_WINDOW}
    """,
    "customers": f"""
        select c.*
        from customers as c
        inner join orders as o on c.customer_id = o.customer_id
        where {PLACED_IN_WINDOW}
    """,
    "order_items": f"""
        select i.*
        from order_items as i
        inner join orders as o on i.order_id = o.order_id
        where {PLACED_IN_WINDOW}
    """,
    "order_payments": f"""
        select p.*
        from order_payments as p
        inner join orders as o on p.order_id = o.order_id
        where {PLACED_IN_WINDOW}
    """,
    # A review exists once the customer answers the survey. 63 reviews are
    # answered before their order's purchase time (a source data issue, left
    # for staging to flag); they arrive with the order instead, so a review
    # never shows up before the order it belongs to.
    "order_reviews": """
        select r.*
        from order_reviews as r
        inner join orders as o on r.order_id = o.order_id
        where greatest(
                r.review_answer_timestamp::timestamp,
                o.order_purchase_timestamp::timestamp
            ) >= $window_start
            and greatest(
                r.review_answer_timestamp::timestamp,
                o.order_purchase_timestamp::timestamp
            ) < $window_end
    """,
}

BATCH_SIZE = 50_000


def source_connection() -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB with one view per raw CSV.

    Every column is read as text. Raw is a faithful landing zone and casting
    belongs in dbt staging; type inference here would also silently drop the
    leading zeros of zip code prefixes such as "01037".
    """
    con = duckdb.connect()
    for view_name, file_name in SOURCE_FILES.items():
        path = (RAW_DIR / file_name).as_posix()
        con.execute(
            f"create view {view_name} as "
            f"select * from read_csv('{path}', header = true, all_varchar = true)"
        )
    return con


def fetch_batches(
    con: duckdb.DuckDBPyConnection, query: str, params: dict[str, Any] | None
) -> Iterator[list[dict[str, str | None]]]:
    # Each resource gets its own cursor: dlt may interleave resources, and a
    # new query on a shared connection would invalidate a pending result.
    relation = con.cursor().sql(query, params=params)
    columns = relation.columns
    while batch := relation.fetchmany(BATCH_SIZE):
        yield [dict(zip(columns, row)) for row in batch]


def table_resource(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    query: str,
    params: dict[str, Any] | None = None,
    primary_key: list[str] | None = None,
) -> Any:
    columns = con.sql(query, params=params).columns
    return dlt.resource(
        fetch_batches(con, query, params),
        name=table_name,
        write_disposition="merge" if primary_key else "replace",
        primary_key=primary_key,
        # Declare every column as text up front. dlt otherwise skips columns
        # that are null in every row of a load, like order_approved_at at
        # purchase time.
        columns={column: {"data_type": "text"} for column in columns},
    )


def transactional_resources(
    con: duckdb.DuckDBPyConnection, window_start: datetime, window_end: datetime
) -> list[Any]:
    params = {"window_start": window_start, "window_end": window_end}
    return [
        table_resource(con, table_name, query, params, PRIMARY_KEYS[table_name])
        for table_name, query in TRANSACTIONAL_QUERIES.items()
    ]


def end_of(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min)


def make_pipeline() -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination=dlt.destinations.duckdb(str(DUCKDB_PATH)),
        dataset_name=DATASET_NAME,
    )


def run_pipeline(resources: list[Any], table_names: list[str]) -> None:
    pipeline = make_pipeline()
    load_info = pipeline.run(resources)
    load_info.raise_on_failed_jobs()

    row_counts = pipeline.last_trace.last_normalize_info.row_counts
    for table_name in table_names:
        print(f"  {DATASET_NAME}.{table_name}: {row_counts.get(table_name, 0):,} rows")


def read_state() -> date:
    if not STATE_PATH.exists():
        sys.exit("No simulation state found. Run `replay.py --reset` first.")
    return date.fromisoformat(json.loads(STATE_PATH.read_text())["simulated_date"])


def write_state(simulated_date: date) -> None:
    STATE_PATH.write_text(json.dumps({"simulated_date": simulated_date.isoformat()}, indent=2) + "\n")


def reset() -> None:
    """Wipe the raw schema, reload reference data and backfill orders up to day 0."""
    missing = [f for f in SOURCE_FILES.values() if not (RAW_DIR / f).exists()]
    if missing:
        sys.exit(f"Missing CSVs in {RAW_DIR}: {', '.join(missing)}. See README step 2.")

    # dlt keeps pipeline state both in the destination and in a local working
    # folder. Drop both, otherwise dlt would assume the old tables still exist.
    with duckdb.connect(str(DUCKDB_PATH)) as con:
        con.execute(f"drop schema if exists {DATASET_NAME} cascade")
    make_pipeline().drop()

    con = source_connection()
    resources = [table_resource(con, table_name, f"select * from {table_name}") for table_name in REFERENCE_TABLES]
    resources += transactional_resources(con, datetime.min, end_of(START_DATE))

    print(f"Resetting simulation to {START_DATE.isoformat()}")
    run_pipeline(resources, REFERENCE_TABLES + list(TRANSACTIONAL_QUERIES))
    write_state(START_DATE)


def advance(days: int) -> None:
    """Load everything that happened in the source system over the next N days."""
    current_date = read_state()
    new_date = current_date + timedelta(days=days)

    con = source_connection()
    resources = transactional_resources(con, end_of(current_date), end_of(new_date))

    print(f"Advancing simulation {current_date.isoformat()} -> {new_date.isoformat()}")
    run_pipeline(resources, list(TRANSACTIONAL_QUERIES))
    # State is saved only after a successful load. If the load fails, the next
    # run replays the same window, which the merge keys make safe.
    write_state(new_date)


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the Olist dataset in daily batches.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--reset",
        action="store_true",
        help="wipe the raw schema, load reference data and orders up to day 0",
    )
    action.add_argument("--days", type=positive_int, metavar="N", help="advance the simulation by N days")
    args = parser.parse_args()

    if args.reset:
        reset()
    else:
        advance(args.days)


if __name__ == "__main__":
    main()
