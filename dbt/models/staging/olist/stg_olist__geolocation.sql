with

source as (
    select * from {{ source('olist', 'geolocation') }}
),

final as (
    select
        geolocation_zip_code_prefix,
        -- double, not dbt.type_float(): that renders FLOAT, which is 64-bit on
        -- Snowflake but 32-bit on DuckDB, where it rounded coordinates to about
        -- 7 digits. Points that differed only past that merged, changing the
        -- distinct-point medians by up to ~600 m. DOUBLE is 64-bit on both.
        cast(geolocation_lat as double) as geolocation_lat,
        cast(geolocation_lng as double) as geolocation_lng,
        geolocation_city,
        geolocation_state,
        {{ dlt_loaded_at() }} as _loaded_at
    from source
)

select * from final
