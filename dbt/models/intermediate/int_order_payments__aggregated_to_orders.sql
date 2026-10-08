-- A view rather than the ephemeral default, so its grain can be tested.
{{ config(materialized='view') }}

with

payments as (
    select * from {{ ref('stg_olist__order_payments') }}
),

-- 2,961 orders are paid in several payments, mostly a credit card plus
-- vouchers. The main payment type is the one that paid the most; ties go to
-- the earliest payment.
ranked_payments as (
    select
        *,
        row_number() over (
            partition by order_id
            order by payment_value desc, payment_sequence asc
        ) as value_rank
    from payments
),

final as (
    select
        order_id,
        count(*) as payment_count,
        sum(payment_value) as total_payment_value,
        sum(case when payment_type = 'voucher' then payment_value else 0 end) as voucher_payment_value,
        max(case when value_rank = 1 then payment_type end) as main_payment_type,
        max(payment_installments) as max_payment_installments
    from ranked_payments
    group by order_id
)

select * from final
