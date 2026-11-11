-- =============================================================================
-- 02_grant_ingest_role.sql
-- Least-privilege grants for YOUTUBE_INGEST_ROLE. Idempotent.
-- Run after 00 and 01. Requires SECURITYADMIN (holds MANAGE GRANTS).
-- =============================================================================

USE ROLE SECURITYADMIN;

-- ---------------------------------------------------------------------------
-- Role hierarchy
-- ---------------------------------------------------------------------------
-- Roll up to SYSADMIN so administrators inherit pipeline access.
GRANT ROLE YOUTUBE_INGEST_ROLE TO ROLE SYSADMIN;

-- Pipeline user. CHANGE THIS to your Snowflake user object name.
-- Double quotes matter: this user was created with a lower-case quoted name,
-- and unquoted identifiers are upper-cased by Snowflake.
-- (The connector authenticates with the user's LOGIN_NAME, which is separate.)
GRANT ROLE YOUTUBE_INGEST_ROLE TO USER "costamurillonow";

-- ---------------------------------------------------------------------------
-- Compute
-- ---------------------------------------------------------------------------
GRANT USAGE, OPERATE ON WAREHOUSE YOUTUBE_INGEST_WH TO ROLE YOUTUBE_INGEST_ROLE;

-- ---------------------------------------------------------------------------
-- Database and schemas
-- ---------------------------------------------------------------------------
GRANT USAGE ON DATABASE YOUTUBE_DB TO ROLE YOUTUBE_INGEST_ROLE;
GRANT USAGE ON SCHEMA YOUTUBE_DB.RAW TO ROLE YOUTUBE_INGEST_ROLE;
GRANT USAGE ON SCHEMA YOUTUBE_DB.CONTROL TO ROLE YOUTUBE_INGEST_ROLE;

-- No CREATE privileges: the loader inserts with INSERT ... SELECT FROM VALUES
-- and needs no stages or temporary tables. All tables are created by SYSADMIN.

-- ---------------------------------------------------------------------------
-- Table privileges (existing + future tables)
-- ---------------------------------------------------------------------------
-- RAW: append-only. DELETE is granted so a retried load can remove rows for
-- its own RUN_ID before re-inserting (idempotent reload). No UPDATE.
GRANT SELECT, INSERT, DELETE ON ALL TABLES    IN SCHEMA YOUTUBE_DB.RAW TO ROLE YOUTUBE_INGEST_ROLE;
GRANT SELECT, INSERT, DELETE ON FUTURE TABLES IN SCHEMA YOUTUBE_DB.RAW TO ROLE YOUTUBE_INGEST_ROLE;

-- CONTROL: run rows are inserted at start and updated at finish.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES    IN SCHEMA YOUTUBE_DB.CONTROL TO ROLE YOUTUBE_INGEST_ROLE;
GRANT SELECT, INSERT, UPDATE ON FUTURE TABLES IN SCHEMA YOUTUBE_DB.CONTROL TO ROLE YOUTUBE_INGEST_ROLE;

-- ---------------------------------------------------------------------------
-- User defaults (already applied on the live account; requires the user's
-- owner, typically ACCOUNTADMIN). Uncomment for a fresh environment.
-- ---------------------------------------------------------------------------
-- USE ROLE ACCOUNTADMIN;
-- ALTER USER "costamurillonow" SET
--     DEFAULT_ROLE      = YOUTUBE_INGEST_ROLE
--     DEFAULT_WAREHOUSE = YOUTUBE_INGEST_WH;
