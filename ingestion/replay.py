"""Replay the static Olist CSVs as if they were a live source system.

The raw schema always reflects the source system as of the end of the
simulated date stored in the destination's state file.

Usage:
    uv run python ingestion/replay.py --reset    # wipe raw (and the snapshot and incremental fact), load reference data and orders up to day 0
    uv run python ingestion/replay.py --days N   # advance the simulation by N days

Both load into the local DuckDB file by default. Add `--destination snowflake`
to load the same raw tables into Snowflake (see snowflake/setup.sql and the
README); each destination keeps its own simulated date.
"""

from __future__ import annotations

import argparse
import json
import os
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

DESTINATIONS = ("duckdb", "snowflake")
PIPELINE_NAME = "olist_replay"
DATASET_NAME = "raw"

# dbt tables that build up history across runs instead of being rebuilt each
# time: the order status snapshot and the incremental order items fact. After
# a reset they would hold rows "from the future" of the restarted simulation,
# so reset drops them and dbt rebuilds them from scratch on its next run. The
# schema names follow dbt's default naming on the dev target (main_<schema>).
DBT_ACCUMULATING_TABLES = ["main_snapshots.snap_orders", "main_marts.fct_order_items"]

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


def in_window(expression: str) -> str:
    return f"({expression} >= $window_start and {expression} < $window_end)"


# Each query returns the rows that are new or changed in the source system
# during the window [$window_start, $window_end).
PLACED_IN_WINDOW = in_window("o.order_purchase_timestamp::timestamp")

