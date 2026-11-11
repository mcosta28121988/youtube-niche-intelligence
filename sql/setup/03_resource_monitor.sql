-- =============================================================================
-- 03_resource_monitor.sql  (OPTIONAL, recommended)
-- Caps monthly credit spend on the ingestion warehouse. Idempotent.
-- Resource monitors can only be created by ACCOUNTADMIN.
--
-- Sizing: an X-Small warehouse uses 1 credit/hour. Daily ingestion runs of a
-- few seconds (billed as 60s minimum) use well under 1 credit/month, so a
-- 5-credit cap leaves generous headroom while preventing runaway costs.
-- Adjust CREDIT_QUOTA to your budget.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

CREATE RESOURCE MONITOR IF NOT EXISTS YOUTUBE_MONTHLY_MONITOR
    WITH CREDIT_QUOTA    = 5
         FREQUENCY       = MONTHLY
         START_TIMESTAMP = IMMEDIATELY
    TRIGGERS
        ON 75  PERCENT DO NOTIFY
        ON 90  PERCENT DO NOTIFY
        ON 100 PERCENT DO SUSPEND
        ON 110 PERCENT DO SUSPEND_IMMEDIATE;

ALTER WAREHOUSE YOUTUBE_INGEST_WH SET RESOURCE_MONITOR = YOUTUBE_MONTHLY_MONITOR;
