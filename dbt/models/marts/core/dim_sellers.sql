with

sellers as (
    select * from {{ ref('stg_olist__sellers') }}
),

geolocation as (
    select * from {{ ref('int_geolocation__grouped_by_zip') }}
),

final as (
    select
        sellers.seller_id,
        sellers.seller_zip_code_prefix,
        sellers.seller_city,
        sellers.seller_state,
        -- Null for the 7 sellers whose zip code prefix has no geolocation.
        geolocation.latitude as seller_latitude,
        geolocation.longitude as seller_longitude
    from sellers
    left join geolocation
        on sellers.seller_zip_code_prefix = geolocation.zip_code_prefix
)

select * from final
