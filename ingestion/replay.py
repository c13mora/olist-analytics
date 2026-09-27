"""Replay the static Olist CSVs as if they were a live source system.

Usage:
    uv run python ingestion/replay.py --reset   # wipe raw schema, load reference data, restart at day 0
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import dlt
import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
DUCKDB_PATH = REPO_ROOT / "data" / "olist.duckdb"
STATE_PATH = Path(__file__).resolve().parent / "state.json"

PIPELINE_NAME = "olist_replay"
DATASET_NAME = "raw"

# Day 0 of the simulation. 2016 has only ~330 orders spread over three months,
# so the first replayed day (2017-01-01) picks them up as an initial backfill
# and the daily cadence starts where order volume becomes steady.
START_DATE = date(2016, 12, 31)

# Reference data: loaded once at reset, static for the whole simulation.
# Customers are deliberately not here: Olist issues a new customer_id for every
# order, so customer rows behave like order attributes and arrive with orders.
REFERENCE_TABLES = {
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "product_category_name_translation": "product_category_name_translation.csv",
    "geolocation": "olist_geolocation_dataset.csv",
}

BATCH_SIZE = 50_000


def read_csv(file_name: str) -> Iterator[list[dict[str, str | None]]]:
    """Yield the rows of a raw CSV as dicts, in batches.

    Every column is read as text. Raw is a faithful landing zone and casting
    belongs in dbt staging; type inference here would also silently drop the
    leading zeros of zip code prefixes such as "01037".
    """
    relation = duckdb.read_csv(str(RAW_DIR / file_name), header=True, all_varchar=True)
    columns = relation.columns
    while batch := relation.fetchmany(BATCH_SIZE):
        yield [dict(zip(columns, row)) for row in batch]


def make_pipeline() -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination=dlt.destinations.duckdb(str(DUCKDB_PATH)),
        dataset_name=DATASET_NAME,
    )


def write_state(simulated_date: date) -> None:
    STATE_PATH.write_text(json.dumps({"simulated_date": simulated_date.isoformat()}, indent=2) + "\n")


def reset() -> None:
    """Wipe the raw schema, reload reference data and restart the simulation at day 0."""
    missing = [f for f in REFERENCE_TABLES.values() if not (RAW_DIR / f).exists()]
    if missing:
        sys.exit(f"Missing CSVs in {RAW_DIR}: {', '.join(missing)}. See README step 2.")

    # dlt keeps pipeline state both in the destination and in a local working
    # folder. Drop both, otherwise dlt would assume the old tables still exist.
    with duckdb.connect(str(DUCKDB_PATH)) as con:
        con.execute(f"drop schema if exists {DATASET_NAME} cascade")
    make_pipeline().drop()

    resources = [
        dlt.resource(read_csv(file_name), name=table_name, write_disposition="replace")
        for table_name, file_name in REFERENCE_TABLES.items()
    ]
    pipeline = make_pipeline()
    load_info = pipeline.run(resources)
    load_info.raise_on_failed_jobs()

    write_state(START_DATE)

    row_counts = pipeline.last_trace.last_normalize_info.row_counts
    print(f"Reset complete. Simulated date: {START_DATE.isoformat()}")
    for table_name in REFERENCE_TABLES:
        print(f"  {DATASET_NAME}.{table_name}: {row_counts.get(table_name, 0):,} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the Olist dataset in daily batches.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--reset",
        action="store_true",
        help="wipe the raw schema, load reference data and restart at day 0",
    )
    args = parser.parse_args()

    if args.reset:
        reset()


if __name__ == "__main__":
    main()
