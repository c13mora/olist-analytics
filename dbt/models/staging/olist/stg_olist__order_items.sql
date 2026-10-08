with

source as (
    select * from {{ source('olist', 'order_items') }}
),

final as (
    select
        order_id,
        -- Renamed from order_item_id: it is the item's position within the
        -- order (1, 2, 3...), not an identifier.
        cast(order_item_id as {{ dbt.type_int() }}) as item_sequence,
        product_id,
        seller_id,
        cast(shipping_limit_date as {{ dbt.type_timestamp() }}) as shipping_limit_at,
        cast(price as {{ dbt.type_numeric() }}) as price,
        cast(freight_value as {{ dbt.type_numeric() }}) as freight_value,
        {{ dlt_loaded_at() }} as _loaded_at
    from source
)

select * from final
