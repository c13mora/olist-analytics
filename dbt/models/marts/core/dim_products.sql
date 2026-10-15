with

products as (
    select * from {{ ref('stg_olist__products') }}
),

source_translations as (
    select
        product_category_name,
        product_category_name_english
    from {{ ref('stg_olist__product_category_name_translation') }}
),

-- Olist's translation table lacks two categories used by 13 products. Their
-- English names are added by hand in a seed.
translation_additions as (
    select
        product_category_name,
        product_category_name_english
    from {{ ref('product_category_name_translation_additions') }}
),

translations as (
    select * from source_translations
    union all
    select * from translation_additions
),

final as (
    select
        products.product_id,
        products.product_category_name,
        products.product_name_length,
        products.product_description_length,
        products.product_photos_qty,
        products.product_weight_g,
        products.product_length_cm,
        products.product_height_cm,
        products.product_width_cm,
        -- 'unknown' only for the 610 products without a category. A new
        -- category missing from both translation sources stays null, so the
        -- not_null test fails instead of hiding it as 'unknown'.
        case
            when products.product_category_name is null then 'unknown'
            else translations.product_category_name_english
        end as product_category_name_english
    from products
    left join translations
        on products.product_category_name = translations.product_category_name
)

select * from final
