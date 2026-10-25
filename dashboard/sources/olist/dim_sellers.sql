-- dim_sellers from the dbt marts. The dashboard reads marts only, never staging or raw.
select * from main_marts.dim_sellers
