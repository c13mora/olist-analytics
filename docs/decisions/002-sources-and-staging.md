# 002 — Sources, staging and known data issues

- **Status:** Accepted
- **Date:** 2026-10-08
- **Code:** [`models/staging/olist/`](../../dbt/models/staging/olist/), [`models/intermediate/`](../../dbt/models/intermediate/), [`macros/dlt_loaded_at.sql`](../../dbt/macros/dlt_loaded_at.sql), [`tests/assert_order_payments_match_item_totals.sql`](../../dbt/tests/assert_order_payments_match_item_totals.sql)

## Context

Phase 1 lands the Olist data in the `raw` schema as text, exactly as the source
has it (see [001](001-replay-loader.md)). Phase 2 turns it into typed, documented,
tested models that the marts can trust. Along the way, two source issues need a
decision about grain: geolocation has many points per zip code, and some orders
are paid in several payments.

## 1. Source freshness is measured from dlt's load id

In the replay, business timestamps are years old even right after a load, so a
freshness check on `order_purchase_timestamp` would always fail. Freshness must
measure when the loader last delivered data.

- **Decision:** dlt stamps every row with `_dlt_load_id`, the start of the load as
  Unix epoch seconds. A row updated by a later load (e.g. an order status
  change) gets the newer id. The macro `dlt_loaded_at` converts it to a naive
  UTC timestamp, with one version per warehouse so the type matches on DuckDB
  and Snowflake.
- **Thresholds:** warn after 24 hours and error after 48 hours, matching a daily
  load. Reference tables load only at reset, so they have no freshness check.
- **`loaded_at_query`, not `loaded_at_field`:** dbt renders `loaded_at_field` while
  parsing YAML, before project macros exist, so the macro is undefined there.
  `loaded_at_query` is rendered when freshness runs.

| Alternative | Why not |
|---|---|
| A business timestamp | Always years old in the replay, so always stale. |
| Have the loader add a `_loaded_at` column | Slightly clearer, but changes Phase 1 code for something dlt already records. |
| `inserted_at` in dlt's `_dlt_loads` table | Pipeline-level, not per table, so it cannot tell which table stopped arriving. |

## 2. Staging conventions

One view per source table, named `stg_olist__<table>`.

- **Rename only for a reason.** Source names are kept, so each column traces back
  easily. Three kinds of rename only:
  - timestamps end in `_at` and dates in `_date` (`order_purchase_timestamp` →
    `purchased_at`, `order_delivered_carrier_date` → `shipped_at`);
  - source misspellings are fixed (`product_name_lenght` →
    `product_name_length`);
  - sequence numbers stop looking like identifiers (`order_item_id` →
    `item_sequence`, `payment_sequential` → `payment_sequence`).
- **Casts fail loudly.** Plain `cast()` with dbt's cross-warehouse type macros. A
  value that does not parse fails the build, instead of silently becoming null
  as it would with `safe_cast`.
- **Light cleaning only.** Review comments are trimmed (8,120 messages had
  padding), and whitespace-only comments become null.
- **No joins in staging.** Category names stay in Portuguese. The English
  translation moves to `dim_products` in Phase 3, which can also cover the two
  categories missing from the translation table.
- **`_loaded_at` on every model**, from the freshness macro, ready for incremental
  models in Phase 4.
- **Descriptions written once.** Column descriptions live in doc blocks
  (`_olist__docs.md`) and are reused by sources and staging, so ~50 descriptions
  are not kept in sync twice.

| Alternative | Why not |
|---|---|
| Rename everything to a house style (e.g. drop entity prefixes) | Harder to trace a column back to the source, and ambiguous once customers and sellers are joined (both have a city and state). |
| `safe_cast` everywhere | Hides format changes in the source as nulls. |
| Translate categories in staging | It is a join, and staging stays 1:1 with sources. |

## 3. Tests live on staging, not on sources

- **Primary keys:** `unique` + `not_null` on single-column keys.
  Items, payments and reviews have two-column keys, tested with
  `dbt_utils.unique_combination_of_columns` plus `not_null` on each column. No
  surrogate keys are added in staging; the marts can add them if needed.
- **Accepted values** on order status, payment type, review score and state
  codes, each paired with `not_null`, because `accepted_values` lets nulls
  through. The 27 state codes are defined once with a YAML anchor.
