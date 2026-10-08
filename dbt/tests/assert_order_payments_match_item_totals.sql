-- Orders whose total paid differs from items + freight by more than 1 BRL.
--
-- A known source issue, not a pipeline bug: about 249 orders differ, mostly
-- single credit-card payments where the gap is likely installment interest.
-- The test only warns, so the issue stays visible without failing builds.
-- Orders with no items (mostly unavailable or canceled) or no payments are
-- out of scope.
{{ config(severity='warn') }}

with

payments as (
    select * from {{ ref('int_order_payments__aggregated_to_orders') }}
),

item_totals as (
    select
        order_id,
        sum(price + freight_value) as item_total
    from {{ ref('stg_olist__order_items') }}
    group by order_id
),

final as (
    select
        payments.order_id,
        payments.total_payment_value,
        item_totals.item_total,
        payments.total_payment_value - item_totals.item_total as difference
    from payments
    inner join item_totals on payments.order_id = item_totals.order_id
    where abs(payments.total_payment_value - item_totals.item_total) > 1
)

select * from final
