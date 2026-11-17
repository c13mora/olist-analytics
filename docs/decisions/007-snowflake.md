# 007 — Running the project on Snowflake

- **Status:** Accepted
- **Date:** 2026-11-17
- **Code:** [`snowflake/setup.sql`](../../snowflake/setup.sql), [`ingestion/replay.py`](../../ingestion/replay.py), [`dbt/profiles.yml`](../../dbt/profiles.yml), [`stg_olist__geolocation.sql`](../../dbt/models/staging/olist/stg_olist__geolocation.sql)
- **Evidence:** [`docs/snowflake/`](../snowflake/)

## Context

Snowflake is the project's secondary target: the same pipeline should run on
it unchanged, during a 30-day trial started for this phase. Earlier records
left a list of pieces never tested there: the load-time macro
([002](002-sources-and-staging.md)), `median()` and `mode()`, day-of-week
numbering ([004](004-marts.md)), and the snapshot and incremental merge
([005](005-incremental-and-snapshots.md)).

## 1. Same loader, different destination

The replay loader gained a `--destination snowflake` option. dlt loads the
same `raw` tables into Snowflake that it loads into DuckDB.

- **Separate state per destination.** Snowflake has its own simulated date
  (`state_snowflake.json`) and its own dlt pipeline state, so a Snowflake run
  never moves the local DuckDB replay.
- **Identifier case.** dlt writes Snowflake names in upper case (`ORDER_ID`),
  which is what dbt's unquoted lower-case names resolve to; no model changed.
- **New dependency:** dlt's `snowflake` extra. The Snowflake driver already
  came with dbt, so it added nothing to install.

| Alternative | Why not |
|---|---|
| Copy the DuckDB `raw` tables to Snowflake once | Simpler, but the loader would never run against Snowflake, which is the point of a second target. |

## 2. Key-pair sign-in for a service user

dbt and dlt sign in as `OLIST_SERVICE`, a user of type `SERVICE`, with a key
pair instead of a password. Snowflake is phasing out password-only sign-in and
recommends key pairs for tools.

- **The private key stays on the developer's computer.** Its path, and the
  account identifier, are read from two environment variables
  (`SNOWFLAKE_PRIVATE_KEY_PATH`, `SNOWFLAKE_ACCOUNT`). dbt's `snowflake`
  target and the loader both use them, so the public repo holds no secrets.
- **Trade-off:** the key has no passphrase, to keep setup simple. Anyone with
  access to the user's home folder could use it; an encrypted key would only
  need one more variable for the passphrase.

| Alternative | Why not |
|---|---|
| Password in an environment variable | Being phased out for this use; weaker than a key. |

## 3. Two roles, least privilege

| Role | Used by | Can |
|---|---|---|
| `LOADER` | dlt | Create and write the raw schemas (`RAW`, and `RAW_STAGING` for merges). |
| `TRANSFORMER` | dbt | Read raw, and create and build its own schemas (`DBT_DEV_*`). |

- **A misbehaving tool cannot damage the other's data.** dbt cannot modify raw
  data, and the loader cannot touch dbt's schemas.
- **Database-level future grants.** `TRANSFORMER` may read any schema and table
  created later in the database. Schema-level grants would be lost every time
  `--reset` drops and recreates the raw schemas.
- **Both roles roll up to `SYSADMIN`,** so administrators can see their objects.

**Consequence of least privilege:** on Snowflake, `--reset` cannot drop dbt's
snapshot and incremental fact, which belong to `TRANSFORMER`. The loader prints
a note, and the README documents the manual step.

| Alternative | Why not |
|---|---|
| One role for both tools | Simpler, but any mistake in either tool could damage all data. |
| Let `LOADER` also drop dbt's tables | Would undo the separation for a step that runs rarely. |

## 4. Cost controls

- **One extra-small warehouse,** `OLIST_WH`, for both roles. It suspends after
  60 idle seconds and resumes on the next query, so it costs nothing while idle.
  Separate warehouses per role would cost the same and add setup.
- **A resource monitor** caps the warehouse at 10 credits a month. It
  notifies at 80%, and suspends the warehouse at 100%.
- **Result:** the whole phase used 0.3 credits, about $1 of the trial's $400.

## 5. Manual runs, no CI

The trial expires after 30 days, after which any CI job against Snowflake
would fail. The run is documented instead: query history, credits used and
the final build log in [`docs/snowflake/`](../snowflake/). CI keeps testing
every change on DuckDB.

## 6. Proving equivalence, not just a passing build

A green build only shows that queries run. The two warehouses were compared
directly:

- **The untested pieces:**
  - The load-time macro returns UTC timestamps (`TIMESTAMP_NTZ`).
  - Day-of-week numbering is correct (Snowflake's `WEEK_START` is 0, the
    default).
  - Every snapshot version is dated by business time.
- **Every mart and intermediate table,** with the full data loaded in both:
  row counts and the sums of their measures.

**The comparison found a bug in the DuckDB build.** `dbt.type_float()` renders
`FLOAT`, which is 64-bit on Snowflake but **32-bit on DuckDB**, so DuckDB had
rounded coordinates to about 7 digits.

- **Effect:** points that differed only past that precision merged, changing
  the point counts of 291 zip prefixes and moving medians by up to about
  600 m. The dashboard never used these coordinates.
- **Fix:** coordinates are cast to `double`, 64-bit on both warehouses.

`double` is standard SQL on both, so no macro was needed. The project's rule
of isolating dialect differences in macros applies when the SQL itself has to
differ, and here it did not.

## Consequences

- **The Snowflake target stops working when the trial ends.** The
  documentation in `docs/snowflake/` remains, and the README has clean-up
  commands. Running again needs a new account and the same setup script.
- **Results depend on one Snowflake setting.** Day-of-week numbering assumes
  `WEEK_START = 0`, the default ([004](004-marts.md)).
- **The earlier "untested on Snowflake" notes are resolved.** Records 002–005
  listed them as consequences; all of them now behave the same on both
  warehouses.
- **The dashboard stays on DuckDB.** It reads the local file and the deployed
  site is built in CI, so Snowflake only concerns the dbt project.
- **Type macros are not automatically portable.** `dbt.type_float()` meant
  different precision on each warehouse. Comparing the warehouses' results,
  not just running the build, is what caught it.

## Verification

- `dbt debug --target snowflake`: connection OK, as `TRANSFORMER`.
- **Loading:** the replay reset loaded into Snowflake in 1.5 minutes, with the
  same row counts as DuckDB.
- **At 2017-03-31:** `dbt build` gave 152 passes and the known warning, which
  reported 26 mismatched orders, as on DuckDB at the same date.
- **One more day:** the incremental model merged 69 rows, the snapshot added
  95 versions (one per order delivered that day), and freshness passed.
- **Full data:** all ten mart and intermediate tables matched DuckDB exactly
  after the `double` fix.
- **Final run** ([log](../snowflake/dbt-build-output.txt)): `dbt build` passed;
  freshness was stale on all sources six days after the last load, as it
  should be.
- **Cost:** 0.3 credits for the phase ([screenshot](../snowflake/cost-credits.png)).
