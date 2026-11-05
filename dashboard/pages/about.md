---
title: About
sidebar_position: 5
---

This dashboard is the reporting layer of an analytics engineering portfolio
project: the Olist dataset replayed day by day as if it were a live source,
loaded with dlt, modelled and tested with dbt, and published with Evidence.

- **Code and decision records:** [github.com/c13mora/olist-analytics](https://github.com/c13mora/olist-analytics)
- **dbt documentation** (models, columns, tests and lineage): [dbt docs](https://c13mora.github.io/olist-analytics/dbt-docs/)

## Data

All figures come from the
[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce),
about 100,000 anonymised orders placed on the Olist marketplace between 2016
and 2018, published by Olist under the
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
licence.

The pages read the project's dbt marts, which are derived from that dataset.
The browser downloads the marts it needs to run the pages' queries, so that
data is shared here under the same licence: non-commercial use, with
attribution, under the same terms. Only the columns the pages use are
published.
