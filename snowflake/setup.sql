-- One-time Snowflake setup for olist-analytics.
--
-- Run once as ACCOUNTADMIN in a Snowsight worksheet, after replacing
-- <PUBLIC_KEY> below with the contents of your public key file (the lines
-- between -----BEGIN PUBLIC KEY----- and -----END PUBLIC KEY-----, joined
-- into one line). Safe to re-run: every statement is idempotent.
--
-- Design:
-- - Two roles, least privilege: LOADER (dlt) creates and writes the raw
--   schemas; TRANSFORMER (dbt) reads raw and builds its own schemas.
-- - One extra-small warehouse that suspends after 60 idle seconds, capped
--   by a resource monitor so the trial credits cannot run away.
-- - One service user that signs in with a key pair, never a password.

use role accountadmin;

-- Cost guard: notify at 80% of 10 credits a month, suspend the warehouse
-- at 100% (after running queries finish) and immediately at 110%.
create resource monitor if not exists olist_monitor
    with credit_quota = 10
    frequency = monthly
    start_timestamp = immediately
    triggers
        on 80 percent do notify
        on 100 percent do suspend
        on 110 percent do suspend_immediate;

create warehouse if not exists olist_wh
    warehouse_size = xsmall
    auto_suspend = 60
    auto_resume = true
    initially_suspended = true
    comment = 'olist-analytics: dlt loads and dbt builds';

alter warehouse olist_wh set resource_monitor = olist_monitor;

create database if not exists olist
    comment = 'olist-analytics: raw (dlt) and dbt schemas';

-- Roles roll up to SYSADMIN, so administrators can see their objects.
create role if not exists loader comment = 'dlt: creates and writes the raw schemas';
create role if not exists transformer comment = 'dbt: reads raw, builds the dbt schemas';
grant role loader to role sysadmin;
grant role transformer to role sysadmin;

grant usage on warehouse olist_wh to role loader;
grant usage on warehouse olist_wh to role transformer;

grant usage on database olist to role loader;
grant usage on database olist to role transformer;

-- dlt creates RAW, plus RAW_STAGING for merges. dbt creates DBT_DEV and its
-- custom schemas (DBT_DEV_STAGING, DBT_DEV_MARTS, DBT_DEV_SNAPSHOTS).
grant create schema on database olist to role loader;
grant create schema on database olist to role transformer;

-- dbt must read what dlt creates. Database-level future grants (rather than
-- schema-level ones) survive `replay.py --reset`, which drops and recreates
-- the raw schemas.
grant usage on future schemas in database olist to role transformer;
grant select on future tables in database olist to role transformer;

create user if not exists olist_service
    type = service
    default_role = transformer
    default_warehouse = olist_wh
    rsa_public_key = '<PUBLIC_KEY>'
    comment = 'olist-analytics: used by dlt (LOADER) and dbt (TRANSFORMER)';

grant role loader to user olist_service;
grant role transformer to user olist_service;

-- Check: both roles granted, key fingerprint set.
show grants to user olist_service;
describe user olist_service;