TRANSACTIONAL_QUERIES = {
    # The CSV only holds each order's final status, so the replay rebuilds its
    # history from the milestone timestamps: an order is (re)loaded whenever a
    # milestone falls in the window, showing its status as of the window end.
    # Milestones that have not happened yet are hidden so nothing leaks from
    # the future. The estimated delivery date is promised at checkout, so it
    # is always visible.
    "orders": f"""
        with orders_typed as (
            select
                *,
                order_status as final_status,
                order_purchase_timestamp::timestamp as purchased_at,
                order_approved_at::timestamp as approved_at,
                order_delivered_carrier_date::timestamp as shipped_at,
                order_delivered_customer_date::timestamp as delivered_at,
                -- Canceled and unavailable orders carry no timestamp for when
                -- that happened. They take their final status at their last
                -- known milestone: the replay never invents timestamps.
                greatest(
                    order_purchase_timestamp::timestamp,
                    order_approved_at::timestamp,
                    order_delivered_carrier_date::timestamp,
                    order_delivered_customer_date::timestamp
                ) as last_milestone_at
            from orders
        )

        select
            order_id,
            customer_id,
            -- Status is the furthest milestone reached, checked from last to
            -- first. Source timestamps are sometimes out of order (e.g. 1,359
            -- orders handed to the carrier before approval), and this way the
            -- status still never moves backwards.
            case
                when final_status in ('canceled', 'unavailable')
                    and last_milestone_at < $window_end then final_status
                when delivered_at < $window_end then 'delivered'
                when shipped_at < $window_end then 'shipped'
                -- Orders that end as 'invoiced' or 'processing' were approved
                -- but never shipped: they hold that status from approval on.
                when final_status in ('invoiced', 'processing')
                    and approved_at < $window_end then final_status
                when approved_at < $window_end then 'approved'
                else 'created'
            end as order_status,
            order_purchase_timestamp,
            case when approved_at < $window_end then order_approved_at end as order_approved_at,
            case when shipped_at < $window_end then order_delivered_carrier_date end as order_delivered_carrier_date,
            case when delivered_at < $window_end then order_delivered_customer_date end as order_delivered_customer_date,
            order_estimated_delivery_date
        from orders_typed
        where
            purchased_at < $window_end
            and (
                {in_window("purchased_at")}
                or {in_window("approved_at")}
                or {in_window("shipped_at")}
                or {in_window("delivered_at")}
            )
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
    "order_reviews": f"""
        select r.*
        from order_reviews as r
        inner join orders as o on r.order_id = o.order_id
        where {in_window("greatest(r.review_answer_timestamp::timestamp, o.order_purchase_timestamp::timestamp)")}
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


def state_path(destination: str = "duckdb") -> Path:
    """Each destination keeps its own simulated date."""
    suffix = "" if destination == "duckdb" else f"_{destination}"
    return Path(__file__).resolve().parent / f"state{suffix}.json"


def snowflake_credentials() -> dict[str, str]:
    """Key-pair credentials from the same environment variables dbt uses.

    dlt signs in with the LOADER role, which can only create and write the
    raw schemas (see snowflake/setup.sql).
    """
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_PRIVATE_KEY_PATH"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        sys.exit(f"Set {', '.join(missing)} to load into Snowflake. See the README section on Snowflake.")
    return {
        "host": os.environ["SNOWFLAKE_ACCOUNT"],
        "username": os.environ.get("SNOWFLAKE_USER", "OLIST_SERVICE"),
        "private_key_path": os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        "database": os.environ.get("SNOWFLAKE_DATABASE", "OLIST"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "OLIST_WH"),
        "role": os.environ.get("SNOWFLAKE_LOADER_ROLE", "LOADER"),
    }


def make_pipeline(destination: str = "duckdb") -> dlt.Pipeline:
    if destination == "snowflake":
        # dlt writes Snowflake identifiers in upper case (ORDER_ID), which is
        # what dbt's unquoted lower-case names resolve to.
        target = dlt.destinations.snowflake(credentials=snowflake_credentials())
        pipeline_name = f"{PIPELINE_NAME}_snowflake"
    else:
        target = dlt.destinations.duckdb(str(DUCKDB_PATH))
        pipeline_name = PIPELINE_NAME
    return dlt.pipeline(pipeline_name=pipeline_name, destination=target, dataset_name=DATASET_NAME)


def run_pipeline(resources: list[Any], table_names: list[str], destination: str = "duckdb") -> dict[str, int]:
    """Load the resources and return the number of rows loaded per table."""
    pipeline = make_pipeline(destination)
    load_info = pipeline.run(resources)
    load_info.raise_on_failed_jobs()

    normalized = pipeline.last_trace.last_normalize_info.row_counts
    row_counts = {table_name: normalized.get(table_name, 0) for table_name in table_names}
    for table_name, rows in row_counts.items():
        print(f"  {DATASET_NAME}.{table_name}: {rows:,} rows")
    return row_counts


def read_state(destination: str = "duckdb") -> date:
    path = state_path(destination)
    if not path.exists():
        sys.exit(f"No simulation state found for {destination}. Run `replay.py --reset` first.")
    return date.fromisoformat(json.loads(path.read_text())["simulated_date"])


def write_state(simulated_date: date, destination: str = "duckdb") -> None:
    state_path(destination).write_text(json.dumps({"simulated_date": simulated_date.isoformat()}, indent=2) + "\n")


def drop_raw(destination: str) -> None:
    """Drop the raw data and dlt's own record of it, in the destination and locally.

    dlt keeps pipeline state both in the destination and in a local working
    folder. Drop both, otherwise dlt would assume the old tables still exist.
    """
    if destination == "snowflake":
        # RAW_STAGING is where dlt stages merges. dbt's tables belong to the
        # TRANSFORMER role, which LOADER cannot drop (see the note in reset).
        with make_pipeline(destination).sql_client() as client:
            client.execute_sql(f"drop schema if exists {DATASET_NAME} cascade")
            client.execute_sql(f"drop schema if exists {DATASET_NAME}_staging cascade")
    else:
        with duckdb.connect(str(DUCKDB_PATH)) as con:
            con.execute(f"drop schema if exists {DATASET_NAME} cascade")
            for table in DBT_ACCUMULATING_TABLES:
                con.execute(f"drop table if exists {table}")
    make_pipeline(destination).drop()


def reset(destination: str = "duckdb") -> None:
    """Wipe raw and dbt's accumulating tables, reload reference data and backfill orders up to day 0."""
    missing = [f for f in SOURCE_FILES.values() if not (RAW_DIR / f).exists()]
    if missing:
        sys.exit(f"Missing CSVs in {RAW_DIR}: {', '.join(missing)}. See README step 2.")

    drop_raw(destination)

    con = source_connection()
    resources = [table_resource(con, table_name, f"select * from {table_name}") for table_name in REFERENCE_TABLES]
    resources += transactional_resources(con, datetime.min, end_of(START_DATE))

    print(f"Resetting simulation to {START_DATE.isoformat()} ({destination})")
    run_pipeline(resources, REFERENCE_TABLES + list(TRANSACTIONAL_QUERIES), destination)
    write_state(START_DATE, destination)
    if destination == "snowflake":
        print(
            "Note: on Snowflake, the dbt snapshot and incremental fact belong to the TRANSFORMER role and\n"
            "were not dropped. If they exist from an earlier run, drop the DBT_DEV_SNAPSHOTS schema and\n"
            "run dbt with --full-refresh, so no history from the previous simulation survives."
        )


def advance(days: int, destination: str = "duckdb") -> dict[str, int]:
    """Load everything that happened in the source system over the next N days."""
    current_date = read_state(destination)
    new_date = current_date + timedelta(days=days)

    con = source_connection()
    resources = transactional_resources(con, end_of(current_date), end_of(new_date))

    print(f"Advancing simulation {current_date.isoformat()} -> {new_date.isoformat()} ({destination})")
    row_counts = run_pipeline(resources, list(TRANSACTIONAL_QUERIES), destination)
    # State is saved only after a successful load. If the load fails, the next
    # run replays the same window, which the merge keys make safe.
    write_state(new_date, destination)
    return row_counts


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
        help="wipe raw and the dbt snapshot and incremental fact, load reference data and orders up to day 0",
    )
    action.add_argument("--days", type=positive_int, metavar="N", help="advance the simulation by N days")
    parser.add_argument(
        "--destination",
        choices=DESTINATIONS,
        default="duckdb",
        help="where to load the raw tables (default: the local DuckDB file)",
    )
    args = parser.parse_args()

    if args.reset:
        reset(args.destination)
    else:
        advance(args.days, args.destination)


if __name__ == "__main__":
    main()
