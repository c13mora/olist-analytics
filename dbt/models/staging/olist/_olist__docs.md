{#
    Column descriptions for the Olist source, written once and reused by
    sources and staging models through doc('olist__<column>').
    Block names follow the raw column names.
#}

{% docs olist__order_id %}
Unique identifier of an order.
{% enddocs %}

{% docs olist__customer_id %}
Identifier of the customer *for one order*. Olist issues a new `customer_id`
for every order, so it is one-to-one with `order_id`. Use `customer_unique_id`
to identify the same person across orders.
{% enddocs %}

{% docs olist__customer_unique_id %}
Identifier of the person behind a `customer_id`. Stable across orders, so it
is the key for repeat-purchase and cohort analysis.
{% enddocs %}

{% docs olist__product_id %}
Unique identifier of a product.
{% enddocs %}

{% docs olist__seller_id %}
Unique identifier of a seller on the Olist marketplace.
{% enddocs %}

{% docs olist__review_id %}
Identifier of a review survey. Not unique on its own: 789 review ids are
attached to more than one order, so the key is (`review_id`, `order_id`).
{% enddocs %}

{% docs olist__zip_code_prefix %}
First five digits of a Brazilian postal code (CEP), kept as text to preserve
leading zeros (e.g. `01037`).
{% enddocs %}

{% docs olist__city %}
City name, lowercase and mostly without accents, as entered in the source.
{% enddocs %}

{% docs olist__state %}
Two-letter Brazilian state code (UF), e.g. `SP`, `RJ`.
{% enddocs %}

{% docs olist__order_status %}
Order status as of the simulated date: `created`, `approved`, `invoiced`,
`processing`, `shipped`, `delivered`, `canceled` or `unavailable`. The replay
rebuilds it from the milestone timestamps; see decision record 001.
{% enddocs %}

{% docs olist__order_purchase_timestamp %}
When the customer placed the order.
{% enddocs %}

{% docs olist__order_approved_at %}
When the payment was approved. Null until approval happens.
{% enddocs %}

{% docs olist__order_delivered_carrier_date %}
When the seller handed the order to the logistics carrier. Null until then.
Sometimes earlier than the approval or even the purchase (a source data issue).
{% enddocs %}

{% docs olist__order_delivered_customer_date %}
When the order was delivered to the customer. Null until then.
{% enddocs %}

{% docs olist__order_estimated_delivery_date %}
Delivery date promised to the customer at checkout (date only).
{% enddocs %}

{% docs olist__order_item_id %}
Sequential number of an item within an order (1, 2, 3...). An order with two
units of the same product has two rows.
{% enddocs %}

{% docs olist__shipping_limit_date %}
Deadline for the seller to hand the item to the carrier.
{% enddocs %}

{% docs olist__price %}
Item price in Brazilian reais (BRL), excluding freight.
{% enddocs %}

{% docs olist__freight_value %}
Freight charged for the item in BRL. When an order has several items, the
freight is split between them.
{% enddocs %}

{% docs olist__payment_sequential %}
Sequence number of a payment within an order. 2,961 orders are paid in more
than one payment, e.g. a credit card plus vouchers.
{% enddocs %}

{% docs olist__payment_type %}
Payment method: `credit_card`, `boleto` (Brazilian bank slip), `voucher`,
`debit_card` or `not_defined`.
{% enddocs %}

{% docs olist__payment_installments %}
Number of installments the customer chose (0 to 24).
{% enddocs %}

{% docs olist__payment_value %}
Amount of this payment in BRL.
{% enddocs %}

{% docs olist__review_score %}
Customer satisfaction score from 1 (worst) to 5 (best).
{% enddocs %}

{% docs olist__review_comment_title %}
Optional review title, in Portuguese.
{% enddocs %}

{% docs olist__review_comment_message %}
Optional review comment, in Portuguese.
{% enddocs %}

{% docs olist__review_creation_date %}
When the satisfaction survey was sent to the customer.
{% enddocs %}

{% docs olist__review_answer_timestamp %}
When the customer answered the survey.
{% enddocs %}

{% docs olist__product_category_name %}
Product category in Portuguese. Null for 610 products. Translate with
`product_category_name_translation`, which lacks two categories (`pc_gamer`,
`portateis_cozinha_e_preparadores_de_alimentos`).
{% enddocs %}

{% docs olist__product_category_name_english %}
Product category name in English.
{% enddocs %}

{% docs olist__product_name_lenght %}
Number of characters in the product name. The column name is misspelled in
the source.
{% enddocs %}

{% docs olist__product_description_lenght %}
Number of characters in the product description. The column name is
misspelled in the source.
{% enddocs %}

{% docs olist__product_photos_qty %}
Number of photos published for the product.
{% enddocs %}

{% docs olist__product_weight_g %}
Product weight in grams.
{% enddocs %}

{% docs olist__product_length_cm %}
Product length in centimeters.
{% enddocs %}

{% docs olist__product_height_cm %}
Product height in centimeters.
{% enddocs %}

{% docs olist__product_width_cm %}
Product width in centimeters.
{% enddocs %}

{% docs olist__geolocation_lat %}
Latitude of a point within the zip code prefix.
{% enddocs %}

{% docs olist__geolocation_lng %}
Longitude of a point within the zip code prefix.
{% enddocs %}

{% docs olist__loaded_at %}
When the loader last wrote this row (UTC), derived from dlt's `_dlt_load_id`.
Updated whenever the row changes in the source, e.g. on an order status
change, so it can drive incremental models.
{% enddocs %}
