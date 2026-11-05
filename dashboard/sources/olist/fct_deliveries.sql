-- From the dbt marts: only the columns the pages use, since the published
-- site lets any visitor download its data. The dashboard reads marts only.
select
    order_id,
    customer_unique_id,
    customer_state,
    order_status,
    purchase_date,
    shipped_at,
    estimated_delivery_date,
    delivery_status,
    has_timestamp_anomaly,
    days_to_carrier,
    days_in_transit,
    days_to_deliver,
    days_late_vs_estimate
from main_marts.fct_deliveries
