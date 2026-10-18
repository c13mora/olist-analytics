-- One row per day. The range covers every purchase (from 2016-09-04) and
-- every promised delivery date (up to 2018-11-12). The source is a fixed
-- export, so the bounds are fixed too.

with

date_spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2016-09-01' as date)",
        end_date="cast('2019-01-01' as date)"
    ) }}
),

final as (
    select
        cast(date_day as date) as date_day,
        cast(extract(year from date_day) as {{ dbt.type_int() }}) as year_number,
        cast(extract(quarter from date_day) as {{ dbt.type_int() }}) as quarter_of_year,
        cast(extract(month from date_day) as {{ dbt.type_int() }}) as month_of_year,
        cast(extract(day from date_day) as {{ dbt.type_int() }}) as day_of_month,
        -- 0 = Sunday to 6 = Saturday, on DuckDB and on Snowflake with its
        -- default WEEK_START setting.
        cast(extract(dow from date_day) as {{ dbt.type_int() }}) as day_of_week,
        extract(dow from date_day) in (0, 6) as is_weekend,
        -- Weeks start on Monday.
        cast({{ dbt.date_trunc('week', 'date_day') }} as date) as week_start_date,
        cast({{ dbt.date_trunc('month', 'date_day') }} as date) as month_start_date,
        cast({{ dbt.date_trunc('quarter', 'date_day') }} as date) as quarter_start_date
    from date_spine
)

select * from final
