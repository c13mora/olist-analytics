# 004 — Building and testing the marts

- **Status:** Accepted
- **Date:** 2026-10-18
- **Code:** [`models/marts/`](../../dbt/models/marts/), [`models/intermediate/int_orders__joined_to_customers.sql`](../../dbt/models/intermediate/int_orders__joined_to_customers.sql), [`seeds/`](../../dbt/seeds/), [`packages.yml`](../../dbt/packages.yml)

## Context

Phase 3 builds the dimensions and facts whose grains and keys are fixed in
[003](003-fact-and-dimension-grains.md); this record does not repeat them. It
covers what came up while building: how each dimension fills its attributes,
which delivery measures the logistics fact carries, and how the marts are
tested.

## 1. Dimensions

**`dim_customers` (96,096 people).**
- A person's location comes from their most recent order. Ties on the purchase
  time go to the later `customer_id`, so the result is deterministic.
- It also carries first and last purchase dates and an order count, which the
  cohort and repeat-purchase analysis needs. The count includes orders in any
  status.
- 269 people have no coordinates, because the source has no geolocation for
  their zip code (see [002](002-sources-and-staging.md)).

**`dim_products` (32,951 products), English category names.**
- Olist's translation table lacks two categories (13 products, 24 items). Their
  English names come from a two-row seed, written by hand in the source's
  style: `pc_gamer` and `portable_kitchen_and_food_preparers`.
- The 610 products with no category at all get `unknown`.
- Only a *missing* category becomes `unknown`. A new category absent from both
  translation sources stays null, so a `not_null` test fails instead of
  hiding it.

| Alternative | Why not |
|---|---|
| `coalesce(translation, 'unknown')` | A new untranslated category would silently become `unknown`. |
| Fall back to the Portuguese name | Mixes languages in one column; the project keeps names in English. |

**`dim_sellers` (3,095 sellers)** adds coordinates; 7 sellers have none.

**`dim_date` (852 days, 2016-09-01 to 2018-12-31).**
- The bounds are fixed, because the source is a fixed export. They cover
  every purchase and promised delivery date.
- `day_of_week` runs from 0 (Sunday) to 6. That holds on DuckDB, and on
  Snowflake with its default `WEEK_START` setting. Weeks start on Monday.
- No month or day names: `monthname()` returns `January` on DuckDB but `Jan`
  on Snowflake, and the dashboard can format dates itself.

## 2. Facts

**One shared join.** Every fact needs the person (`customer_unique_id`), which
Olist links to orders only through the per-order `customer_id`.
`int_orders__joined_to_customers` does that join once. It stays ephemeral (the
project default): it is a 1:1 join, and the facts built on it test its grain.

**`fct_deliveries` measures**, all in calendar days, null until the later
milestone happens:

| Column | Meaning |
|---|---|
| `days_to_carrier` | purchase to carrier pickup |
| `days_in_transit` | carrier pickup to delivery |
| `days_to_deliver` | purchase to delivery |
| `days_late_vs_estimate` | delivery date minus promised date; negative when early |
| `delivery_status` | `on_time`, `late` or `not_delivered` |
| `has_timestamp_anomaly` | source timestamps out of order |

- **`delivery_status` comes from the delivery date, not the order status.** Six
  canceled orders were still delivered, and the order status says nothing
  about timeliness. Delivery on the promised day counts as on time.
- **Out-of-order timestamps are flagged, not removed.** 1,382 orders have a
  carrier pickup before approval or purchase, or a delivery before pickup.
  They keep their values, and SLA analysis can exclude them with the flag.
  Negative durations only occur on flagged orders.

| Alternative | Why not |
|---|---|
| Durations in hours | The promised date has no time of day, so lateness can only be measured in days; mixing units would confuse. |
| Drop anomalous orders | Hides a source quality issue and changes order counts. |
| Status from `order_status` | Cannot distinguish on time from late, and misses the delivered canceled orders. |

