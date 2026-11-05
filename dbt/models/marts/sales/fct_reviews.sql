-- One row per review: the customer satisfaction survey sent after an order.
-- The key is (review_id, order_id), because 789 review ids appear on more
-- than one order. Join to fct_deliveries on order_id to relate scores to
-- delivery times; an order can have up to three reviews.

with

reviews as (
    select * from {{ ref('stg_olist__order_reviews') }}
),

orders as (
    select * from {{ ref('int_orders__joined_to_customers') }}
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['reviews.review_id', 'reviews.order_id']) }}
            as review_key,
        reviews.review_id,
        reviews.order_id,
        orders.customer_unique_id,
        orders.purchase_date,
        reviews.review_score,
        reviews.review_created_at,
        reviews.review_answered_at,
        -- The comment text itself (Portuguese free text) stays in staging.
        reviews.review_comment_title is not null
        or reviews.review_comment_message is not null as has_comment,
        cast(reviews.review_created_at as date) as review_date
    from reviews
    inner join orders
        on reviews.order_id = orders.order_id
)

select * from final
