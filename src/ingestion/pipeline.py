"""End-to-end ingestion: YouTube API -> Snowflake RAW, with run tracking.

Run order:
  1. register the run in CONTROL.PIPELINE_RUNS (RUNNING)
  2. purge RAW rows past the retention window (runs even if extraction fails)
  3. discover videos per configured search (search.list with filters)
  4. enrich videos (videos.list) and channels (channels.list)
  5. load all RAW tables atomically for this RUN_ID
  6. mark the run SUCCEEDED / FAILED with metrics
"""

from __future__ import annotations

import logging
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import Resource

from config.settings import PipelineSettings
from src.api.categories import CategoryResolver
from src.api.channel_extractor import get_channel_statistics
from src.api.quota import QuotaTracker
from src.api.video_extractor import get_video_statistics
from src.api.youtube_client import get_youtube_client
from src.ingestion.discover_videos import search_videos
from src.warehouse.pipeline_runs import PipelineRunTracker, RunMetrics, RunStatus
from src.warehouse.snowflake_connection import get_snowflake_connection
from src.warehouse.snowflake_loader import (
    CHANNEL_SNAPSHOT,
    VIDEO_DISCOVERY,
    VIDEO_SNAPSHOT,
    load_run,
    purge_expired,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractedData:
    discovery: list[dict[str, Any]] = field(default_factory=list)
    videos: list[dict[str, Any]] = field(default_factory=list)
    channels: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PipelineResult:
    run_id: str
    metrics: RunMetrics
    loaded: dict[str, int] = field(default_factory=dict)
    purged: dict[str, int] = field(default_factory=dict)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp(rows: list[dict[str, Any]], extracted_at: str) -> list[dict[str, Any]]:
    return [{**row, "extracted_at": extracted_at} for row in rows]


def extract(
    settings: PipelineSettings,
    youtube: Resource,
    quota: QuotaTracker,
    metrics: RunMetrics,
) -> ExtractedData:
    """Call the YouTube API; updates ``metrics`` as each stage completes."""
    data = ExtractedData()

    # Resolve all category names up front so a typo fails before any search.
    resolver = CategoryResolver(youtube, quota)
    now = datetime.now(timezone.utc)
    search_params = [
        (
            search,
            search.api_parameters(
                category_id=resolver.resolve(search.category, search.region_code),
                now=now,
            ),
        )
        for search in settings.searches
    ]

    for search, params in search_params:
        extracted_at = _utc_now()
        results = search_videos(
            keyword=search.keyword,
            max_pages=search.max_pages,
            youtube=youtube,
            quota=quota,
            filters=params,
        )
        recorded_filters = {"q": search.keyword, **params}
        data.discovery.extend(
            {**row, "search_name": search.name, "search_filters": recorded_filters}
            for row in _stamp(results, extracted_at)
        )

    video_ids = list(dict.fromkeys(row["video_id"] for row in data.discovery))
    metrics.videos_discovered = len(video_ids)

    extracted_at = _utc_now()
    data.videos = _stamp(
        get_video_statistics(video_ids, youtube=youtube, quota=quota),
        extracted_at,
    )
    metrics.videos_enriched = len(data.videos)

    channel_ids = list(dict.fromkeys(row["channel_id"] for row in data.videos))
    extracted_at = _utc_now()
    data.channels = _stamp(
        get_channel_statistics(channel_ids, youtube=youtube, quota=quota),
        extracted_at,
    )
    metrics.channels_extracted = len(data.channels)

    return data


def run_pipeline(settings: PipelineSettings, load: bool = True) -> PipelineResult:
    """Run the pipeline. With ``load=False`` nothing touches Snowflake."""
    run_id = str(uuid.uuid4())
    metrics = RunMetrics()
    quota = QuotaTracker()
    result = PipelineResult(run_id=run_id, metrics=metrics)

    logger.info(
        "Run %s: %s searches, up to %s search calls, load=%s",
        run_id, len(settings.searches), settings.planned_search_calls, load,
    )

    youtube = get_youtube_client()

    if not load:
        extract(settings, youtube, quota, metrics)
        _sync_quota(metrics, quota)
        _log_summary(result)
        return result

    with closing(get_snowflake_connection()) as conn:
        tracker = PipelineRunTracker(conn, run_id, settings.pipeline_name)
        tracker.start(settings.to_run_parameters())
        try:
            result.purged = purge_expired(conn, settings.retention_days)
            data = extract(settings, youtube, quota, metrics)
            result.loaded = load_run(
                conn,
                run_id,
                [
                    (VIDEO_DISCOVERY, data.discovery),
                    (VIDEO_SNAPSHOT, data.videos),
                    (CHANNEL_SNAPSHOT, data.channels),
                ],
            )
        except Exception as error:
            _sync_quota(metrics, quota)
            tracker.finish(RunStatus.FAILED, metrics, f"{type(error).__name__}: {error}")
            raise
        _sync_quota(metrics, quota)
        tracker.finish(RunStatus.SUCCEEDED, metrics)

    _log_summary(result)
    return result


def run_retention(settings: PipelineSettings) -> dict[str, int]:
    """Purge expired RAW rows without calling the YouTube API."""
    with closing(get_snowflake_connection()) as conn:
        return purge_expired(conn, settings.retention_days)


def _sync_quota(metrics: RunMetrics, quota: QuotaTracker) -> None:
    metrics.search_calls = quota.search_calls
    metrics.quota_units = quota.units


def _log_summary(result: PipelineResult) -> None:
    m = result.metrics
    logger.info(
        "Run %s summary: videos discovered=%s, enriched=%s, channels=%s, "
        "search calls=%s, quota units=%s",
        result.run_id, m.videos_discovered, m.videos_enriched,
        m.channels_extracted, m.search_calls, m.quota_units,
    )
