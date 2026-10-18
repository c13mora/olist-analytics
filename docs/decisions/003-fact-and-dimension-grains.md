# 003 — Grain of the fact and dimension tables

- **Status:** Accepted
- **Date:** 2026-10-14
- **Code:** `dbt/models/marts/` (built in the Phase 3 tasks that follow)

## Context

The marts are what the dashboard and anyone querying the project will use, so
their grain decides which questions can be answered correctly and which ones
silently double count. The grain of each table is fixed here, before any model
is written, from what the data can actually support:

- 99,441 orders hold 112,650 items, about 1.14 per order. 1,278 orders have
  more than one seller.
- Carrier pickup and customer delivery are recorded **once per order**, even
  for orders with several sellers. Only the seller's shipping deadline is
  recorded per item.
- 2,961 orders are paid in several payments (see [002](002-sources-and-staging.md)).
- 96,096 people (`customer_unique_id`) placed the 99,441 orders, because Olist
  issues a new `customer_id` for every order. 2,997 people ordered more than
  once, and 250 of them used different zip codes on different orders.
- Purchases run from 2016-09-04 to 2018-10-17; promised delivery dates reach
  2018-11-12.

## Decision

### Facts

| Table | One row per | Rows | Key |
|---|---|---|---|
| `fct_order_items` | order item | 112,650 | `order_item_key`, from (`order_id`, `item_sequence`) |
| `fct_payments` | payment | 103,886 | `payment_key`, from (`order_id`, `payment_sequence`) |
| `fct_deliveries` | order | 99,441 | `order_id` |

**`fct_order_items`: one row per item.** This is the finest grain for sales, so
price and freight sum correctly by product, seller, category or date. It
carries the order's customer, status and purchase date, repeated on each of the
order's items.

**`fct_payments`: one row per payment, kept separate from items.** An order
with two items and two payments would produce four rows if payments and items
shared a table, and any sum over them would double count. Order-level payment
totals are already available in `int_order_payments__aggregated_to_orders`.

**`fct_deliveries`: one row per order, covering every order.** Carrier and
delivery dates only exist per order, so a finer grain would invent data.
Orders not delivered (yet) stay in the table, with delivery measures left
empty. On-time and cancellation rates then use the right denominator.

| Alternative | Why not |
|---|---|
| A single order-grain sales fact | Loses product and seller detail, which most sales questions need. |
| One fact holding items and payments | Multiplies rows whenever an order has several of both. |
| Spread payments across items | Any split (by price, evenly) is arbitrary; the source does not say which item a voucher paid for. |
| Deliveries per order and seller | The source has no per-seller delivery dates, so the rows would repeat the same dates. |
| Deliveries for delivered orders only | Hides canceled and late orders from the denominators, so on-time rates look better than they are. |

### Dimensions

| Table | One row per | Rows | Key |
|---|---|---|---|
| `dim_customers` | person | 96,096 | `customer_unique_id` |
| `dim_sellers` | seller | 3,095 | `seller_id` |
| `dim_products` | product | 32,951 | `product_id` |
| `dim_date` | day, 2016-09-01 to 2018-12-31 | 852 | `date_day` |

**`dim_customers`: one row per person, not per order.** Repeat purchases and
cohorts (planned for the dashboard) are only possible at this grain. A
person's location comes from their most recent order as of the simulated date.
Delivery analysis needs the location of each specific order, so
`fct_deliveries` carries the order's own zip code and state.

**`dim_sellers`** adds coordinates from `int_geolocation__grouped_by_zip`.
**`dim_products`** adds the English category name; the fallback for products
whose category has no translation, or no category at all, is decided in the
dimensions task. **`dim_date`** is built with `dbt_utils.date_spine`, which works
on DuckDB and Snowflake, and covers every purchase and promised date.

| Alternative | Why not |
|---|---|
| `dim_customers` per `customer_id` | It is one-to-one with orders, so it cannot tell that two orders came from the same person. |
| Track customer location history (SCD Type 2) | Only 250 people moved; snapshots are better spent on order status (Phase 4). |
| A date dimension generated from the data | Gaps on days without orders; a spine guarantees every day exists. |

### Keys

- **Dimensions keep Olist's own ids.** They are already unique and stable, so a
  separate surrogate key adds a join without adding information.
- **Facts with a two-column grain get a one-column key** built with
  `dbt_utils.generate_surrogate_key` (`order_item_key`, `payment_key`). It gives
  a simple primary key for `unique` + `not_null` tests and joins.
- **Dates join on the date itself.** Facts link to `dim_date` once per date they
  carry (purchase, delivery, promised delivery), so one date dimension serves
  every role.

## Consequences

- **Revenue has two sources that differ slightly.** Sales measures come from
  `fct_order_items` (price + freight) and payment measures from `fct_payments`.
  They differ for the 249 orders flagged in [002](002-sources-and-staging.md).
- **Order-level attributes repeat on item rows.** Counting orders from
  `fct_order_items` needs `count(distinct order_id)`, and order-level values
  must not be summed there.
- **Not every order appears in every fact.** 775 orders without items (mostly
  unavailable or canceled) are absent from `fct_order_items` but present in
  `fct_deliveries`; the one order without payments is absent from
  `fct_payments`.
- **Customer location has two meanings.** `dim_customers` gives where a person
  lives now; `fct_deliveries` gives where each order went. They differ for at
  most 250 people.
- **Counting customers means counting people.** Distinct customers are
  `count(distinct customer_unique_id)`; counting `customer_id` would count
  orders.
- **Incremental later.** `fct_order_items` is the largest fact and becomes
  incremental in Phase 4. The strategy is decided then; staging already
  exposes `_loaded_at`, which changes whenever an order's status does.

## Verification

The grains are enforced by tests as each table is built: `unique` + `not_null`
on every key listed above, and `relationships` tests from each fact to its
dimensions.
