---
title: Seller performance
sidebar_position: 2
---

How revenue is spread across Olist's sellers, and whether they hand orders to
the carrier on time. January 2017 to August 2018, as on the
[executive overview](/). Definitions are at the bottom of the page.

```sql seller_totals
select
    seller_id,
    sum(price) as revenue,
    count(distinct order_id) as orders
from olist.fct_order_items
where purchase_date between '2017-01-01' and '2018-08-31'
group by seller_id
```

```sql shipping
-- One row per item that reached the carrier. Orders with out-of-order
-- source timestamps are left out (see has_timestamp_anomaly).
select
    items.seller_id,
    items.order_id,
    date_trunc('month', items.purchase_date) as month,
    deliveries.shipped_at > items.shipping_limit_at as is_late_to_carrier,
    deliveries.delivery_status
from olist.fct_order_items as items
inner join olist.fct_deliveries as deliveries
    on items.order_id = deliveries.order_id
where
    items.purchase_date between '2017-01-01' and '2018-08-31'
    and deliveries.shipped_at is not null
    and not deliveries.has_timestamp_anomaly
```

```sql kpis
with ranked as (
    select
        revenue,
        row_number() over (order by revenue desc) as revenue_rank,
        count(*) over () as seller_count,
        sum(revenue) over () as total_revenue
    from ${seller_totals}
)

select
    max(seller_count) as active_sellers,
    (select median(orders) from ${seller_totals}) as median_orders,
    sum(revenue) filter (where revenue_rank <= seller_count * 0.1) / max(total_revenue)
        as top_10_pct_share,
    (select avg(case when is_late_to_carrier then 1.0 else 0 end) from ${shipping}) as late_to_carrier_rate
from ranked
```

<BigValue data={kpis} value=active_sellers title="Active sellers" fmt=num0 />
<BigValue data={kpis} value=median_orders title="Median orders per seller" fmt=num0 />
<BigValue data={kpis} value=top_10_pct_share title="Revenue from top 10% of sellers" fmt=pct0 />
<BigValue data={kpis} value=late_to_carrier_rate title="Items late to the carrier" fmt=pct1 />

## A few sellers carry the marketplace

```sql concentration
with ranked as (
    select
        revenue,
        row_number() over (order by revenue desc) as revenue_rank,
        count(*) over () as seller_count,
        sum(revenue) over () as total_revenue
    from ${seller_totals}
),

cumulative as (
    select
        revenue_rank,
        ceil(100.0 * revenue_rank / seller_count) as seller_percentile,
        sum(revenue) over (order by revenue_rank) / total_revenue as cumulative_share
    from ranked
)

select
    seller_percentile,
    max(cumulative_share) as cumulative_share
from cumulative
group by seller_percentile
order by seller_percentile
```

<LineChart
    data={concentration}
    x=seller_percentile
    y=cumulative_share
    title="Share of revenue from the top X% of sellers"
    xAxisTitle="Top % of sellers, by revenue"
    yFmt=pct0
/>

The top 10% of sellers bring in two thirds of revenue, and the top 1% alone
a quarter. At the other end, 18% of active sellers sold a single order in
twenty months.

```sql sellers_by_state
select
    sellers.seller_state as state,
    count(distinct totals.seller_id) as sellers,
    sum(totals.revenue) as revenue
from ${seller_totals} as totals
inner join olist.dim_sellers as sellers
    on totals.seller_id = sellers.seller_id
group by 1
order by sellers desc
limit 10
```

<BarChart
    data={sellers_by_state}
    x=state
    y=sellers
    swapXY=true
    title="Active sellers by state (top 10)"
    yFmt=num0
/>

São Paulo hosts 60% of active sellers and 64% of revenue, while customers are
spread across the country (see the [executive overview](/)). 69% of revenue
ships across state lines, and even São Paulo sellers send 59% of theirs out
of the state.

## Shipping on time

Sellers commit to a deadline for handing each item to the carrier. Missing
it is the part of delivery a seller controls.

```sql late_by_month
select
    month,
    avg(case when is_late_to_carrier then 1.0 else 0 end) as late_to_carrier_rate
from ${shipping}
group by month
order by month
```

