---
title: Executive overview
---

The Olist marketplace from **January 2017 to August 2018**, the period with
orders on every day. The export holds only a handful of orders before and
after, so those months are left out. Definitions are at the bottom of the page.

```sql kpis
with items as (
    select
        sum(price) as revenue,
        sum(freight_value) as freight,
        count(distinct order_id) as orders_with_items
    from olist.fct_order_items
    where purchase_date between '2017-01-01' and '2018-08-31'
),

orders as (
    select
        count(*) as orders,
        count(distinct customer_unique_id) as customers,
        1.0 * count(*) filter (where delivery_status = 'on_time')
            / count(*) filter (where delivery_status <> 'not_delivered') as on_time_rate,
        1.0 * count(*) filter (where order_status in ('canceled', 'unavailable'))
            / count(*) as cancellation_rate
    from olist.fct_deliveries
    where purchase_date between '2017-01-01' and '2018-08-31'
)

select
    items.revenue,
    items.freight,
    orders.orders,
    orders.customers,
    items.revenue / items.orders_with_items as average_order_value,
    orders.on_time_rate,
    orders.cancellation_rate
from items
cross join orders
```

<BigValue data={kpis} value=revenue title="Revenue (GMV)" fmt='"R$"#,##0.0,,"M"' />
<BigValue data={kpis} value=orders title="Orders" fmt=num0 />
<BigValue data={kpis} value=customers title="Customers" fmt=num0 />
<BigValue data={kpis} value=average_order_value title="Average order value" fmt='"R$"#,##0' />
<BigValue data={kpis} value=on_time_rate title="On-time delivery" fmt=pct1 />
<BigValue data={kpis} value=cancellation_rate title="Canceled or unavailable" fmt=pct1 />

## Growth

```sql monthly
select
    date_trunc('month', purchase_date) as month,
    sum(price) as revenue,
    count(distinct order_id) as orders
from olist.fct_order_items
where purchase_date between '2017-01-01' and '2018-08-31'
group by 1
order by 1
```

<BarChart
    data={monthly}
    x=month
    y=revenue
    title="Revenue by month"
    yFmt='"R$"#,##0,"k"'
/>

<LineChart
    data={monthly}
    x=month
    y=orders
    title="Orders by month"
    yFmt=num0
/>

Revenue grew from about R$120k in January 2017 to R$1.01M in November 2017,
the highest month in the data (Black Friday), then held between R$0.84M and
R$1.0M a month through 2018.

## Where revenue comes from

```sql top_categories
select
    products.product_category_name_english as category,
    sum(items.price) as revenue
from olist.fct_order_items as items
inner join olist.dim_products as products
    on items.product_id = products.product_id
where items.purchase_date between '2017-01-01' and '2018-08-31'
group by 1
order by revenue desc
limit 10
```

<BarChart
    data={top_categories}
    x=category
    y=revenue
    swapXY=true
    title="Top 10 categories by revenue"
    yFmt='"R$"#,##0,"k"'
/>

Health & beauty, watches & gifts, and bed, bath & table lead, each above
R$1M over the period.

```sql top_states
select
    deliveries.customer_state as state,
    sum(items.price) as revenue
from olist.fct_order_items as items
inner join olist.fct_deliveries as deliveries
    on items.order_id = deliveries.order_id
where items.purchase_date between '2017-01-01' and '2018-08-31'
group by 1
order by revenue desc
limit 10
```

<BarChart
    data={top_states}
    x=state
    y=revenue
    swapXY=true
    title="Top 10 customer states by revenue"
    yFmt='"R$"#,##0,"k"'
/>

São Paulo alone accounts for 38% of revenue, more than Rio de Janeiro (13%)
and Minas Gerais (12%) combined.

```sql payment_mix
select
    payment_type,
    sum(payment_value) as amount_paid
from olist.fct_payments
where purchase_date between '2017-01-01' and '2018-08-31'
group by 1
order by amount_paid desc
```

<BarChart
    data={payment_mix}
    x=payment_type
    y=amount_paid
    swapXY=true
    title="Amount paid by payment type"
    yFmt='"R$"#,##0,"k"'
/>

Credit cards carry 78% of the amount paid and boleto (Brazilian bank slip)
18%; vouchers and debit cards make up the rest.

## Definitions

| Metric | Definition |
|---|---|
| Revenue (GMV) | Sum of item prices, excluding freight. |
| Orders | Distinct orders placed in the period, in any status. |
| Customers | Distinct people (`customer_unique_id`), not Olist's per-order `customer_id`. |
| Average order value | Revenue ÷ orders that have at least one item. |
| On-time delivery | Orders delivered on or before the promised date ÷ delivered orders. |
| Canceled or unavailable | Orders that ended canceled or unavailable ÷ all orders. |

Payments include freight and installment interest, so the amount paid is
higher than revenue. All figures come from the dbt marts; see the
[decision records](https://github.com/c13mora/olist-analytics/tree/main/docs/decisions)
for how they are built.
