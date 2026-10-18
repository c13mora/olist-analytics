-- One row per payment, kept apart from items: joining the two would multiply
-- rows for orders with several of both. See docs/decisions/003.

with

payments as (
    select * from {{ ref('stg_olist__order_payments') }}
),

orders as (
    select * from {{ ref('int_orders__joined_to_customers') }}
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['payments.order_id', 'payments.payment_sequence']) }}
            as payment_key,
        payments.order_id,
        payments.payment_sequence,
        orders.customer_unique_id,
        orders.order_status,
        orders.purchase_date,
        payments.payment_type,
        payments.payment_installments,
        payments.payment_value
    from payments
    inner join orders
        on payments.order_id = orders.order_id
)

select * from final
