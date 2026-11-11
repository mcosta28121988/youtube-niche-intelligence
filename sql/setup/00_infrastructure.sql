-- =============================================================================
-- 00_infrastructure.sql
-- Role, warehouse, database and schemas for the YouTube Niche Intelligence
-- platform. Idempotent: safe to re-run (IF NOT EXISTS everywhere).
--
-- Role model (Snowflake best practice - avoid ACCOUNTADMIN for daily work):
--   USERADMIN  -> owns functional roles
--   SYSADMIN   -> owns warehouses, databases, schemas, tables
--   SECURITYADMIN -> manages grants (see 02_grant_ingest_role.sql)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Functional role used by the Python ingestion pipeline
-- ---------------------------------------------------------------------------
USE ROLE USERADMIN;

CREATE ROLE IF NOT EXISTS YOUTUBE_INGEST_ROLE
    COMMENT = 'Python ingestion pipeline: writes to YOUTUBE_DB.RAW and CONTROL';

-- ---------------------------------------------------------------------------
-- Compute
-- ---------------------------------------------------------------------------
USE ROLE SYSADMIN;

-- X-Small + 60s auto-suspend: ingestion is bursty (a few seconds per run),
-- so a short suspend window keeps credit usage close to zero.
CREATE WAREHOUSE IF NOT EXISTS YOUTUBE_INGEST_WH
    WAREHOUSE_SIZE      = 'XSMALL'
    AUTO_SUSPEND        = 60
    AUTO_RESUME         = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT             = 'Ingestion workloads for YOUTUBE_DB';

-- ---------------------------------------------------------------------------
-- Storage
-- ---------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS YOUTUBE_DB
    COMMENT = 'YouTube Niche Intelligence platform';

CREATE SCHEMA IF NOT EXISTS YOUTUBE_DB.RAW
    COMMENT = 'Landing zone: append-only API extracts, one row per entity per run';

CREATE SCHEMA IF NOT EXISTS YOUTUBE_DB.CONTROL
    COMMENT = 'Pipeline metadata: run log and operational tables';
