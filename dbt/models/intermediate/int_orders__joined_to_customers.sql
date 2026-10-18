-- Orders with the person who placed them and the location the order went to.
-- Every fact needs customer_unique_id (the person), and Olist only links it to
-- orders through the per-order customer_id, so the join lives here once.
-- Ephemeral (the project default): a 1:1 join whose grain the facts test.

with

orders as (
    select * from {{ ref('stg_olist__orders') }}
),

customers as (
    select * from {{ ref('stg_olist__customers') }}
),

final as (
    select
        orders.order_id,
        orders.customer_id,
        customers.customer_unique_id,
        customers.customer_zip_code_prefix,
        customers.customer_state,
        orders.order_status,
        orders.purchased_at,
        orders.approved_at,
        orders.shipped_at,
        orders.delivered_at,
        orders.estimated_delivery_date,
        orders._loaded_at,
        cast(orders.purchased_at as date) as purchase_date
    from orders
    inner join customers
        on orders.customer_id = customers.customer_id
)

select * from final
