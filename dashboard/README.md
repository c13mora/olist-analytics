# Olist dashboard

An [Evidence](https://legacy-docs.evidence.dev) site built on the project's dbt
marts. It uses classic, open-source Evidence (`@evidence-dev/evidence` 40.x),
which builds a static site that runs locally without an account and deploys to
GitHub Pages.

## Run it locally

Needs Node 22 (see `.nvmrc` at the repo root) and a built DuckDB file: run the
replay and `dbt build` first (see the main README). The dashboard is meant for
the full dataset, so replay to the end of the data.

```bash
cd dashboard
npm install
npm run sources   # read the marts from data/olist.duckdb
npm run dev       # local preview at http://localhost:3000/olist-analytics
```

Then check every page's queries the way the browser runs them (the build
alone does not fail on broken SQL):

```bash
cd ..
uv run python scripts/check_dashboard_queries.py
```

The site is published to GitHub Pages by `.github/workflows/deploy.yml`,
together with the dbt docs, under the `/olist-analytics` base path set in
`evidence.config.yaml`.

## How it is organised

- `sources/olist/`: one query per mart table, read from `../data/olist.duckdb`.
  The dashboard reads marts only, never staging or raw, and only the columns
  the pages use: visitors can download the site's data.
- `pages/`: one Markdown page per topic, with SQL and chart components.

## Notes

- `package.json` pins TypeScript 5 through `overrides`. Classic Evidence's
  dependencies only accept TypeScript 4 or 5, but npm would otherwise pick
  TypeScript 7, released after Evidence's last update.
