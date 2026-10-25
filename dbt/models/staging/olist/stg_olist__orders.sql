with

source as (
    select * from {{ source('olist', 'orders') }}
),

renamed as (
    select
        order_id,
        customer_id,
        order_status,
        cast(order_purchase_timestamp as {{ dbt.type_timestamp() }}) as purchased_at,
        cast(order_approved_at as {{ dbt.type_timestamp() }}) as approved_at,
        cast(order_delivered_carrier_date as {{ dbt.type_timestamp() }}) as shipped_at,
        cast(order_delivered_customer_date as {{ dbt.type_timestamp() }}) as delivered_at,
        cast(order_estimated_delivery_date as date) as estimated_delivery_date,
        {{ dlt_loaded_at() }} as _loaded_at
    from source
),

final as (
    select
        *,
        -- The latest milestone that has happened so far. In the replay, an
        -- order's status only changes when a milestone passes, so this is the
        -- business time of its latest change. snap_orders uses it to date
        -- each version. Empty milestones fall back to the purchase time,
        -- because greatest() returns null on Snowflake if any input is null.
        greatest(
            purchased_at,
            coalesce(approved_at, purchased_at),
            coalesce(shipped_at, purchased_at),
            coalesce(delivered_at, purchased_at)
        ) as status_updated_at
    from renamed
)

select * from final
