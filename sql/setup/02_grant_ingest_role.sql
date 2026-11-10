-- =============================================================================
-- Grant the ingestion role to the pipeline user and give it DML on RAW/CONTROL.
-- Run as ACCOUNTADMIN (or SECURITYADMIN + object owner). Idempotent.
--
-- Context: YOUTUBE_INGEST_ROLE already has warehouse USAGE/OPERATE, database and
-- schema USAGE, and CREATE TABLE / CREATE STAGE. It was missing:
--   1. assignment to the pipeline user
--   2. DML on the pre-existing tables (owned by ACCOUNTADMIN)
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- 1. Role hierarchy: assign to the user and roll up to SYSADMIN (best practice,
--    so admins can manage objects the role creates).
GRANT ROLE YOUTUBE_INGEST_ROLE TO USER costamurillonow;
GRANT ROLE YOUTUBE_INGEST_ROLE TO ROLE SYSADMIN;

-- 2. DML on existing and future tables in RAW and CONTROL.
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA YOUTUBE_DB.RAW TO ROLE YOUTUBE_INGEST_ROLE;
GRANT SELECT, INSERT ON FUTURE TABLES IN SCHEMA YOUTUBE_DB.RAW TO ROLE YOUTUBE_INGEST_ROLE;

-- CONTROL.PIPELINE_RUNS rows are inserted at start and updated at finish.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA YOUTUBE_DB.CONTROL TO ROLE YOUTUBE_INGEST_ROLE;
GRANT SELECT, INSERT, UPDATE ON FUTURE TABLES IN SCHEMA YOUTUBE_DB.CONTROL TO ROLE YOUTUBE_INGEST_ROLE;

-- 3. Optional: make the pipeline role the user's default instead of ACCOUNTADMIN.
-- ALTER USER costamurillonow SET DEFAULT_ROLE = YOUTUBE_INGEST_ROLE
--                                DEFAULT_WAREHOUSE = YOUTUBE_INGEST_WH;

-- Verify
SHOW GRANTS TO ROLE YOUTUBE_INGEST_ROLE;
SHOW GRANTS OF ROLE YOUTUBE_INGEST_ROLE;
