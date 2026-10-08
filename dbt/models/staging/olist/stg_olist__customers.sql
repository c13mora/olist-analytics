with

source as (
    select * from {{ source('olist', 'customers') }}
),

final as (
    select
        customer_id,
        customer_unique_id,
        customer_zip_code_prefix,
        customer_city,
        customer_state,
        {{ dlt_loaded_at() }} as _loaded_at
    from source
)

select * from final
