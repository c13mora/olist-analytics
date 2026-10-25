-- One row per order item: the finest grain for sales. Order attributes
-- (person, status, purchase date) repeat on each of the order's items, so
-- count orders with count(distinct order_id). See docs/decisions/003.
--
-- Incremental, as the largest fact. An item never changes after it arrives,
-- but its order's status does, so a run must pick up new items AND existing
-- items whose order changed. _loaded_at is the later of the item's and the
-- order's load time: the loader reloads an order whenever its status
-- changes, which moves _loaded_at forward for all its items.
-- - merge on order_item_key: inserts new items and updates the status of
--   existing ones (append would duplicate them).
-- - Load time, not business time: a business-time watermark would skip data
--   that arrives late; it only works here because the replay never does.
-- - Reloading a day reprocesses its items with identical values: harmless.
-- - A column change fails the build (on_schema_change='fail') until the
--   table is rebuilt on purpose with --full-refresh.

{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key='order_item_key',
        on_schema_change='fail'
    )
}}

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
        order_items.price + order_items.freight_value as total_item_value,
        greatest(order_items._loaded_at, orders._loaded_at) as _loaded_at
    from order_items
    inner join orders
        on order_items.order_id = orders.order_id
    {% if is_incremental() %}
        -- Only items that are new, or whose order was reloaded, since the
        -- newest row already in the table.
        where
            greatest(order_items._loaded_at, orders._loaded_at)
            > (select max(this_table._loaded_at) from {{ this }} as this_table)
    {% endif %}
)

select * from final
