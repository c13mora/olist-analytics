# 005 — Incremental models, snapshots and CI on replayed data

- **Status:** Accepted
- **Date:** 2026-10-25
- **Code:** [`snapshots/snap_orders.yml`](../../dbt/snapshots/snap_orders.yml), [`fct_order_items.sql`](../../dbt/models/marts/sales/fct_order_items.sql), [`ingestion/replay.py`](../../ingestion/replay.py), [`scripts/demo.py`](../../scripts/demo.py), [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)

## Context

The replay ([001](001-replay-loader.md)) exists so the project can show the
dbt features that only matter when data changes. Phase 4 builds them:

- a snapshot of order status history (SCD Type 2);
- an incremental version of the largest fact, `fct_order_items`;
- a demo to watch both at work;
- CI that runs the pipeline on real data, including source freshness.

The replay shapes each decision: changes arrive one simulated day at a time,
the same day can be reloaded, and `--reset` restarts the simulation.

## 1. The snapshot dates history in business time

`snap_orders` keeps one row per version of each order, valid from
`dbt_valid_from` to `dbt_valid_to`.

- **Decision:** the timestamp strategy on a new column in `stg_olist__orders`,
  `status_updated_at`: the latest milestone that has happened so far
  (purchase, approval, carrier pickup, delivery).
- **Why it works:** in the replay, a status only changes when a milestone
  passes, and canceled orders switch at their last milestone. So the latest
  milestone is exactly the business time of the order's latest change.
- **What it gives:** dbt uses it as `dbt_valid_from`, so time spent in each
  status is real and measurable, e.g. a median of 6.7 days with the carrier.
- **Cross-warehouse:** empty milestones fall back to the purchase time before
  `greatest()`, because Snowflake's `greatest()` returns null if any input is
  null.
- **Modern pattern:** the snapshot is defined in YAML, with
  `relation: ref('stg_olist__orders')`.

| Alternative | Why not |
|---|---|
| `check` strategy on status and dates | `dbt_valid_from` would be when `dbt snapshot` ran. Ten replayed days run in a minute would give status durations of seconds. |
| Timestamp strategy on `_loaded_at` | Load time moves whenever a day is reloaded, which would record versions where nothing changed. |
| Snapshot the raw source directly | Raw is text, and the snapshot needs a computed column; a YAML snapshot cannot transform its input. |

**Tests:** exactly one current version per order (`unique` on `order_id`
where `dbt_valid_to` is null), and versions that follow each other without
gaps or overlaps (`dbt_utils.mutually_exclusive_ranges`).

## 2. The largest fact is incremental, keyed on load time

An item never changes after it arrives, but its order's status does, and the
status repeats on every item row. So an incremental run must pick up new
items **and** existing items whose order changed.

- **Change detection:** `_loaded_at` on the fact is the later of the item's
  and the order's load time. A status change makes the loader reload the
  order, which moves `_loaded_at` forward for all its items. Each run takes
  rows newer than the newest one already in the table.
- **Writing:** `merge` on `order_item_key`. New items are inserted; existing
  ones get the new status. Supported natively on DuckDB (1.4+) and Snowflake.
- **Column changes:** `on_schema_change: fail`. A changed column stops the
  build until the table is rebuilt on purpose with `--full-refresh`.
- **Reloading a day** reprocesses its items with identical values: harmless.

| Alternative | Why not |
|---|---|
| Watermark on business time (`status_updated_at`) | Works here only because the replay never delivers late; in a real pipeline, late-arriving data would be skipped forever. |
| `append` | Cannot update a row; a status change would duplicate the item. |
| `microbatch` | Batches by event date (the purchase), so a status change on an old order falls in an old batch and is never reprocessed. |
| `delete+insert` | Would also work; `merge` states the intent more clearly and is native on both warehouses. |

**First deployment needs `--full-refresh`.** The Phase 3 table has no
`_loaded_at`, so a normal run fails. DuckDB reports it misleadingly as
`Referenced table "this_table" not found`.

## 3. `--reset` drops the tables that accumulate history

The snapshot and the incremental fact are not rebuilt from scratch on each
run, so after `--reset` they would keep rows "from the future" of the
restarted simulation.

