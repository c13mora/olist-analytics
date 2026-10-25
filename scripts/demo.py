"""Demo: replay day by day and watch the incremental fact and the snapshot.

For each simulated day it loads the day with the replay, runs every model
(fct_order_items incrementally) and the snap_orders snapshot, and reports
what changed. At the end it runs every test, then shows one order's status
history and how long orders stay in each status. See docs/demo.md for a
walkthrough of the output.

Usage, from the repo root:
    uv run python scripts/demo.py --reset --days 7   # start from a clean simulation
    uv run python scripts/demo.py --days 3           # continue from the current date

Runs against the local DuckDB file (the dev target).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = REPO_ROOT / "dbt"
DUCKDB_PATH = REPO_ROOT / "data" / "olist.duckdb"
STATE_PATH = REPO_ROOT / "ingestion" / "state.json"

FACT = "main_marts.fct_order_items"
SNAPSHOT = "main_snapshots.snap_orders"

# With --reset, the simulation first jumps to 2017-01-31 in one load (2016 plus
# January 2017), so the day-by-day part starts with steady order volume.
WARM_UP_DAYS = 31


def run(command: list[str], cwd: Path = REPO_ROOT) -> str:
    env = {**os.environ, "DBT_PROFILES_DIR": str(DBT_DIR)}
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"Command failed: {' '.join(command)}\n{result.stdout[-3000:]}{result.stderr[-3000:]}")
    return result.stdout


def replay(*args: str) -> str:
    return run(["uv", "run", "python", "ingestion/replay.py", *args])


def dbt(*args: str) -> str:
    return run(["uv", "run", "dbt", *args], cwd=DBT_DIR)


def query(sql: str) -> list[tuple]:
    with duckdb.connect(str(DUCKDB_PATH), read_only=True) as con:
        return con.sql(sql).fetchall()


def simulated_date() -> str:
    return json.loads(STATE_PATH.read_text())["simulated_date"]


def table_exists(name: str) -> bool:
    schema, table = name.split(".")
    return bool(query(
        f"select 1 from information_schema.tables where table_schema = '{schema}' and table_name = '{table}'"
    ))


def start_clean() -> None:
    print("Resetting the simulation (this reloads the reference data and takes a few minutes)...")
    replay("--reset")
    replay("--days", str(WARM_UP_DAYS))
    print(f"Warm-up: loaded everything up to {simulated_date()}, building and testing all models...")
    dbt("build", "-s", "olist")
    print("Initial build done: every model built, every test passed, first snapshot taken.\n")


def replay_one_day() -> tuple[str, int, int, int, int, int]:
    """Advance one day and return what the replay, the fact and the snapshot did."""
    previous_max, fact_rows_before = query(f"select max(_loaded_at), count(*) from {FACT}")[0]
    (versions_before,) = query(f"select count(*) from {SNAPSHOT}")[0]

    output = replay("--days", "1")
    day = simulated_date()
    orders_loaded = int(re.search(r"raw\.orders: ([\d,]+) rows", output).group(1).replace(",", ""))
    (new_orders,) = query(f"select count(*) from raw.orders where cast(order_purchase_timestamp as date) = '{day}'")[0]

    # A daily run: every model (fct_order_items incrementally, the other marts
    # rebuilt) plus the snapshot. Tests run once at the end, to keep each day
    # quick; skipping the other marts would leave them stale and fail tests.
    dbt("build", "-s", "olist", "--resource-type", "model", "--resource-type", "snapshot")

    processed, fact_rows = query(f"""
        select count(*) filter (where _loaded_at > timestamp '{previous_max}'), count(*)
        from {FACT}
    """)[0]
    (versions,) = query(f"select count(*) from {SNAPSHOT}")[0]
    return day, new_orders, orders_loaded - new_orders, processed, fact_rows, versions - versions_before


def show_order_history() -> None:
    order_id, versions = query(f"""
        select order_id, count(*) as versions from {SNAPSHOT}
        group by order_id order by versions desc, min(dbt_valid_from) limit 1
    """)[0]
    print(f"\nStatus history of order {order_id} ({versions} versions in snap_orders):")
    rows = query(f"""
        select order_status, dbt_valid_from, dbt_valid_to from {SNAPSHOT}
        where order_id = '{order_id}' order by dbt_valid_from
    """)
    for status, valid_from, valid_to in rows:
        until = f"{valid_to:%Y-%m-%d %H:%M}" if valid_to else "now (current version)"
        print(f"  {status:<12} from {valid_from:%Y-%m-%d %H:%M}  to {until}")


def show_status_durations() -> None:
    print("\nTime orders spent in each status (completed versions only):")
    print(f"  {'status':<12}{'versions':>10}{'median days':>14}")
    rows = query(f"""
        select
            order_status,
            count(*),
            round(median(date_diff('hour', dbt_valid_from, dbt_valid_to)) / 24.0, 1)
        from {SNAPSHOT}
        where dbt_valid_to is not null
        group by order_status
        order by case order_status
            when 'created' then 1 when 'approved' then 2 when 'invoiced' then 3
            when 'processing' then 4 when 'shipped' then 5 else 6
        end
    """)
    for status, versions, median_days in rows:
        print(f"  {status:<12}{versions:>10,}{median_days:>14}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay day by day and watch the incremental fact and the snapshot.")
    parser.add_argument("--days", type=int, default=7, help="number of days to replay one by one (default 7)")
    parser.add_argument("--reset", action="store_true", help="start from a clean simulation first")
    args = parser.parse_args()

    if args.reset:
        start_clean()
    elif not (table_exists(FACT) and table_exists(SNAPSHOT)):
        sys.exit("No fact table or snapshot yet. Run with --reset to start a clean simulation.")

    print(f"Replaying {args.days} days one at a time, starting after {simulated_date()}:\n")
    print(f"{'day':<12}{'new orders':>12}{'status updates':>16}"
          f"{'fact rows processed':>21}{'fact rows total':>17}{'snapshot versions added':>25}")
    for _ in range(args.days):
        day, new_orders, updates, processed, fact_rows, versions_added = replay_one_day()
        print(f"{day:<12}{new_orders:>12,}{updates:>16,}{processed:>21,}{fact_rows:>17,}{versions_added:>25,}")

    print("\nRunning every test on the result...")
    dbt("test", "-s", "olist")
    print("All tests pass (one expected warning: orders whose payments differ from items).")

    show_order_history()
    show_status_durations()


if __name__ == "__main__":
    main()
