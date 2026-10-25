# Demo: incremental models and snapshots

The Olist data is a static export, so the project replays it one day at a time
to behave like a live source (see [decision record 001](decisions/001-replay-loader.md)).
This demo uses that to show the two dbt features that only make sense when
data changes:

- **An incremental model.** `fct_order_items` processes only what changed
  since its last run, instead of rebuilding the whole table.
- **A snapshot.** `snap_orders` keeps every version of every order's status
  (SCD Type 2), so the history survives even though `raw` only holds the
  latest state.

## Run it

From the repo root:

```bash
uv run python scripts/demo.py --reset --days 7   # clean start, then 7 days one by one
uv run python scripts/demo.py --days 3           # continue from the current date
```

With `--reset`, the script:

1. resets the replay, which also drops the snapshot and the incremental table
   so no history "from the future" survives;
2. loads everything up to 2017-01-31 in one go, so the daily part starts with
   steady order volume;
3. builds and tests every model, which also takes the first snapshot.

Then, for each day, it runs the replay for one day and a daily dbt run: every
model (the incremental one incrementally) and the snapshot. At the end it runs
every test. A clean run takes about 6 minutes, mostly the reset. The replay is
deterministic, so the numbers below come out the same every time.

## The output

```
Replaying 7 days one at a time, starting after 2017-01-31:

day           new orders  status updates  fact rows processed  fact rows total  snapshot versions added
2017-02-01            73              86                  187            1,395                      159
2017-02-02            69             119                  221            1,470                      188
2017-02-03            60             132                  212            1,532                      192
2017-02-04            67              24                   99            1,604                       91
2017-02-05            75               5                   88            1,687                       80
2017-02-06            85             155                  270            1,775                      240
2017-02-07           112             203                  351            1,902                      315

Running every test on the result...
All tests pass (one expected warning: orders whose payments differ from items).

Status history of order 5f6b520cff06f23c77386b75976256e9 (4 versions in snap_orders):
  created      from 2017-01-31 11:58  to 2017-02-01 02:55
  approved     from 2017-02-01 02:55  to 2017-02-02 10:52
  shipped      from 2017-02-02 10:52  to 2017-02-07 17:27
  delivered    from 2017-02-07 17:27  to now (current version)

Time orders spent in each status (completed versions only):
  status        versions   median days
  created            144           1.2
  approved           350           1.9
  shipped            230           6.7
```

## What it shows

### Each day's columns

| Column | Meaning |
|---|---|
| new orders | Orders placed that day. |
| status updates | Existing orders that reached a new milestone that day (approved, shipped, delivered…), so the loader reloaded them. |
| fact rows processed | Rows the incremental `fct_order_items` run handled: the new orders' items plus the items of updated orders. |
| fact rows total | Size of `fct_order_items` after the run. |
| snapshot versions added | New rows in `snap_orders`. |

### The incremental model only touches what changed

On 2017-02-07, the run processed 351 rows out of 1,902: the 112 new orders'
items, plus the items of the 203 orders whose status changed. Every other row
was left alone. The share shrinks as the table grows: by the end of the data
the table holds 112,650 items, while a typical day touches about 500 of them
and the busiest (Black Friday, 2017-11-24) about 2,000.

Updated rows matter as much as new ones. An item never changes after it
arrives, but its order's status does, and that status is repeated on the item
row. That is why the model tracks when the *order* was last reloaded, not just
the item ([`fct_order_items.sql`](../dbt/models/marts/sales/fct_order_items.sql)).

### The snapshot records one version per change

Each day, snapshot versions added = new orders + status updates
(73 + 86 = 159 on 2017-02-01, and likewise every day). Every order the loader
delivers is either new or has a new status, and the snapshot records exactly
that, nothing more. Reloading a day adds nothing, because versions are keyed
on the order's latest milestone, not on load time.

### History is in business time

The example order was created on Jan 31, approved the next day, shipped on
Feb 2 and delivered on Feb 7. Those are the times the events happened in the
source, not when the demo ran. That is what makes durations meaningful: this
order spent five days with the carrier.

### Weekends are visible

Feb 4 and 5, 2017 were a Saturday and a Sunday. Orders kept coming in (67 and
75), but status updates dropped to 24 and 5: approvals, pickups and deliveries
mostly wait for Monday, when updates jump back to 155.

### What snapshots make possible

Across the orders whose status changed during the demo, an order spent a
median of 1.2 days waiting for approval, 1.9 days approved before the carrier
picked it up, and 6.7 days with the carrier. `raw.orders` cannot answer this,
because it only keeps the latest status.

These medians cover only versions that ended within the demo's days. Orders
that stay longer in a status are not counted yet, so a longer replay gives
larger, more representative figures.

## Under the hood

- [Decision record 001](decisions/001-replay-loader.md): how the replay works
  and how order status is rebuilt.
- [`snap_orders.yml`](../dbt/snapshots/snap_orders.yml): the snapshot, with the
  timestamp strategy on `status_updated_at`.
- [`fct_order_items.sql`](../dbt/models/marts/sales/fct_order_items.sql): the
  incremental model and why it merges on load time.
- [`scripts/demo.py`](../scripts/demo.py): the demo itself.
