-- One row per order item: the finest grain for sales. Order attributes
-- (person, status, purchase date) repeat on each of the order's items, so
-- count orders with count(distinct order_id). See docs/decisions/003.

with

order_items as (
    select * from {{ ref('stg_olist__order_items') }}
),

orders as (
    select * from {{ ref('int_orders__joined_to_customers') }}
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['order_items.order_id', 'order_items.item_sequence']) }}
            as order_item_key,
        order_items.order_id,
        order_items.item_sequence,
        orders.customer_unique_id,
        order_items.product_id,
        order_items.seller_id,
        orders.order_status,
        orders.purchase_date,
        orders.purchased_at,
        order_items.shipping_limit_at,
        order_items.price,
        order_items.freight_value,
        order_items.price + order_items.freight_value as total_item_value
    from order_items
    inner join orders
        on order_items.order_id = orders.order_id
)

select * from final
