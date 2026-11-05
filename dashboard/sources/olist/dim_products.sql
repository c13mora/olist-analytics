-- From the dbt marts: only the columns the pages use, since the published
-- site lets any visitor download its data. The dashboard reads marts only.
select
    product_id,
    product_category_name_english
from main_marts.dim_products
