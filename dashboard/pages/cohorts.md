---
title: Customer cohorts
sidebar_position: 4
---

Do customers come back? Customers are grouped into cohorts by the month of
their first order, January 2017 to August 2018. A customer is one person
(`customer_unique_id`), not Olist's per-order `customer_id`. Definitions are
at the bottom of the page.

```sql customer_orders
-- Every order in the period, with the customer's first order date.
select
    customer_unique_id,
    order_id,
    purchase_date,
    min(purchase_date) over (partition by customer_unique_id) as first_purchase_date
from olist.fct_deliveries
where purchase_date between '2017-01-01' and '2018-08-31'
```

```sql customers
-- One row per customer: cohort, and the first order on a later day than the
-- first one (null if the customer never came back).
select
    customer_unique_id,
    min(first_purchase_date) as first_purchase_date,
    date_trunc('month', min(first_purchase_date)) as cohort_month,
    count(*) as orders,
    min(purchase_date) filter (where purchase_date > first_purchase_date) as return_date
from ${customer_orders}
group by customer_unique_id
```

```sql kpis
select
    count(*) as customers,
    avg(case when orders > 1 then 1.0 else 0 end) as multi_order_rate,
    avg(case when return_date is not null then 1.0 else 0 end) as returning_rate,
    avg(case when return_date <= first_purchase_date + interval 180 day then 1.0 else 0 end)
        filter (where first_purchase_date < '2018-03-01') as returning_180_day_rate,
    median(date_diff('day', first_purchase_date, return_date)) as median_days_to_return,
    (
        select sum(items.price) filter (where orders.purchase_date > orders.first_purchase_date)
            / sum(items.price)
        from olist.fct_order_items as items
        inner join ${customer_orders} as orders
            on items.order_id = orders.order_id
    ) as returning_revenue_share
from ${customers}
```

<BigValue data={kpis} value=customers title="Customers" fmt=num0 />
<BigValue data={kpis} value=returning_rate title="Came back on a later day" fmt=pct1 />
<BigValue data={kpis} value=returning_180_day_rate title="Came back within 180 days" fmt=pct1 />
<BigValue data={kpis} value=median_days_to_return title="Median days to come back" fmt=num0 />
<BigValue data={kpis} value=returning_revenue_share title="Revenue from returning orders" fmt=pct1 />

Olist is a marketplace of one-off buyers. Only 2.2% of customers ever placed
an order on a later day, and those orders bring in 2.2% of revenue. Counting
any second order, 3.1% have more than one, but 30% of second orders were
placed the same day as the first: a basket split into separate orders, not a
customer coming back.

## Growth came from new customers

```sql cohort_sizes
select
    cohort_month,
    count(*) as new_customers
from ${customers}
group by 1
order by 1
```

<BarChart
    data={cohort_sizes}
    x=cohort_month
    y=new_customers
    title="New customers by month of first order"
    yFmt=num0
/>

Monthly cohorts grew from 765 new customers in January 2017 to 6,000 to
7,000 a month in 2018, with the largest in November 2017 (Black Friday,
7,305). Almost all of the marketplace's growth was acquisition.

## Retention

```sql retention
-- Share of each cohort that ordered again (on a later day than the first
-- order) in each month after their first one.
with returns as (
    select distinct
        orders.customer_unique_id,
        date_trunc('month', orders.first_purchase_date) as cohort_month,
        date_diff(
            'month',
            date_trunc('month', orders.first_purchase_date),
            date_trunc('month', orders.purchase_date)
        ) as months_since_first_order
    from ${customer_orders} as orders
    where orders.purchase_date > orders.first_purchase_date
)

select
    strftime(sizes.cohort_month, '%Y-%m') as cohort,
    returns.months_since_first_order,
    count(distinct returns.customer_unique_id) / max(sizes.new_customers) as return_rate
from returns
inner join ${cohort_sizes} as sizes
    on returns.cohort_month = sizes.cohort_month
where returns.months_since_first_order between 1 and 12
group by 1, 2
order by 1, 2
```

<Heatmap
    data={retention}
    x=months_since_first_order
    y=cohort
    value=return_rate
    valueFmt=pct1
    title="Share of each cohort ordering again, by months since first order"
/>

In any month after their first order, at most 0.8% of a cohort orders again,
and usually far less. There is no month in which customers typically come
back: the few returns are thinly spread over the following year.

```sql return_by_cohort
-- Only cohorts with a full 180 days of data after their first order.
select
    cohort_month,
    avg(case when return_date <= first_purchase_date + interval 180 day then 1.0 else 0 end)
        as returning_180_day_rate
from ${customers}
where first_purchase_date < '2018-03-01'
group by 1
order by 1
```

<BarChart
    data={return_by_cohort}
    x=cohort_month
    y=returning_180_day_rate
    title="Customers who came back within 180 days, by cohort"
    yFmt=pct1
/>

The 180-day return rate stayed between 1.6% and 2.6% for every cohort: as
the marketplace grew, it did not get better at bringing customers back. For
a business like this, retention is the largest untapped lever.

## Definitions

| Metric | Definition |
|---|---|
| Customer | One person (`customer_unique_id`). |
| Cohort | The month of the customer's first order in the period. |
| Came back | Placed an order on a later calendar day than their first order. Same-day orders are treated as one basket. |
| Came back within 180 days | Came back within 180 days of the first order; only cohorts up to February 2018, which have 180 days of data. |
| Revenue from returning orders | Item revenue of orders placed after the customer's first order day, of all item revenue. |

Orders in any status count, as on the [executive overview](/). Customers
whose first order was before 2017 are counted from their first order in the
period.
