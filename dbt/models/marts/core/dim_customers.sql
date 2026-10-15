-- One row per person (customer_unique_id), not per order: Olist issues a new
-- customer_id for every order. See docs/decisions/003.

with

customers as (
    select * from {{ ref('stg_olist__customers') }}
),

orders as (
    select * from {{ ref('stg_olist__orders') }}
),

geolocation as (
    select * from {{ ref('int_geolocation__grouped_by_zip') }}
),

customer_orders as (
    select
        customers.customer_unique_id,
        customers.customer_id,
        customers.customer_zip_code_prefix,
        customers.customer_city,
        customers.customer_state,
        orders.purchased_at
    from customers
    inner join orders
        on customers.customer_id = orders.customer_id
),

-- A person's location is the one on their most recent order. 250 people used
-- different zip codes on different orders.
latest_orders as (
    select
        *,
        row_number() over (
            partition by customer_unique_id
            order by purchased_at desc, customer_id desc
        ) as recency_rank
    from customer_orders
),

order_history as (
    select
        customer_unique_id,
        count(*) as order_count,
        min(purchased_at) as first_purchased_at,
        max(purchased_at) as last_purchased_at
    from customer_orders
    group by customer_unique_id
),

final as (
    select
        latest_orders.customer_unique_id,
        latest_orders.customer_zip_code_prefix,
        latest_orders.customer_city,
        latest_orders.customer_state,
        -- Null when the zip code prefix has no geolocation.
        geolocation.latitude as customer_latitude,
        geolocation.longitude as customer_longitude,
        order_history.first_purchased_at,
        order_history.last_purchased_at,
        order_history.order_count
    from latest_orders
    inner join order_history
        on latest_orders.customer_unique_id = order_history.customer_unique_id
    left join geolocation
        on latest_orders.customer_zip_code_prefix = geolocation.zip_code_prefix
    where latest_orders.recency_rank = 1
)

select * from final
