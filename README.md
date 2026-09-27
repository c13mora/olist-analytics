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

Alternatively, use the Kaggle CLI (requires `~/.kaggle/kaggle.json` with your API token):

```bash
uvx kaggle datasets download olistbr/brazilian-ecommerce -p data/raw/ --unzip
```

> `data/` is gitignored — the CSVs are never committed.

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
uv run python ingestion/replay.py --reset   # load reference data, restart simulation at 2016-12-31
uv run python ingestion/replay.py --days 1  # advance simulation by N days
cd dbt
uv run dbt build --target dev               # build + test all models on DuckDB
uv run dbt snapshot                         # capture SCD2 history
```

The loader and dbt share one DuckDB file, `data/olist.duckdb` (gitignored).
Raw tables land in its `raw` schema.

## Architecture

```
ingestion/    replay loader (dlt) — simulates daily incremental loads
dbt/          dbt project: staging → intermediate → marts, plus snapshots
dashboard/    Evidence static site
data/raw/     Olist CSVs (gitignored)
docs/         ROADMAP and decision records
```

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full build plan.