- **Why staging:** tests then check the typed, cleaned data that marts read, and
  are not duplicated on raw tables.
- **Proven to fail:** with a duplicate order and an unknown status inserted into
  `raw.orders`, `unique` and `accepted_values` both failed.

## 4. Geolocation: one point per zip code prefix

The source has 1,000,163 rows for 19,015 prefixes:

- 262k rows are exact duplicates;
- after removing them, a prefix still has a median of 29 points;
- a typical prefix's points spread over about 2.6 km, but some spread over
  up to about 3,900 km;
- 42 points fall outside Brazil, and for 5 prefixes every point does.

Joining customers or sellers to this table directly would multiply their rows.

- **Decision:** staging stays 1:1 with the source. The intermediate model
  `int_geolocation__grouped_by_zip` builds one row per prefix:
  1. it keeps each distinct point once, so duplicates do not weigh twice;
  2. it drops points outside a rough bounding box around Brazil;
  3. it takes the median latitude and longitude, plus the most common state.
- **Tests:** `unique` + `not_null` on the prefix keep the fan-out from coming back,
  and latitude and longitude are checked against the bounding box.

| Alternative | Why not |
|---|---|
| Remove duplicates in staging | Staging stays 1:1 with the source; grouping logic belongs in intermediate. |
| Average instead of median | Pulled toward stray points that can be thousands of kilometers away. |
| Pick one point per prefix | Arbitrary, and as exposed to strays as the average. |

## 5. Payments: one row per payment, rolled up per order

2,961 orders are paid in several payments, up to 29: mostly a credit card plus
vouchers (2,245), several vouchers (427) or several credit cards (287).

- **Decision:** staging keeps one row per payment, the grain `fct_payments` will
  use. The intermediate model `int_order_payments__aggregated_to_orders` rolls
  payments up to one row per order for order-level facts: number of payments,
  total paid, voucher amount, maximum installments, and the main payment type.
- **Main payment type** is the type of the largest payment, with ties going to
  the earliest payment.
- **Payments vs. items:** for 98,416 of 98,665 orders, total paid matches items
  plus freight within 1 BRL. The 249 that differ are mostly single credit-card
  payments, probably installment interest. A singular test lists them with
  severity `warn`, so the issue stays visible without failing builds.

| Alternative | Why not |
|---|---|
| Keep only the first payment per order | Drops the vouchers, so totals are wrong. |
| One column per payment type | Wide and rigid; a new payment type would need a schema change. |
| A failing reconciliation test | It would fail every build on a known source issue we cannot fix. |

## 6. Intermediate models are views

The project default for intermediate models is ephemeral, but dbt cannot test
ephemeral models, and both models above exist to fix a grain that must be
tested. The geolocation model also aggregates 1M rows that two dimensions will
read. Both are views, set in the model with a comment saying why.

## 7. Linting runs on a dedicated target

SQLFluff renders models through dbt from the repo root, where the `dev`
profile's relative DuckDB path does not resolve. It uses a `lint` target backed
by an in-memory database, which is enough because linting only compiles SQL.
The pre-commit hook runs SQLFluff through uv, so it uses the same locked
versions as CI.

## Consequences

- **Missing coordinates.** The source has no geolocation for 157 customer
  prefixes (278 customers) and 7 sellers, and 5 prefixes drop out because all
  their points are outside Brazil. 99,162 of 99,441 customers and 3,088 of
  3,095 sellers can be placed on a map; the dimensions will show null
  coordinates for the rest.
- **Orders without payments or items.** One order has no payment, so it is
  absent from the payment rollup. 775 orders have no items, almost all
  unavailable or canceled. Order-level facts must use outer joins.
- **A permanent warning.** `dbt build` always ends with one warning, the 249
  orders where payments do not match items. It is expected and documented.
- **Snowflake is untested.** The Snowflake version of `dlt_loaded_at` and the use
  of `median()` and `mode()` will be verified in Phase 6.

## Verification

- `dbt build -s olist`: 54 nodes, 53 pass, 1 expected warning (249 rows), exit
  code 0, on the full dataset (99,441 orders).
- Staging row counts and non-null counts match raw for every column; item
  prices sum to the same total.
- The payment rollup matches staging to the cent (16,008,872.12 BRL paid, of
  which 379,436.87 BRL in vouchers).
- Freshness passes after a load and fails as stale with thresholds below the
  data's age.
