-- From the dbt marts: only the columns the pages use, since the published
-- site lets any visitor download its data. The dashboard reads marts only.
select
    order_id,
    seller_id,
    product_id,
    purchase_date,
    shipping_limit_at,
    price,
    freight_value
from main_marts.fct_order_items
