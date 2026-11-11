-- =============================================================================
-- Migration 20261111_01: adopt RBAC ownership model and RAW table v2
--
-- One-off. Brings the manually created account (all objects owned by
-- ACCOUNTADMIN, tables without RUN_ID / RAW_PAYLOAD) in line with sql/setup.
--
-- Run order:
--   1. this file          (ACCOUNTADMIN)
--   2. setup/01_raw_tables.sql      (recreates tables as SYSADMIN)
--   3. setup/02_grant_ingest_role.sql
--
-- Safety: the four tables were verified empty on 2026-11-11. The guard below
-- aborts the migration if any of them now contains data. Dropped tables
-- remain recoverable with UNDROP TABLE for the Time Travel period (1 day).
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- ---------------------------------------------------------------------------
-- Guard: refuse to run if RAW/CONTROL tables contain any rows
-- ---------------------------------------------------------------------------
EXECUTE IMMEDIATE $$
DECLARE
    total_rows INTEGER DEFAULT 0;
    tables_not_empty EXCEPTION (-20001, 'Migration aborted: RAW/CONTROL tables contain data.');
BEGIN
    SELECT COALESCE(SUM(row_count), 0) INTO :total_rows
    FROM YOUTUBE_DB.INFORMATION_SCHEMA.TABLES
    WHERE table_schema IN ('RAW', 'CONTROL')
      AND table_type = 'BASE TABLE';

    IF (total_rows > 0) THEN
        RAISE tables_not_empty;
    END IF;

    RETURN 'Guard passed: tables are empty';
END;
$$;

-- ---------------------------------------------------------------------------
-- Drop v1 tables (recreated by setup/01_raw_tables.sql)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS YOUTUBE_DB.RAW.VIDEO_DISCOVERY;
DROP TABLE IF EXISTS YOUTUBE_DB.RAW.VIDEO_SNAPSHOT;
DROP TABLE IF EXISTS YOUTUBE_DB.RAW.CHANNEL_SNAPSHOT;
DROP TABLE IF EXISTS YOUTUBE_DB.CONTROL.PIPELINE_RUNS;

-- ---------------------------------------------------------------------------
-- Transfer ownership away from ACCOUNTADMIN
-- COPY CURRENT GRANTS keeps the privileges already granted to other roles.
-- ---------------------------------------------------------------------------
GRANT OWNERSHIP ON ROLE YOUTUBE_INGEST_ROLE TO ROLE USERADMIN COPY CURRENT GRANTS;

GRANT OWNERSHIP ON WAREHOUSE YOUTUBE_INGEST_WH TO ROLE SYSADMIN COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DATABASE YOUTUBE_DB         TO ROLE SYSADMIN COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA YOUTUBE_DB.RAW       TO ROLE SYSADMIN COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA YOUTUBE_DB.CONTROL   TO ROLE SYSADMIN COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA YOUTUBE_DB.PUBLIC    TO ROLE SYSADMIN COPY CURRENT GRANTS;

-- ---------------------------------------------------------------------------
-- Align settings and comments with setup/00_infrastructure.sql
-- (each statement runs as the new owner)
-- ---------------------------------------------------------------------------
USE ROLE USERADMIN;

ALTER ROLE YOUTUBE_INGEST_ROLE SET
    COMMENT = 'Python ingestion pipeline: writes to YOUTUBE_DB.RAW and CONTROL';

USE ROLE SYSADMIN;

ALTER WAREHOUSE YOUTUBE_INGEST_WH SET
    AUTO_SUSPEND = 60
    COMMENT      = 'Ingestion workloads for YOUTUBE_DB';

COMMENT ON DATABASE YOUTUBE_DB IS 'YouTube Niche Intelligence platform';
COMMENT ON SCHEMA YOUTUBE_DB.RAW IS 'Landing zone: append-only API extracts, one row per entity per run';
COMMENT ON SCHEMA YOUTUBE_DB.CONTROL IS 'Pipeline metadata: run log and operational tables';
