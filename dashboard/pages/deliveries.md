---
title: Delivery SLAs
sidebar_position: 3
---

How fast orders reach customers, how often Olist keeps its promised delivery
date, and what late deliveries do to reviews. Orders placed from January 2017
to August 2018. Definitions are at the bottom of the page.

```sql deliveries
-- Orders placed in the period. Durations leave out the orders whose source
-- timestamps are out of order (has_timestamp_anomaly).
select
    *,
    date_diff('day', purchase_date, estimated_delivery_date) as promised_days
from olist.fct_deliveries
where purchase_date between '2017-01-01' and '2018-08-31'
```

```sql kpis
select
    avg(case when delivery_status = 'on_time' then 1.0 else 0 end)
        filter (where delivery_status <> 'not_delivered') as on_time_rate,
    median(days_to_deliver) filter (where not has_timestamp_anomaly) as median_days_to_deliver,
    median(promised_days) as median_promised_days,
    -median(days_late_vs_estimate) filter (where not has_timestamp_anomaly) as median_days_early,
    median(days_to_carrier) filter (where not has_timestamp_anomaly) as median_days_to_carrier,
    median(days_in_transit) filter (where not has_timestamp_anomaly) as median_days_in_transit
from ${deliveries}
```

<BigValue data={kpis} value=on_time_rate title="On-time delivery" fmt=pct1 />
<BigValue data={kpis} value=median_days_to_deliver title="Median days to deliver" fmt=num0 />
<BigValue data={kpis} value=median_promised_days title="Median days promised" fmt=num0 />
<BigValue data={kpis} value=median_days_early title="Median days early" fmt=num0 />
<BigValue data={kpis} value=median_days_to_carrier title="Median days to the carrier" fmt=num0 />
<BigValue data={kpis} value=median_days_in_transit title="Median days in transit" fmt=num0 />

Olist promises generously: a typical order is promised in 24 days and arrives
in 10, twelve days early. Two of those days are spent before the carrier picks
it up, seven with the carrier.

## Over time

```sql monthly
select
    date_trunc('month', purchase_date) as month,
    avg(case when delivery_status = 'on_time' then 1.0 else 0 end)
        filter (where delivery_status <> 'not_delivered') as on_time_rate,
    median(days_to_deliver) filter (where not has_timestamp_anomaly) as median_days_to_deliver,
    median(promised_days) as median_promised_days
from ${deliveries}
group by 1
order by 1
```

<LineChart
    data={monthly}
    x=month
    y=on_time_rate
    title="On-time delivery by month of purchase"
    yFmt=pct0
/>

<LineChart
    data={monthly}
    x=month
    y={['median_days_to_deliver', 'median_promised_days']}
    title="Median days to deliver vs days promised"
    yFmt=num0
/>

On-time delivery dips when volume peaks: 87.6% for November 2017 orders
(Black Friday), then 85.9% in February and 81.0% in March 2018, the weakest
month. The last months look faster partly because the export ends in October
2018: slow orders from August 2018 had not been delivered yet.

## By region

```sql by_state
select
    customer_state as state,
    count(*) filter (where delivery_status <> 'not_delivered') as delivered_orders,
    median(days_to_deliver) filter (where not has_timestamp_anomaly) as median_days_to_deliver,
    median(promised_days) as median_promised_days,
    avg(case when delivery_status = 'on_time' then 1.0 else 0 end)
        filter (where delivery_status <> 'not_delivered') as on_time_rate
from ${deliveries}
group by 1
order by on_time_rate
```

<DataTable data={by_state} rows=27>
    <Column id=state title="Customer state" />
    <Column id=delivered_orders title="Delivered orders" fmt=num0 />
    <Column id=median_days_to_deliver title="Median days to deliver" fmt=num0 contentType=colorscale scaleColor=red />
    <Column id=median_promised_days title="Median days promised" fmt=num0 />
    <Column id=on_time_rate title="On-time delivery" fmt=pct1 contentType=colorscale scaleColor=green />
</DataTable>

Distance and lateness are different problems. The far north (Amazonas, Amapá,
Roraima) waits longest, about 25 days, but still gets 87% or more on time
because its promises are just as long. The weakest on-time rates are on the
Northeast coast: Alagoas 78.5%, Maranhão 82.5% and Sergipe 84.6%. São Paulo
gets its orders in a median of 7 days.

## Late deliveries cost reviews

```sql reviews_by_lateness
select
    case
        when deliveries.days_late_vs_estimate <= -8 then '1. 8+ days early'
        when deliveries.days_late_vs_estimate <= -1 then '2. 1-7 days early'
        when deliveries.days_late_vs_estimate = 0 then '3. On the promised day'
        when deliveries.days_late_vs_estimate <= 3 then '4. 1-3 days late'
        when deliveries.days_late_vs_estimate <= 7 then '5. 4-7 days late'
        else '6. 8+ days late'
    end as delivery_timing,
    count(*) as reviews,
    avg(reviews.review_score) as average_review_score
from ${deliveries} as deliveries
inner join olist.fct_reviews as reviews
    on deliveries.order_id = reviews.order_id
where
    deliveries.delivery_status <> 'not_delivered'
    and not deliveries.has_timestamp_anomaly
group by 1
order by 1
```

<BarChart
    data={reviews_by_lateness}
    x=delivery_timing
    y=average_review_score
    title="Average review score by delivery timing"
    yFmt=num2
    yMax=5
/>

Every day late costs stars. Orders arriving well ahead of the promise average
4.32; a delivery exactly on the promised day already drops to 4.03, one to
three days late to 3.29, and more than a week late to 1.70.

## Definitions

| Metric | Definition |
|---|---|
| On-time delivery | Delivered on or before the promised date, of delivered orders. |
| Days to deliver | Calendar days from purchase to delivery. |
| Days promised | Calendar days from purchase to the estimated delivery date shown at checkout. |
| Days early | Promised date minus delivery date; negative when late. |
| Days to the carrier / in transit | Purchase to carrier pickup / carrier pickup to delivery. |

Durations leave out the 1.4% of orders whose source timestamps are out of order
(for example, picked up before being approved). Orders not delivered yet are
counted in no rate here; cancellations are on the [executive overview](/).
