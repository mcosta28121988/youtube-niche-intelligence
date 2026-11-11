-- =============================================================================
-- Migration 20261111_02: track search.list calls; remove unused CREATE grants
--
-- * search.list has its own daily allowance (100 calls), separate from the
--   10,000-unit budget, so it gets its own column in PIPELINE_RUNS.
-- * The loader uses INSERT ... SELECT FROM VALUES and needs no stages or
--   temporary tables, so the pipeline role's CREATE privileges are revoked.
-- Idempotent: safe to re-run.
-- =============================================================================

USE ROLE SYSADMIN;

ALTER TABLE YOUTUBE_DB.CONTROL.PIPELINE_RUNS
    ADD COLUMN IF NOT EXISTS SEARCH_CALLS NUMBER(38,0)
    COMMENT 'search.list calls made (separate 100/day allowance)';

ALTER TABLE YOUTUBE_DB.CONTROL.PIPELINE_RUNS
    ALTER COLUMN API_QUOTA_UNITS_ESTIMATED
    COMMENT 'Estimated units used from the 10,000/day budget (excludes search.list)';

USE ROLE SECURITYADMIN;

REVOKE CREATE TABLE, CREATE STAGE ON SCHEMA YOUTUBE_DB.RAW FROM ROLE YOUTUBE_INGEST_ROLE;
REVOKE CREATE TABLE ON SCHEMA YOUTUBE_DB.CONTROL FROM ROLE YOUTUBE_INGEST_ROLE;
