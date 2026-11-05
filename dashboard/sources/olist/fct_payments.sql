-- From the dbt marts: only the columns the pages use, since the published
-- site lets any visitor download its data. The dashboard reads marts only.
select
    purchase_date,
    payment_type,
    payment_value
from main_marts.fct_payments
