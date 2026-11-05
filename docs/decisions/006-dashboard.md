# 006 — The Evidence dashboard and its publication

- **Status:** Accepted
- **Date:** 2026-11-05
- **Code:** [`dashboard/`](../../dashboard/), [`scripts/check_dashboard_queries.py`](../../scripts/check_dashboard_queries.py), [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml), [`fct_reviews.sql`](../../dbt/models/marts/sales/fct_reviews.sql)

## Context

Phase 5 puts a reporting layer on the marts built in Phases 3 and 4
([003](003-fact-and-dimension-grains.md), [004](004-marts.md)): four dashboard
pages, published as a website together with the dbt docs. Two project goals
shape every choice: anyone can run the project locally for free, and the site
is static and hosted on GitHub Pages.

## 1. Classic, open-source Evidence (40.x)

Evidence's official template now targets **Evidence Studio**: a separate CLI,
new Markdoc-style syntax and ClickHouse SQL, hosting on Evidence's platform or
as a self-hosted Docker server. Its docs say local development needs an
Evidence account.

- **Decision:** classic Evidence 40.x (`@evidence-dev/evidence`), from the
  template's `legacy` branch. It builds a static site with `npm run build`,
  runs locally without an account, and deploys to GitHub Pages.
- **Setup:** trimmed to the DuckDB connector (from twelve), with exact
  version pins and a committed `package-lock.json`.

| Alternative | Why not |
|---|---|
| New Evidence (Studio CLI) | Needs an account for local development and a running server instead of static hosting, breaking both project goals. |
| Observable Framework | Also static and free, but more JavaScript-heavy, and Evidence was already the chosen stack. |

**Trade-off:** classic Evidence is now the legacy line, with docs at
`legacy-docs.evidence.dev`. A static site keeps working when a package stops
being updated, but dependencies age (section 7).

## 2. Node 22, installed the standard way

The uv environment holds Python packages only. Node's packages live in
`dashboard/node_modules`, locked by `package-lock.json`; only the Node runtime
is shared, as Python itself was before uv managed interpreters.

- **Decision:** Node 22 LTS installed system-wide, pinned for everyone in
  `.nvmrc`, which CI reads, and in the `engines` field of `package.json`.

| Alternative | Why not |
|---|---|
| Node inside the uv environment (`nodejs-wheel`) | Unconventional; Evidence's docs and community don't use it, and CI installs Node the standard way anyway. |
| A Node version manager (fnm) | The right choice if other projects needed another Node version; none did. |

## 3. What the dashboard reads

- **Marts only**, never staging or raw. That is what the marts are for.
- **The full dataset.** The deployed site replays to the end of the data in
  one go. Charts cover January 2017 to August 2018, when there were orders
  every day; the export has only a handful of orders outside that window.
- **No snapshot data.** Replaying in one jump leaves no day-by-day status
  history, so status timings come from the milestone durations in
  `fct_deliveries`.
- **A new mart, `fct_reviews`.** Reviews stopped at staging, so no page could
  show review scores. One row per review (`review_id`, `order_id`), tested like
  the other facts. It produced the clearest finding of the dashboard: the
  average review falls from 4.32 to 1.70 as deliveries go from well early to
  over a week late.

## 4. Choices behind the numbers

Each page states its definitions, and every sentence on a page was checked
against the data before it was written.

- **A returning customer orders on a later day.** 3.1% of customers have
  several orders, but 30% of second orders were placed the same day as the
  first: a basket split into separate orders. Counting them would overstate
  retention by half.
- **Late to the carrier** compares the seller's shipping deadline with carrier
  pickup: the part of delivery a seller controls. When sellers ship on time,
  95% of deliveries arrive on time; when they are late, 79%.
- **Orders with several sellers** (1.3%) share their delivery dates and reviews
  across all their sellers, because the source records them per order.
- **Out-of-order timestamps** (1.4% of orders) are left out of duration
  figures, using the flag from [004](004-marts.md).
- **Incomplete recent data is said so.** The last months look faster because
  slow orders were not delivered yet when the export ends, and 180-day return
  rates only cover cohorts that have 180 days of data.

## 5. Checking the pages

