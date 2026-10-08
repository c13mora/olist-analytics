with

source as (
    select * from {{ source('olist', 'geolocation') }}
),

final as (
    select
        geolocation_zip_code_prefix,
        cast(geolocation_lat as {{ dbt.type_float() }}) as geolocation_lat,
        cast(geolocation_lng as {{ dbt.type_float() }}) as geolocation_lng,
        geolocation_city,
        geolocation_state,
        {{ dlt_loaded_at() }} as _loaded_at
    from source
)

select * from final
