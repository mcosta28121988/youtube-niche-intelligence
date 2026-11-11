-- =============================================================================
-- verify_setup.sql - read-only checks of the Snowflake environment.
-- Usage: python -m src.warehouse.run_sql sql/checks/verify_setup.sql
-- =============================================================================

USE ROLE SECURITYADMIN;

SHOW GRANTS TO ROLE YOUTUBE_INGEST_ROLE;
SHOW GRANTS OF ROLE YOUTUBE_INGEST_ROLE;
SHOW FUTURE GRANTS IN SCHEMA YOUTUBE_DB.RAW;
SHOW FUTURE GRANTS IN SCHEMA YOUTUBE_DB.CONTROL;

USE ROLE SYSADMIN;

SHOW WAREHOUSES LIKE 'YOUTUBE_INGEST_WH';
SHOW SCHEMAS IN DATABASE YOUTUBE_DB;
SHOW TABLES IN DATABASE YOUTUBE_DB;
