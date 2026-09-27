# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project overview

End-to-end analytics engineering portfolio project built on the Brazilian
E-Commerce Public Dataset by Olist. Static CSVs are **replayed in daily batches**
to simulate a live source system, so the project can show incremental models,
snapshots (SCD Type 2), and source freshness checks.

Goals, in priority order:
1. Show production-grade dbt practice (layered models, tests, docs, CI).
2. Stay reproducible: anyone can `git clone` and run it locally on DuckDB, for free.
3. Also run on Snowflake (secondary target, used during a trial window).

Owner: Carlos (Analytics Engineer / Data & Analytics Manager). This is a
portfolio project he will discuss in interviews, so clarity and explainability
matter more than cleverness.

## Stack

| Layer | Tool |
|---|---|
| Python env | uv |
| Ingestion / replay | Python + dlt |
| Warehouse | DuckDB (default `dev` target), Snowflake (`snowflake` target) |
| Transformation | dbt Core (`dbt-duckdb`, `dbt-snowflake`) |
| dbt packages | dbt_utils, dbt-expectations (Metaplane fork), dbt-project-evaluator |
| Linting | SQLFluff (dbt templater) + pre-commit |
| Dashboard | Evidence (`dashboard/`), deployed as a static site |
| CI/CD | GitHub Actions |

## Repository map

```
ingestion/        replay loader (dlt) and simulation state
dbt/              dbt project (models, snapshots, macros, seeds, tests)
dashboard/        Evidence project
data/raw/         Olist CSVs (gitignored, never commit)
docs/             ROADMAP.md and decision records (docs/decisions/)
.github/workflows CI and deploy pipelines
```

## Common commands

```bash
uv sync                                         # install Python deps
uv run python ingestion/replay.py --days 1      # advance the simulation by N days
uv run python ingestion/replay.py --reset       # wipe raw schema, restart at day 0
cd dbt && uv run dbt deps                       # install dbt packages
uv run dbt build --target dev                   # run + test everything on DuckDB
uv run dbt build -s <model>+                    # build a model and its children
uv run dbt snapshot                             # capture SCD2 changes
uv run dbt source freshness
uv run dbt docs generate && uv run dbt docs serve
uv run sqlfluff lint dbt/models
cd dashboard && npm run sources && npm run dev  # Evidence local preview
```

## Replay design

- `ingestion/state.json` stores the current simulated date.
- Each run loads orders whose `order_purchase_timestamp` <= simulated date into
  the `raw` schema, and **updates order status** as the approval, carrier and
  delivery timestamps pass the simulated date (created → approved → shipped →
  delivered). These status changes are what the snapshots capture.
- Reference data (sellers, products, categories, geolocation) loads once at reset.
- Loads are idempotent: re-running the same simulated day must not duplicate rows.

## dbt conventions

- Layers: `staging` (1:1 with sources, rename/cast/clean only) →
  `intermediate` (joins, business logic) → `marts` (facts and dimensions).
- Naming: `stg_olist__<entity>`, `int_<entity>__<verb>`, `fct_<process>`,
  `dim_<entity>`. Snapshots: `snap_<entity>`.
- Materializations: staging = view, intermediate = ephemeral or view,
  marts = table, large facts = incremental.
- Every model has a YAML entry with a description. Every primary key gets
  `unique` + `not_null`. Foreign keys get `relationships` tests.
- SQL style: lowercase keywords, trailing commas, CTEs for every
  step, a final `select * from final`. Follow the `.sqlfluff` config.
- **Cross-warehouse SQL:** code must run on both DuckDB and Snowflake. Prefer dbt
  cross-database macros (`dbt.dateadd`, `dbt.datediff`, `dbt.date_trunc`,
  `dbt.safe_cast`) over dialect-specific functions. If unavoidable, isolate
  the difference in a macro under `macros/`.
- Source data is in Portuguese; translate category names via the provided
  translation table and keep column names in English.

## How to work with me (Claude)

- Work in small steps that map to one ROADMAP task. Don't build a whole layer
  in one go.
- Before writing code for a new task, briefly state the plan and any design
  choice worth discussing (e.g. grain of a fact table, incremental strategy).
- After changes, run the relevant `dbt build -s ...` and SQLFluff, and report
  results. Don't claim something works without running it.
- Explain the *why* of non-obvious decisions in a short comment or in a
  decision record (`docs/decisions/NNN-title.md`), since Carlos needs to defend
  them in interviews.
- Ask before adding new dependencies or packages.
- Never commit files from `data/`, credentials, or `profiles.yml` secrets.
  Snowflake credentials come from environment variables only.
- When a ROADMAP task is done, tick its checkbox in `docs/ROADMAP.md`.
