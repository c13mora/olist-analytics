-- A view rather than the ephemeral default: dbt cannot test ephemeral models,
-- and the unique test on zip_code_prefix is what keeps the fan-out away.
{{ config(materialized='view') }}

with

geolocation as (
    select * from {{ ref('stg_olist__geolocation') }}
),

-- The source repeats 262k points verbatim. Keep each point once, so repeats
-- do not count twice in the median.
distinct_points as (
    select distinct
        geolocation_zip_code_prefix as zip_code_prefix,
        geolocation_lat as latitude,
        geolocation_lng as longitude,
        geolocation_state as state
    from geolocation
),

-- Rough bounding box around Brazil. Drops 42 points, and with them the 5
-- prefixes that have no point inside Brazil.
points_in_brazil as (
    select * from distinct_points
    where
        latitude between -34 and 6
        and longitude between -74 and -34
),

final as (
    select
        zip_code_prefix,
        -- Median, not average: points of one prefix can be thousands of
        -- kilometers apart, and the median is not pulled by such strays.
        median(latitude) as latitude,
        median(longitude) as longitude,
        -- Most common state. 8 prefixes have points in two states.
        mode(state) as state,
        count(*) as point_count
    from points_in_brazil
    group by zip_code_prefix
)

select * from final
