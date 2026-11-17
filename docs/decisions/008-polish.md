# 008 — Best-practice checks and final polish

- **Status:** Accepted
- **Date:** 2026-11-17
- **Code:** [`dbt/seeds/dbt_project_evaluator_exceptions.csv`](../../dbt/seeds/dbt_project_evaluator_exceptions.csv), [`dbt/dbt_project.yml`](../../dbt/dbt_project.yml), [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`README.md`](../../README.md)

## Context

Phase 7 closes the project. Two things remained: auditing the dbt project
against dbt Labs' best-practice rules, installed since Phase 0 but never run,
and presenting the project to the people it is for, who will read the README
before anything else.

## 1. dbt-project-evaluator: fix what has a point, document the rest

The package checks a project against 78 rules (naming, documentation, test
coverage, structure). On its first run, 73 passed and 5 warned. Each warning
was treated as either a fix or a documented exception.

**Fixed (two models had no tests at all):**

- **`int_orders__joined_to_customers`, ephemeral → view.** dbt cannot test
  ephemeral models, so its primary key was never tested, against the project
  rule that every primary key gets `unique` + `not_null`. It is now a view
  with those tests. This reverses the choice in [004](004-marts.md), which
  relied on the facts built on it to test its grain indirectly; a direct test
  is clearer and costs nothing.
- **`stg_olist__geolocation`** gets `not_null` tests on its key columns.

Test coverage is now 100% of models.

**Exceptions:** four rules the project breaks on purpose. Each is listed in an
exceptions seed with its reason and the decision record behind it:

| Rule | Where | Why it is deliberate |
|---|---|---|
| Sources without freshness | the four reference sources | Loaded once at reset ([002](002-sources-and-staging.md)). |
| Model fan-out | `int_orders__joined_to_customers` feeds four facts | A shared join is its purpose ([004](004-marts.md)). |
| Root model | `dim_date` | A generated date spine has no upstream model. |
| Missing primary key test | `stg_olist__geolocation` | One row per source point, duplicates included; the next model makes and tests one row per prefix ([002](002-sources-and-staging.md)). |

**Enforced in CI.** The package's checks only warn by default. Their severity
now comes from an environment variable: `warn` locally, `error` in CI. A
change that breaks a rule, or adds a violation without a documented
exception, fails its pull request.

| Alternative | Why not |
|---|---|
| Fix every warning | Would undo deliberate design choices, e.g. freshness checks on data that never changes. |
| Disable the rules | Loses the check for future changes; an exception list is explicit and reviewable. |
| Run the evaluator only locally | Rules decay unnoticed; CI makes them part of every change. |

## 2. A README for the people who will read it

The README was a setup guide that grew phase by phase. It now leads with what
a reviewer needs, in this order:

1. what the project is, with links to the live site
2. the problem it solves, and how it improves on its v1
   ([olist-dashboard](https://github.com/c13mora/olist-dashboard))
3. architecture and data model
4. key findings
5. what each practice demonstrates, linked to its decision record
6. how to run it, CI/CD, and next steps

**Diagrams as text, not screenshots.** The roadmap asked for a lineage
screenshot. The README instead uses Mermaid diagrams, which GitHub draws from
text: one for the architecture, and one for the model lineage, generated from
dbt's manifest. A link points to the interactive lineage graph in the live
dbt docs.

| Alternative | Why not |
|---|---|
| Screenshot of the dbt docs lineage graph | Unreadable at 31 nodes, and silently out of date after the next model change. |
| Only the link to the dbt docs | Readers who don't click through see no structure at all. |

The v1 project's README now links here, and both repositories are pinned on
the GitHub profile, so the "v1 → v2" story is visible from either side.

## Consequences

- **New code must respect the evaluator's rules.** Breaking one fails CI
  unless a reasoned exception is added to the seed.
- **The lineage diagram is a copy.** It was generated from the manifest once
  and must be regenerated when models are added or renamed; the dbt docs link
  is always current.
- **The README's numbers are a snapshot** of the dashboard's findings for
  January 2017 to August 2018, fixed by the export itself.

## Verification

- **Evaluator:** 78 of 78 checks pass, with no warnings, including with
  severity set to `error` as in CI. Removing one exception made the run fail,
  as it should.
- **Builds:** `dbt build -s olist` passes (160 checks, the known warning). The
  README's own command, `dbt build` with the evaluator, passes 237 checks.
- **The README's claims were checked:**
  - Model and test counts come from the manifest (20 models, 138 tests).
  - The lineage diagram matches the project's 31 nodes and 30 dependencies.
  - The key findings match the dashboard's verified figures.
  - The licence file is MIT.
- **On GitHub:** the v1 README links to this repository, and both are pinned
  on the profile.
