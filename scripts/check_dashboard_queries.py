"""Run every SQL query of every dashboard page, the way the browser does.

Evidence's `build:strict` does not fail on broken SQL: a query that errors
only prints "Error in Query!" and the build still succeeds. This script runs
each page's queries in order against Evidence's own data cache (written by
`npm run sources`), so column types match the browser (dates become
timestamps there), and exits with code 1 if any query fails or returns no
rows. Later queries reference earlier ones with ${name}, as in Evidence;
filter inputs are replaced by their "all" value ('%').

Usage, from the repo root (after `npm run sources` in dashboard/):
    uv run python scripts/check_dashboard_queries.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = REPO_ROOT / "dashboard" / "pages"
CACHE_DIR = REPO_ROOT / "dashboard" / ".evidence" / "template" / "static" / "data"


def source_views(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Expose each cached source table as a view named <source>_<table>."""
    names = []
    for path in sorted(CACHE_DIR.glob("*/*/**/*.parquet")):
        source, table = path.relative_to(CACHE_DIR).parts[:2]
        name = f"{source}_{table}"
        con.execute(f"create or replace view {name} as select * from read_parquet('{path.as_posix()}')")
        names.append(f"{source}.{table}")
    return names


def check_page(con: duckdb.DuckDBPyConnection, page: Path) -> list[str]:
    """Run the page's queries in order; return a list of failures."""
    failures = []
    for name, sql in re.findall(r"```sql (\w+)\n(.*?)```", page.read_text(encoding="utf-8"), re.S):
        sql = re.sub(r"\b(\w+)\.(\w+)\b", lambda m: f"{m[1]}_{m[2]}" if m[1] in SOURCES else m[0], sql)
        sql = re.sub(r"'\$\{inputs\.\w+\.value\}'", "'%'", sql)
        sql = re.sub(r"\$\{(\w+)\}", r"\1", sql)
        try:
            con.execute(f"create or replace temp view {name} as {sql}")
            (rows,) = con.sql(f"select count(*) from {name}").fetchone()
        except duckdb.Error as error:
            failures.append(f"{page.name}: {name}: {str(error).splitlines()[0]}")
            continue
        status = "ok" if rows else "NO ROWS"
        print(f"  {name:<24} {rows:>7,} rows  {status}")
        if not rows:
            failures.append(f"{page.name}: {name}: returned no rows")
    return failures


if __name__ == "__main__":
    if not CACHE_DIR.exists():
        sys.exit(f"No Evidence data cache at {CACHE_DIR}. Run `npm run sources` in dashboard/ first.")
    con = duckdb.connect()
    SOURCES = {name.split(".")[0] for name in source_views(con)}

    failures = []
    for page in sorted(PAGES_DIR.glob("**/*.md")):
        print(page.relative_to(PAGES_DIR).as_posix())
        failures += check_page(con, page)

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  {failure}")
        sys.exit(1)
    print("\nAll dashboard queries ran and returned rows.")
