with

source as (
    select * from {{ source('olist', 'order_payments') }}
),

final as (
    select
        order_id,
        cast(payment_sequential as {{ dbt.type_int() }}) as payment_sequence,
        payment_type,
        cast(payment_installments as {{ dbt.type_int() }}) as payment_installments,
        cast(payment_value as {{ dbt.type_numeric() }}) as payment_value,
        {{ dlt_loaded_at() }} as _loaded_at
    from source
)

select * from final
