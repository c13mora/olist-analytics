"""Check that replaying the same simulated day twice leaves raw unchanged.

Advances the simulation by one day, fingerprints every transactional table,
rewinds state.json and replays the same day again. The second run must leave
each table exactly as the first did: same row count, same content, and no
duplicate primary keys. Exits with code 1 otherwise.

Usage:
    uv run python ingestion/check_idempotency.py

The simulation ends one day ahead of where it started. Run it on a day with
activity (e.g. after `--reset` and `--days 400`), or the check proves little.
"""

from __future__ import annotations

import sys

import duckdb

import replay

Fingerprint = tuple[int, int, int]


def fingerprint(con: duckdb.DuckDBPyConnection, table_name: str, primary_key: list[str]) -> Fingerprint:
    """Return (row count, content checksum, duplicate primary keys) for a raw table.

    The checksum sums a hash of every row, so it ignores row order but changes
    if any value changes or a row is added twice. dlt's own columns are left
    out because they change on every load by design.
    """
    table = f"{replay.DATASET_NAME}.{table_name}"
    rows, checksum = con.sql(
        f"""
        select count(*), coalesce(sum(hash(t)::hugeint), 0)
        from (select * exclude (_dlt_load_id, _dlt_id) from {table}) as t
        """
    ).fetchone()
    (duplicate_keys,) = con.sql(f"select count(*) - count(distinct ({', '.join(primary_key)})) from {table}").fetchone()
    return rows, checksum, duplicate_keys


def fingerprint_all() -> dict[str, Fingerprint]:
    with duckdb.connect(str(replay.DUCKDB_PATH), read_only=True) as con:
        return {
            table_name: fingerprint(con, table_name, primary_key)
            for table_name, primary_key in replay.PRIMARY_KEYS.items()
        }


def main() -> None:
    start_date = replay.read_state()

    print("First run:")
    loaded = replay.advance(1)
    first = fingerprint_all()

    print("Replaying the same day:")
    replay.write_state(start_date)
    replay.advance(1)
    second = fingerprint_all()

    print(f"\n{'table':<16}{'rows':>10}  {'same content':<14}{'duplicate keys':>14}")
    failed = False
    for table_name, (rows, checksum, duplicate_keys) in second.items():
        same = (rows, checksum) == first[table_name][:2]
        failed |= not same or duplicate_keys > 0
        print(f"{table_name:<16}{rows:>10,}  {'yes' if same else 'NO':<14}{duplicate_keys:>14,}")

    if failed:
        sys.exit("\nFAILED: replaying the same day changed raw.")
    if not any(loaded.values()):
        print("\nWARNING: the replayed day had no source changes, so this check proves little.")
    print("\nPASSED: replaying the same day left raw unchanged.")


if __name__ == "__main__":
    main()
