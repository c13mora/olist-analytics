with

source as (
    select * from {{ source('olist', 'order_reviews') }}
),

final as (
    select
        review_id,
        order_id,
        cast(review_score as {{ dbt.type_int() }}) as review_score,
        -- Free-text comments: trim padding, and treat whitespace-only text as
        -- no comment at all.
        nullif(trim(review_comment_title), '') as review_comment_title,
        nullif(trim(review_comment_message), '') as review_comment_message,
        cast(review_creation_date as {{ dbt.type_timestamp() }}) as review_created_at,
        cast(review_answer_timestamp as {{ dbt.type_timestamp() }}) as review_answered_at,
        {{ dlt_loaded_at() }} as _loaded_at
    from source
)

select * from final
