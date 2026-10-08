with

source as (
    select * from {{ source('olist', 'products') }}
),

final as (
    select
        product_id,
        -- Kept in Portuguese here. Staging does no joins, so the English
        -- translation is added downstream.
        product_category_name,
        -- The source misspells "length" as "lenght".
        cast(product_name_lenght as {{ dbt.type_int() }}) as product_name_length,
        cast(product_description_lenght as {{ dbt.type_int() }}) as product_description_length,
        cast(product_photos_qty as {{ dbt.type_int() }}) as product_photos_qty,
        cast(product_weight_g as {{ dbt.type_int() }}) as product_weight_g,
        cast(product_length_cm as {{ dbt.type_int() }}) as product_length_cm,
        cast(product_height_cm as {{ dbt.type_int() }}) as product_height_cm,
        cast(product_width_cm as {{ dbt.type_int() }}) as product_width_cm,
        {{ dlt_loaded_at() }} as _loaded_at
    from source
)

select * from final
