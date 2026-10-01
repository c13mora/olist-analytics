{#
    Convert dlt _dlt_load_id into a UTC load timestamp.

    dlt stamps every row with the load it arrived in, as Unix epoch seconds
    stored as text (e.g. '1790893847.2949178'). Rows updated by a later load
    get the new id, so max(_dlt_load_id) is when the source last delivered data.
    Source freshness uses this instead of a business timestamp: in the replay,
    purchase dates are years old even when the loader ran a minute ago.
#}
{% macro dlt_loaded_at(column='_dlt_load_id') -%}
    {{ return(adapter.dispatch('dlt_loaded_at')(column)) }}
{%- endmacro %}

{% macro default__dlt_loaded_at(column) -%}
    to_timestamp(cast({{ column }} as double))
{%- endmacro %}

{% macro snowflake__dlt_loaded_at(column) -%}
    to_timestamp_ntz(cast({{ column }} as number(38, 6)), 0)
{%- endmacro %}