**Result:** 93.2% of delivered orders arrived on time. On-time orders took a
median of 10 days and arrived 13 days before the promise; late ones took 31
days and arrived 7 days late.

## 3. Testing the marts

**Guards against join mistakes.**
- `dbt_utils.equal_rowcount` compares each fact with its staging source, and
  `dim_products` and `dim_sellers` with theirs. A join can never add or lose
  rows unnoticed.
- 12 `relationships` tests check every fact column that points to a
  dimension: person, product, seller, and each date.
- `fct_order_items` and `fct_payments` also check that their `order_id` exists
  in `fct_deliveries`, the table with every order. That is fact to fact, but
  it closes the last gap.

**`dbt-expectations` from Metaplane's fork.** The original
`calogica/dbt_expectations` is frozen at 0.10.4, and the dbt hub redirects it
to `metaplane/dbt_expectations`. The project now pins `>=0.10.10, <0.11.0`.
That also swaps its helper package to `godatadriven/dbt_date`. Re-resolving
the packages moved `dbt_project_evaluator` from 1.4.0 to 1.4.1.

**Tests chosen because each catches a real failure**, and holds on the full
dataset today:

| Test | What it protects |
|---|---|
| Price above zero; freight, payments and installments not negative | Revenue sums. 9 payments are exactly 0, so 0 is allowed there. |
| Zip code prefixes are exactly five digits | The leading zeros that raw keeps by loading text ([001](001-replay-loader.md)). |
| Promised date and shipping deadline never before the purchase | Timestamps mixed up upstream. |
| Last purchase never before first purchase | The person rollup in `dim_customers`. |
| Sum of `order_count` in `dim_customers` equals the orders in `fct_deliveries` | Rolling orders up to people loses or duplicates none. |
| `dim_date` days are exactly one apart | Every fact date finds its day. |
| Every day of the source's active period has orders | The replay skipping a day. |

**Tests rejected:**

| Candidate | Why not |
|---|---|
| `total_item_value = price + freight_value` | Restates the model's own formula. |
| Delivery after pickup on non-flagged orders | That is the anomaly flag's own definition. |
| `dbt_utils.recency` on purchase dates | Always stale in the replay; source freshness already covers recency. |
| Product weight above zero | 4 products weigh 0; the test would only add noise. |

**The missing-days test follows the replay.** It checks days from 2017-01-05,
when daily volume starts, up to the latest loaded purchase date. So it never
fails on days the replay has not reached yet.

- **It stops at 2018-08-31.** After that, the export holds only 20 straggler
  orders (16 in September, 4 in October), and 32 days are empty.
- **How:** a `row_condition`. The macro applies it both to the date bounds and
  to the rows it counts, so the end still moves with the simulated date.

## Consequences

- **The marts answer at the grain of 003.** Revenue comes from
  `fct_order_items`, payments from `fct_payments`, and on-time rates from
  `fct_deliveries`.
- **Two bounds are hard-coded to the export.** `dim_date` ends on 2018-12-31
  and the missing-days test on 2018-08-31. Extending the data would mean
  revisiting both.
- **One warning remains on every build:** the orders whose payments do not
  match items (see [002](002-sources-and-staging.md)).
- **Snowflake is untested until Phase 6**, in particular `day_of_week`, which
  depends on Snowflake's `WEEK_START` setting.
- **Incremental next.** Phase 4 turns `fct_order_items` into an incremental
  model.

## Verification

- **Full build:** `dbt build -s olist` ran 130 nodes, with 129 passes and the
  known warning. That holds mid-replay (2017-03-31: 26 mismatched orders) and
  at the end of the data (249).
- **Totals:** item price (13,591,643.70 BRL), freight (2,251,909.54 BRL) and
  payments (16,008,872.12 BRL) match staging to the cent. Order counts in
  `dim_customers` add up to all 99,441 orders.
- **Negative tests:**
  - An item with an unknown product and seller failed both relationship
    tests.
  - Deleting one day of orders failed the missing-days test with exactly 1
    day.
