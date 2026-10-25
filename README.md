# olist-analytics

End-to-end analytics engineering project on the Olist e-commerce dataset: daily replay ingestion (dlt), dbt models with tests and snapshots, DuckDB/Snowflake, and an Evidence dashboard.

## Quick start

### 1. Clone and install

```bash
git clone <repo-url> && cd olist-analytics
uv sync
```

### 2. Download the Olist dataset

1. Create a free account at [Kaggle](https://www.kaggle.com)
2. Go to the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
3. Download and unzip into `data/raw/` so the layout is:

```
data/raw/
├── olist_customers_dataset.csv
├── olist_geolocation_dataset.csv
├── olist_order_items_dataset.csv
├── olist_order_payments_dataset.csv
├── olist_order_reviews_dataset.csv
├── olist_orders_dataset.csv
├── olist_products_dataset.csv
├── olist_sellers_dataset.csv
└── product_category_name_translation.csv
```

Alternatively, use the Kaggle CLI. Create an API token in your Kaggle
settings (Settings → API), then either save it as the only content of
`~/.kaggle/access_token` or set it in the `KAGGLE_API_TOKEN` environment
variable:

```bash
uvx --from "kaggle>=2.2" kaggle datasets download olistbr/brazilian-ecommerce -p data/raw/ --unzip
```

> `data/` is gitignored — the CSVs are never committed.

### CI

Every pull request into `main` runs two GitHub Actions jobs
([`ci.yml`](.github/workflows/ci.yml)): SQLFluff, and a build on real
replayed data. The build job downloads the CSVs from Kaggle with a token
stored in the `KAGGLE_API_TOKEN` repository secret and caches them. It then
loads three months, builds and tests every model, loads one more day and
builds again (exercising the incremental model and the snapshot), and checks
source freshness. To run it in a fork, add your own Kaggle token as that
secret.

### 3. Set up dbt

```bash
export DBT_PROFILES_DIR=./dbt   # profiles.yml lives in dbt/, not ~/.dbt/
cd dbt
uv run dbt deps                  # install dbt packages
uv run dbt debug                 # verify the DuckDB connection
```

### 4. Run the pipeline

From the repo root:

```bash
uv run python ingestion/replay.py --reset   # load reference data + 2016 orders, restart at 2016-12-31
uv run python ingestion/replay.py --days 1  # load what happened in the next N days
cd dbt
uv run dbt build --target dev               # build + test all models on DuckDB
uv run dbt snapshot                         # capture SCD2 history
```

The loader and dbt share one DuckDB file, `data/olist.duckdb` (gitignored).
Raw tables land in its `raw` schema.

To verify that loads are idempotent, replay the same day twice and compare:

```bash
uv run python ingestion/check_idempotency.py   # advances one day; exits 1 if raw changed
```

`--reset` also drops the order status snapshot and the incremental
`fct_order_items`, so no history "from the future" survives a restart; dbt
rebuilds them on its next run.

### 5. Watch incremental models and snapshots at work

```bash
uv run python scripts/demo.py --reset --days 7
```

Replays seven days one at a time and shows, per day, what the incremental
model processed and what the snapshot recorded, then one order's status
history. See [docs/demo.md](docs/demo.md) for a walkthrough of the output.

## Architecture

```
ingestion/    replay loader (dlt) — simulates daily incremental loads
dbt/          dbt project: staging → intermediate → marts, plus snapshots
scripts/      demo of incremental models and snapshots
dashboard/    Evidence static site
data/raw/     Olist CSVs (gitignored)
docs/         ROADMAP, decision records and demo walkthrough
```

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full build plan.
