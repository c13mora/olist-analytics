with

source as (
    select * from {{ source('olist', 'sellers') }}
),

final as (
    select
        seller_id,
        seller_zip_code_prefix,
        seller_city,
        seller_state,
        {{ dlt_loaded_at() }} as _loaded_at
    from source
)

select * from final
