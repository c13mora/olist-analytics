-- From the dbt marts: only the columns the pages use, since the published
-- site lets any visitor download its data. The dashboard reads marts only.
select
    order_id,
    review_score
from main_marts.fct_reviews