- **Decision:** `replay.py --reset` also drops `main_snapshots.snap_orders` and
  `main_marts.fct_order_items`. dbt rebuilds both on its next run, so no
  `--full-refresh` is needed after a reset.
- **Trade-off:** the loader now knows two dbt table names. They follow dbt's
  default naming on the `dev` target, as a comment in the loader says.

| Alternative | Why not |
|---|---|
| Document a manual drop or `--full-refresh` after every reset | Easy to forget, and the failure is silent: wrong history, not an error. |

## 4. The demo runs a realistic daily job

`scripts/demo.py` replays day by day. For each day it runs a full daily
`dbt build` of every model plus the snapshot, without tests. All tests run
once at the end.

The first version rebuilt only the incremental fact and the snapshot each
day. The final test run then failed four tests, because the other marts were
left behind while staging moved on. The tests caught it, and the demo now
mirrors a real daily job. The output is walked through in
[`docs/demo.md`](../demo.md).

## 5. CI builds and tests on real replayed data

Until this phase, CI only linted SQL; no model or test ever ran in CI. A
freshness check needs loaded data, and the CSVs are never committed.

- **Decision:** a second CI job downloads the dataset from Kaggle, using a
  token stored in the `KAGGLE_API_TOKEN` repository secret, and caches the
  CSVs. The dataset never changes, so later runs skip Kaggle.
- **Kaggle's newer tokens:** a single string, not the old `kaggle.json`
  username and key. The Kaggle CLI 2.2+ reads it from `KAGGLE_API_TOKEN`.
- **Steps:**
  1. Replay three months.
  2. `dbt build -s olist`: every model and test, plus the first snapshot.
  3. Load one more day and build again. This exercises the incremental path
     and adds snapshot versions, which a single build never would.
  4. `dbt source freshness`.
- **Scope:** `-s olist` keeps `dbt_project_evaluator`'s models out until
  Phase 7.
- **What freshness proves in CI:** right after a load it always passes, so in
  CI it catches a loader that delivered nothing. Warning when data stops
  arriving needs a scheduled pipeline, which is out of scope.

| Alternative | Why not |
|---|---|
| Commit a small sample of the CSVs | Breaks the project rule against committing data, and redistributes a licensed dataset (CC BY-NC-SA). |
| Generate synthetic data in CI | The tests would check made-up data instead of Olist's real quirks. |
| Keep CI to linting | Leaves the tests depending on someone remembering to run them. |

## Consequences

- **One status per order per snapshot run.** The snapshot sees the state at
  each run, so statuses reached and left on the same day collapse. Run
  `dbt snapshot` after every `replay.py --days 1`; jumping several days loses
  intermediate statuses (see [001](001-replay-loader.md)).
- **The snapshot and incremental fact depend on run order.** They hold
  history that a plain rebuild cannot recreate after the fact.
- **Hard-coded names.** `--reset` drops two tables by name, tied to the `dev`
  target's schema naming.
- **CI needs the secret.** Pull requests from forks get no secrets, so their
  build job can only run on a cached dataset. A fork must add its own token.
- **The cache can expire.** GitHub evicts a cache after seven days without
  use, and caches made on a pull request are scoped to it. When the cache is
  missing, the job simply downloads again.
- **Snowflake is untested until Phase 6:** the snapshot and the merge on
  Snowflake.

## Verification

- **Snapshot,** over 14 replayed days:
  - Reloading a day left the version count at 828.
  - One current version per order, matching staging.
  - Every `dbt_valid_from` equals `status_updated_at`.
  - Example history: created Jan 5 → approved Jan 7 → shipped Jan 11 →
    delivered Jan 17.
- **Incremental fact:**
  - Over 10 replayed days, each run processed only that day's changes:
    between 37 and 211 rows, while the table grew from 637 to 1,165.
  - Reloading a day reprocessed its rows and left the table unchanged.
  - The result was identical, row by row, to a full rebuild.
- **Demo:** from a clean reset, 7 days, then every test passes. Snapshot
  versions added each day equal new orders plus status updates.
- **CI** ([run 40240427117](https://github.com/c13mora/olist-analytics/actions/runs/40240427117)):
  - The first run downloaded the dataset from Kaggle and saved the cache.
  - Both builds: 138 passes and the known warning.
  - All 5 sources fresh.
  - Build job time: 2 min 2 s.
