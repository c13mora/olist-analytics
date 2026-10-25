-- fct_order_items from the dbt marts. The dashboard reads marts only, never staging or raw.
select * from main_marts.fct_order_items
