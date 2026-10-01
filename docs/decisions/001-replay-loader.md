# 001 — Replay the static Olist dataset as a daily source

- **Status:** Accepted
- **Date:** 2026-10-01
- **Code:** [`ingestion/replay.py`](../../ingestion/replay.py), [`ingestion/check_idempotency.py`](../../ingestion/check_idempotency.py)

## Context

The Olist dataset is a static export: nine CSVs holding the *final* state of
99,441 orders placed between September 2016 and October 2018. Loaded once, it
never changes, so a project built on it cannot show the parts of analytics
engineering that deal with change over time: incremental models, snapshots
(SCD Type 2) and source freshness checks.

## Decision

A Python + dlt loader replays the CSVs as if they came from a live source
system. `ingestion/state.json` holds a simulated date, and the `raw` schema
always reflects the source **as of the end of that date**.

- `replay.py --reset` wipes `raw`, loads reference data, and backfills
  everything up to day 0 (2016-12-31).
- `replay.py --days N` loads what happened in the window from the end of the
  current date to the end of the date N days later.

### Alternatives considered

| Option | Why not |
|---|---|
| Load the CSVs once | Nothing ever changes, so incremental models, snapshots and freshness have nothing to show. |
| Generate synthetic data | Full control over change, but loses the real data and its real quality problems, which are part of what the project should demonstrate. |
| **Replay the real data** (chosen) | Real data, real quirks, and time under our control. The cost: the CSVs only hold final states, so the history in between must be rebuilt, using the rules below. |

### Day 0 is 2016-12-31

2016 has only 329 orders spread over three months (4 in September, 324 in
October, 1 in December). Replaying them day by day adds little, so reset loads
them as an initial backfill. Daily replay starts on 2017-01-01, from which
order volume grows steadily.

### When each table arrives

| Raw table | Arrives | Write mode |
|---|---|---|
| `sellers`, `products`, `product_category_name_translation`, `geolocation` | Once, at reset | replace |
| `orders` | At purchase, then again whenever a milestone passes (see below) | merge on `order_id` |
| `customers` | With their order | merge on `customer_id` |
| `order_items` | With their order | merge on `order_id`, `order_item_id` |
| `order_payments` | With their order | merge on `order_id`, `payment_sequential` |
| `order_reviews` | When the customer answers the review | merge on `review_id`, `order_id` |

- **Customers arrive with orders, not at reset.** Olist issues a new
  `customer_id` for every order (99,441 ids for 99,441 orders), so customer
  rows behave like order attributes. The person behind them is
  `customer_unique_id`.
- **Reviews arrive when they are answered**, because the score does not exist
  before then. 63 reviews are answered before their order's purchase time,
  which is a source data issue. Those arrive with their order instead, so a
  review never shows up before the order it belongs to.

### How order status is rebuilt

The CSV gives each order's final status plus four timestamps: purchase,
approval, carrier pickup and customer delivery. As of the simulated date, the
loader shows an order's status by checking these rules in order, and the first
one that applies wins:

1. Final status `canceled` or `unavailable`, and its last known timestamp has
   passed → that final status.
2. Delivered to the customer → `delivered`.
3. Handed to the carrier → `shipped`.
4. Final status `invoiced` or `processing`, and approved → that final status.
5. Approved → `approved`.
6. Otherwise → `created`.

Timestamps for milestones that have not happened yet are hidden, so nothing
leaks from the future. The estimated delivery date is always visible, because
the customer sees it at checkout.

Why each rule is shaped this way:

- **Furthest milestone wins.** Source timestamps are sometimes out of order:
  1,359 orders were handed to the carrier before approval, 166 before they
  were purchased, and 23 were delivered before shipping. Checking from
  `delivered` backwards means status never moves backwards in time. The raw
  timestamps are kept as they are; flagging them belongs in staging.
- **Canceled and unavailable orders switch at their last known timestamp.**
  The data has no cancellation timestamp, and the replay never invents one.
  - 141 canceled orders have only a purchase time, so they arrive already
    canceled.
  - The other 484 canceled orders, and all 609 unavailable ones, switch once
    their last recorded milestone passes.
- **`invoiced` and `processing` hold from approval onwards.** All 615 orders
  that end in these statuses were approved and never shipped, so they have no
  later milestone that could conflict.

## Idempotency

Re-running a day must not duplicate or change data:

- Every transactional table is merged on its primary key, so a replayed row
  overwrites itself.
- `state.json` is written only after a load succeeds. If a load fails, the next
  run replays the same window, which the merge keys make safe.
- `check_idempotency.py` proves it. It loads one day, fingerprints each table
  (row count, a checksum of all source columns, duplicate keys), rewinds the
  state, replays the same day and fails if anything changed.

All columns land in `raw` as text, and casting happens in dbt staging. Type
inference during loading would turn zip code prefixes like `01037` into
numbers and drop their leading zeros.

## Consequences

- **One state per order per day.** Each run collapses its window into one load,
  so a dbt snapshot sees at most one status per order per run. An order
  approved and shipped on the same day goes straight from `created` to
  `shipped`. Advancing several days at once collapses even more, so the
  snapshot demo should run `--days 1` followed by `dbt snapshot`.
- **8 orders never reach their final status.** They are `delivered` in the CSV
  but have no delivery date: 7 stay `shipped` and 1 stays `approved`. Past the
  end of the data, these 8 are the only differences between `raw.orders` and
  the CSV.
- **Some orders never show `approved`.** For all 609 unavailable orders, and
  for the 409 canceled orders whose last known timestamp is the approval, the
  approval is also the moment they switch to their final status. They go
  straight from `created` to `unavailable` or `canceled`.
- **Reference data never changes.** Sellers and products are static, so
  snapshots focus on orders.
- **Reset takes about 2.5 minutes**, almost all of it on the 1M geolocation
  rows passing through dlt as Python dicts. Adding `pyarrow` would cut this to
  seconds. It is not added yet, to avoid a new dependency for a one-off step.
- **The replay ends in October 2018.** The last source timestamp is a purchase
  on 2018-10-17. Advancing beyond that loads nothing new.

## Verification

- **Day-by-day run:** 45 single-day advances from day 0. No order's status
  moved backwards, and no timestamp after the simulated date appeared. Jumping
  past the end of the data then left all 99,441 orders matching the CSV,
  except the 8 orders above.
- **`check_idempotency.py` on 2018-02-05:** the day loaded 903 order rows (271
  new orders, 632 status updates), and the second run changed nothing.
- **Negative test:** with merges temporarily replaced by appends, the same
  check failed, with duplicate keys in every table.