**`build:strict` does not fail on broken SQL.** A failing query only prints
`Error in Query!`, and the build reports success. Many queries also only run
in the browser: those built on other queries, and those using filters.

- **Decision:** two checks, both run in CI before anything is published:
  - The build output is searched for `Error in Query`, and the job fails if it
    appears.
  - `scripts/check_dashboard_queries.py` runs every query of every page in
    order, like the browser, with filters set to "all", and fails on any
    error or empty result.
- **Run on the browser's copy of the data.** The checker reads Evidence's own
  data cache, not the dbt tables. Evidence stores dates as timestamps, so
  `date + 180` failed in the browser while working on the original tables. A
  first version of the checker missed exactly that bug.

## 6. Publishing to GitHub Pages

**`deploy.yml` builds and publishes.** It replays the full dataset, runs
`dbt build` (every test must pass), generates the dbt docs as one static page,
builds the dashboard, runs both checks, and publishes the dashboard with the
docs under `/dbt-docs/`. Pull requests only build and check; pushes to `main`
publish.

- **Base path.** The site lives at `/olist-analytics/`. Evidence's
  `deployment.basePath` adds that prefix to every site-relative link.
- **The data is public.** The browser downloads the mart data to run the
  queries, so visitors can download it.
  - The Olist dataset is CC BY-NC-SA 4.0, which allows sharing adapted data
    non-commercially, with attribution, under the same licence. An About page
    gives the attribution and licence.
  - Only the columns the pages use are published. Two dimensions no page
    reads are not published at all.
- **Size.** Evidence saves every named query's result with the site, and four
  row-level intermediate queries added about 16 MB each. Moving them into the
  queries that use them, as CTEs, cut the site from 204 MB to 99 MB with
  identical figures. Most of the rest is the browser's DuckDB engine (71 MB,
  of which each visitor downloads one 33–38 MB file).

| Alternative | Why not |
|---|---|
| Publish pre-aggregated data only | Would need a reporting model per chart in dbt, and the seller table would lose its search and filter. |
| Keep the intermediate queries named | Simpler pages, but 16 MB downloads per page and row-level data republished. |

## 7. Pin what other people release

Twice in this phase, a release by someone else broke the build without any
change on our side:

- **TypeScript 7** came out after classic Evidence's last update, and one of
  Evidence's dependencies only accepts TypeScript 4 or 5. An `overrides` entry
  pins TypeScript 5.9.3.
- **`python-dateutil` 4.0.0** (2026-11-01) stopped installing `six`, which the
  Kaggle CLI uses without declaring it. CI could no longer download the
  dataset. The workflows and README now pin `kaggle==2.2.5` and add `six`
  explicitly.

The rule since: exact versions for tools used in CI, and every open range
treated as a risk.

## Consequences

- **The dashboard depends on legacy Evidence.** Future dependency conflicts
  are likely; the overrides in `package.json` are where they get fixed.
- **Queries repeat their first steps.** A CTE shared by several queries on a
  page is written in each of them, in exchange for a smaller, faster site.
- **Hard-coded periods.** Pages filter January 2017 to August 2018, matching
  the source's active period. Different data would need new bounds.
- **The site is only as fresh as `main`.** It is rebuilt on every push to
  `main`, from the full replay, not on a schedule.
- **Local preview moved** to `http://localhost:3000/olist-analytics`, because
  of the base path.
- **The dashboard reads DuckDB.** The Snowflake run (Phase 6) concerns dbt;
  the dashboard stays on the local DuckDB file.

## Verification

- **Queries:** every query of all five pages runs against Evidence's data
  with the checker. A deliberately broken page made it fail, naming the page,
  query and column.
- **Figures:** every figure in the page texts was recomputed from the marts.
  Unverified or imprecise sentences were corrected, e.g. "1%" became "1.4%",
  and an unchecked claim about vouchers was removed.
- **The assembled site, served locally under `/olist-analytics/`:** every
  page, data file, DuckDB engine file and the dbt docs loaded, and links
  between pages carried the prefix.
- **CI on the pull request:** both workflows passed, including a fresh Kaggle
  download. The deploy build ran 152 dbt nodes plus the known warning, loaded
  all six tables with dbt's row counts, found no query errors, and passed the
  checker. Publishing runs on the merge into `main`.
