with

source as (
    select * from {{ source('olist', 'product_category_name_translation') }}
),

final as (
    select
        product_category_name,
        product_category_name_english,
        {{ dlt_loaded_at() }} as _loaded_at
    from source
)

select * from final
