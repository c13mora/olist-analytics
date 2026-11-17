# olist-analytics

End-to-end analytics engineering project on the Olist e-commerce dataset: daily replay ingestion (dlt), dbt models with tests and snapshots, DuckDB/Snowflake, and an Evidence dashboard.

## Live site

- **Dashboard:** [c13mora.github.io/olist-analytics](https://c13mora.github.io/olist-analytics/):
  executive overview, seller performance, delivery SLAs and customer cohorts.
- **dbt docs:** [c13mora.github.io/olist-analytics/dbt-docs](https://c13mora.github.io/olist-analytics/dbt-docs/):
  every model, column and test, with the lineage graph.

Both are rebuilt from the full replayed dataset and published on every push to
`main` ([`deploy.yml`](.github/workflows/deploy.yml)), only after every dbt
test and every dashboard query passes.

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
uvx --from "kaggle==2.2.5" --with six kaggle datasets download olistbr/brazilian-ecommerce -p data/raw/ --unzip
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

## Running on Snowflake

The same loader and dbt project also run on Snowflake, the secondary target.
On the full dataset, every mart matches the DuckDB build exactly. The run is
documented in [docs/snowflake/](docs/snowflake/), and the reasoning in
[decision record 007](docs/decisions/007-snowflake.md).

### 1. Set up the account (once)

1. **Create a key pair** for the service user (Git Bash includes `openssl`). The
   private key stays on your computer; never commit or share it.
   ```bash
   mkdir -p ~/.snowflake
   openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.snowflake/olist_rsa_key.p8 -nocrypt
   openssl rsa -in ~/.snowflake/olist_rsa_key.p8 -pubout -out ~/.snowflake/olist_rsa_key.pub
   ```
2. **Run [`snowflake/setup.sql`](snowflake/setup.sql)** as `ACCOUNTADMIN` in a
   Snowsight worksheet, with `<PUBLIC_KEY>` replaced by the public key on one
   line (`grep -v "PUBLIC KEY" ~/.snowflake/olist_rsa_key.pub | tr -d '\n'`).
   It creates:
   - a `LOADER` role (writes the raw schemas) and a `TRANSFORMER` role (reads
     raw, builds the dbt schemas);
   - an extra-small warehouse, `OLIST_WH`, that suspends after 60 idle
     seconds, capped at 10 credits a month by a resource monitor;
   - the `OLIST` database;
   - an `OLIST_SERVICE` user that signs in with the key, never a password.
3. **Set two environment variables,** then restart your terminal or editor.
   Credentials never go in the repo.
   ```powershell
   [Environment]::SetEnvironmentVariable("SNOWFLAKE_ACCOUNT", "<ORGNAME-ACCOUNTNAME>", "User")
   [Environment]::SetEnvironmentVariable("SNOWFLAKE_PRIVATE_KEY_PATH", "$HOME\.snowflake\olist_rsa_key.p8", "User")
   ```
   Find the identifier with
   `select current_organization_name() || '-' || current_account_name();`.

### 2. Load and build

From the repo root:

```bash
uv run python ingestion/replay.py --reset --destination snowflake     # raw tables, as LOADER
uv run python ingestion/replay.py --days 90 --destination snowflake   # advance the simulation
cd dbt
uv run dbt debug --target snowflake      # check the connection
uv run dbt build --target snowflake      # every model and test, as TRANSFORMER
uv run dbt source freshness --target snowflake
```

The Snowflake replay keeps its own simulated date (`ingestion/state_snowflake.json`),
separate from the local DuckDB one. On Snowflake, `--reset` does not drop the
dbt snapshot and incremental fact, which belong to the `TRANSFORMER` role; drop
the `DBT_DEV_SNAPSHOTS` schema and run dbt with `--full-refresh` after a reset.

### 3. Clean up

To remove everything when you are done, run as `ACCOUNTADMIN`:

```sql
drop database if exists olist;
drop warehouse if exists olist_wh;
drop user if exists olist_service;
drop role if exists loader;
drop role if exists transformer;
drop resource monitor if exists olist_monitor;
```

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
