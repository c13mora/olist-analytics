-- One row per order, every order: carrier and delivery dates exist only per
-- order, and keeping undelivered orders gives on-time rates the right
-- denominator. See docs/decisions/003.

with

orders as (
    select * from {{ ref('int_orders__joined_to_customers') }}
),

order_items as (
    select * from {{ ref('stg_olist__order_items') }}
),

-- 775 orders have no items (mostly unavailable or canceled), so this is
-- left-joined below.
order_item_summary as (
    select
        order_id,
        count(*) as item_count,
        count(distinct seller_id) as seller_count,
        sum(freight_value) as total_freight_value
    from order_items
    group by order_id
),

final as (
    select
        orders.order_id,
        orders.customer_unique_id,
        -- Where this order went, which can differ from the person's current
        -- location in dim_customers.
        orders.customer_zip_code_prefix,
        orders.customer_state,
        orders.order_status,
        orders.purchase_date,
        orders.purchased_at,
        orders.approved_at,
        orders.shipped_at,
        orders.delivered_at,
        orders.estimated_delivery_date,
        coalesce(order_item_summary.item_count, 0) as item_count,
        coalesce(order_item_summary.seller_count, 0) as seller_count,
        order_item_summary.total_freight_value,
        cast(orders.delivered_at as date) as delivery_date,

        -- Durations in calendar days. Null until the later milestone happens.
        {{ dbt.datediff('orders.purchased_at', 'orders.shipped_at', 'day') }}
            as days_to_carrier,
        {{ dbt.datediff('orders.shipped_at', 'orders.delivered_at', 'day') }}
            as days_in_transit,
        {{ dbt.datediff('orders.purchased_at', 'orders.delivered_at', 'day') }}
            as days_to_deliver,
        -- Positive when delivered after the promised date, negative when early.
        {{ dbt.datediff('orders.estimated_delivery_date', 'cast(orders.delivered_at as date)', 'day') }}
            as days_late_vs_estimate,

        -- Based on the delivery date, not the status: 6 canceled orders were
        -- still delivered. Delivered on the promised day counts as on time.
        case
            when orders.delivered_at is null then 'not_delivered'
            when cast(orders.delivered_at as date) > orders.estimated_delivery_date then 'late'
            else 'on_time'
        end as delivery_status,

        -- Source timestamps out of order (e.g. handed to the carrier before
        -- approval or even purchase). Kept, but flagged so SLA analysis can
        -- exclude them.
        coalesce(
            orders.shipped_at < orders.approved_at
            or orders.shipped_at < orders.purchased_at
            or orders.delivered_at < orders.shipped_at,
            false
        ) as has_timestamp_anomaly
    from orders
    left join order_item_summary
        on orders.order_id = order_item_summary.order_id
)

select * from final
