-- =============================================================================
-- Migration 20261111_03: record which configured search produced each row
--
-- Searches are now defined in config/searches.toml with filters (duration,
-- upload date, region, category ...). The same keyword can be searched with
-- different filters, so the discovery grain becomes run x search x video.
--   * SEARCH_NAME    - unique name of the configured search
--   * SEARCH_FILTERS - exact search.list parameters sent
-- Existing rows (keyword-only searches) are backfilled with
-- SEARCH_NAME = SEARCH_KEYWORD; their SEARCH_FILTERS stay NULL.
-- Idempotent: safe to re-run.
-- =============================================================================

USE ROLE SYSADMIN;

ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY
    ADD COLUMN IF NOT EXISTS SEARCH_NAME VARCHAR(200)
    COMMENT 'Unique name of the configured search (config/searches.toml)';

ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY
    ADD COLUMN IF NOT EXISTS SEARCH_FILTERS VARIANT
    COMMENT 'Exact search.list parameters sent (q, order, regionCode, ...)';

UPDATE YOUTUBE_DB.RAW.VIDEO_DISCOVERY
SET SEARCH_NAME = SEARCH_KEYWORD
WHERE SEARCH_NAME IS NULL;

ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY ALTER COLUMN SEARCH_NAME SET NOT NULL;

-- Primary keys are informational in Snowflake; this documents the new grain.
ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY DROP PRIMARY KEY;
ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY
    ADD CONSTRAINT PK_VIDEO_DISCOVERY PRIMARY KEY (RUN_ID, SEARCH_NAME, VIDEO_ID);

ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY SET
    COMMENT = 'Search results. Grain: one row per run x configured search x video.';
