-- =============================================================================
-- Migration 20261111_04: category-only searches and trending charts
--
-- Discovery rows can now come from:
--   * search   - search.list with a keyword, a category, or both
--   * trending - videos.list chart=mostPopular (region + optional category)
-- Category-only searches and trending charts have no keyword, so
-- SEARCH_KEYWORD becomes nullable. SEARCH_SOURCE records which source
-- produced each row; existing rows are all keyword searches.
-- Idempotent: safe to re-run.
-- =============================================================================

USE ROLE SYSADMIN;

ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY ALTER COLUMN SEARCH_KEYWORD DROP NOT NULL;

ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY ALTER COLUMN SEARCH_KEYWORD
    COMMENT 'Keyword sent to search.list as q; NULL for category-only searches and trending charts';

ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY ALTER COLUMN SEARCH_RANK
    COMMENT '1-based position in the search results or trending chart';

ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY
    ADD COLUMN IF NOT EXISTS SEARCH_SOURCE VARCHAR(20)
    COMMENT 'Discovery source: search (search.list) or trending (videos.list chart=mostPopular)';

UPDATE YOUTUBE_DB.RAW.VIDEO_DISCOVERY
SET SEARCH_SOURCE = 'search'
WHERE SEARCH_SOURCE IS NULL;

ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY ALTER COLUMN SEARCH_SOURCE SET NOT NULL;

ALTER TABLE YOUTUBE_DB.RAW.VIDEO_DISCOVERY SET
    COMMENT = 'Discovered videos from searches and trending charts. Grain: one row per run x configured search x video.';