<LineChart
    data={late_by_month}
    x=month
    y=late_to_carrier_rate
    title="Items handed to the carrier after the seller's deadline"
    yFmt=pct0
/>

Late shipping rises with volume: 13% of items in November 2017 (Black Friday)
and February 2018, against about 7% in calmer months. It was highest while
the marketplace was ramping up in early 2017 (22% in January).

```sql impact
select
    case when is_late_to_carrier then 'Seller late to carrier' else 'Seller on time' end
        as seller_shipping,
    avg(case when delivery_status = 'on_time' then 1.0 else 0 end) as on_time_delivery_rate
from ${shipping}
where delivery_status <> 'not_delivered'
group by 1
order by 1 desc
```

<BarChart
    data={impact}
    x=seller_shipping
    y=on_time_delivery_rate
    title="Customer on-time delivery, by seller shipping"
    yFmt=pct0
/>

When the seller ships on time, 95% of items reach the customer by the promised
date; when the seller is late, only 79% do.

## Sellers

```sql seller_states
select distinct seller_state
from olist.dim_sellers
order by 1
```

<Dropdown data={seller_states} name=state value=seller_state title="Seller state" defaultValue="%">
    <DropdownOption valueLabel="All states" value="%" />
</Dropdown>

```sql seller_table
with reviews_by_seller as (
    -- A review is about an order, so every seller in the order gets it.
    select
        seller_orders.seller_id,
        avg(reviews.review_score) as average_review_score
    from (
        select distinct seller_id, order_id
        from olist.fct_order_items
        where purchase_date between '2017-01-01' and '2018-08-31'
    ) as seller_orders
    inner join olist.fct_reviews as reviews
        on seller_orders.order_id = reviews.order_id
    group by seller_orders.seller_id
),

shipping_by_seller as (
    select
        seller_id,
        avg(case when is_late_to_carrier then 1.0 else 0 end) as late_to_carrier_rate,
        avg(case when delivery_status = 'on_time' then 1.0 else 0 end)
            filter (where delivery_status <> 'not_delivered') as on_time_delivery_rate
    from ${shipping}
    group by seller_id
)

select
    sellers.seller_id,
    sellers.seller_state,
    sellers.seller_city,
    totals.revenue,
    totals.orders,
    shipping_by_seller.late_to_carrier_rate,
    shipping_by_seller.on_time_delivery_rate,
    reviews_by_seller.average_review_score
from ${seller_totals} as totals
inner join olist.dim_sellers as sellers
    on totals.seller_id = sellers.seller_id
left join shipping_by_seller
    on totals.seller_id = shipping_by_seller.seller_id
left join reviews_by_seller
    on totals.seller_id = reviews_by_seller.seller_id
where sellers.seller_state like '${inputs.state.value}'
order by totals.revenue desc
```

<DataTable data={seller_table} search=true rows=15>
    <Column id=seller_id title="Seller" />
    <Column id=seller_state title="State" />
    <Column id=seller_city title="City" />
    <Column id=revenue title="Revenue" fmt='"R$"#,##0' />
    <Column id=orders title="Orders" fmt=num0 />
    <Column id=late_to_carrier_rate title="Late to carrier" fmt=pct1 />
    <Column id=on_time_delivery_rate title="Customer on time" fmt=pct1 />
    <Column id=average_review_score title="Avg. review" fmt=num2 />
</DataTable>

## Definitions

| Metric | Definition |
|---|---|
| Active sellers | Sellers with at least one item sold in the period. |
| Revenue | Sum of item prices, excluding freight. |
| Late to the carrier | Items whose order reached the carrier after the item's shipping deadline, of items that reached the carrier. |
| Customer on-time delivery | Delivered on or before the promised date, of delivered items. |
| Avg. review | Mean review score (1 to 5) of the seller's orders. |

Carrier pickup, delivery and reviews are recorded once per order. In the 1%
of orders with several sellers, every seller in the order gets the order's
dates and reviews. Orders with out-of-order source timestamps are left out
of the shipping figures.
