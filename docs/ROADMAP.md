# Roadmap — Olist Analytics Engineering Project

Pace: ~3 hours/week. Estimated total: 11–14 weeks.
Rule: finish and push each phase before starting the next.

## Target repository structure

```
olist-analytics/
├── CLAUDE.md
├── README.md
├── pyproject.toml              # uv-managed Python deps
├── .pre-commit-config.yaml
├── .sqlfluff
├── .gitignore                  # data/, *.duckdb, .env, target/, logs/
├── .github/workflows/
│   ├── ci.yml                  # lint + dbt build on every PR
│   └── deploy.yml              # Evidence site + dbt docs to GitHub Pages
├── data/raw/                   # Olist CSVs (gitignored)
├── ingestion/
│   ├── replay.py               # daily replay loader (dlt)
│   └── state.json              # current simulated date
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml            # dev (DuckDB) + snowflake, secrets via env vars
│   ├── packages.yml
│   ├── models/
│   │   ├── staging/olist/      # _olist__sources.yml, stg_olist__*.sql
│   │   ├── intermediate/
│   │   └── marts/
│   │       ├── core/           # dim_customers, dim_sellers, dim_products, dim_date
│   │       ├── sales/          # fct_order_items, fct_payments
│   │       └── logistics/      # fct_deliveries
│   ├── snapshots/              # snap_orders
│   ├── macros/
│   ├── seeds/                  # e.g. Brazilian state → region mapping
│   └── tests/                  # singular tests
├── dashboard/                  # Evidence project
└── docs/
    ├── ROADMAP.md
    └── decisions/              # short decision records
```

## Phase 0 — Setup (1 week)
- [x] Create GitHub repo, `.gitignore`, MIT license, README stub
- [x] Initialize uv project; add dbt-duckdb, dbt-snowflake, dlt, sqlfluff, pre-commit
- [x] Download Olist CSVs from Kaggle into `data/raw/` (document steps in README)
- [x] `dbt init`, configure `dev` target on DuckDB, `dbt debug` passes
- [x] SQLFluff config + pre-commit hooks
- [x] Skeleton `ci.yml` that runs lint

## Phase 1 — Replay loader (1–2 weeks)
- [x] `replay.py --reset`: load reference tables (sellers, products, categories, geolocation)
- [x] `replay.py --days N`: load new orders, items, payments, reviews up to the simulated date
- [x] Status updates on existing orders as timestamps pass the simulated date
- [x] Idempotency check: re-running a day creates no duplicates
- [x] Decision record: why replay, and how status is derived

## Phase 2 — Sources and staging (1–2 weeks)
- [x] `_olist__sources.yml` with descriptions and freshness rules
- [x] One staging model per source table (rename, cast, clean)
- [x] Generic tests: unique/not_null PKs, accepted_values on statuses
- [ ] Handle known data issues (duplicate geolocation rows, multi-payment orders)

## Phase 3 — Intermediate and marts (2–3 weeks)
- [ ] Define the grain of each fact table in a decision record
- [ ] Dimensions: customers, sellers, products (with English category names), date
- [ ] Facts: order items, payments, deliveries (promised vs actual dates)
- [ ] Relationship tests between facts and dimensions
- [ ] Add dbt_utils and dbt-expectations tests where they add value

## Phase 4 — Incremental models and snapshots (1–2 weeks)
- [ ] `snap_orders` snapshot capturing status changes (SCD2)
- [ ] Convert the largest fact to incremental; document the strategy
- [ ] Demo: advance replay several days, show snapshot history and incremental runs
- [ ] Source freshness wired into CI

## Phase 5 — Evidence dashboard (2 weeks)
- [ ] Pages: executive overview, seller performance, delivery SLAs, customer cohorts
- [ ] Build the site in CI; deploy to GitHub Pages together with dbt docs
- [ ] Live links added to README

## Phase 6 — Snowflake run (start the trial only here, ~1–2 weeks)
- [ ] Roles, warehouse (XS, auto-suspend), database and schemas
- [ ] `snowflake` target via env vars; full `dbt build` passes
- [ ] Fix any dialect differences via cross-database macros
- [ ] Screenshots: query history, cost/credits used, build output → `docs/snowflake/`
- [ ] README section "Running on Snowflake"

## Phase 7 — Polish (1 week)
- [ ] dbt-project-evaluator passes (or exceptions documented)
- [ ] README: problem, architecture diagram, lineage screenshot, key findings, how to run, next steps
- [ ] Link from the earlier Streamlit Olist project ("v1 → v2" story)
- [ ] Pin repo on GitHub profile
