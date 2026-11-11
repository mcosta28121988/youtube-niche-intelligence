"""Video discovery: filtered search (search.list) and trending charts (videos.list).

Both return rows of the same shape, so they load into RAW.VIDEO_DISCOVERY
side by side.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from src.api.quota import QuotaTracker
from src.api.retry import error_reasons, execute_with_retry
from src.api.youtube_client import get_youtube_client

logger = logging.getLogger(__name__)

PAGE_SIZE = 50  # maximum results per page for search.list and videos.list

# videos.list error reasons when a region/category has no Most Popular chart
# (the live API answers 404 notFound; videoChartNotFound is documented).
CHART_NOT_FOUND_REASONS = frozenset({"notFound", "videoChartNotFound"})


def _discovery_row(
    video_id: str,
    snippet: dict[str, Any],
    keyword: str | None,
    rank: int,
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "video_id": video_id,
        "channel_id": snippet.get("channelId"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "channel_title": snippet.get("channelTitle"),
        "published_at": snippet.get("publishedAt"),
        "keyword": keyword,
        "search_rank": rank,
        "raw_payload": item,
    }


def search_videos(
    keyword: str | None = None,
    max_pages: int = 1,
    youtube: Resource | None = None,
    quota: QuotaTracker | None = None,
    order: str = "viewCount",
    filters: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Search videos by keyword and/or filters.

    ``keyword`` is optional: without it, search.list returns the top videos
    matching the filters alone (e.g. ``videoCategoryId`` + ``regionCode``).
    ``filters`` are extra search.list parameters (e.g. ``videoDuration``,
    ``regionCode``, ``publishedAfter``) and may override ``order``.
    Returns one record per unique video with its 1-based ``search_rank``
    across pages. Each page costs one search.list call.
    """
    youtube = youtube or get_youtube_client()
    label = keyword or f"filters {dict(filters or {})}"

    videos: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    rank = 0
    next_page_token = None

    for page in range(max_pages):
        logger.info("Searching %s, page %s", label, page + 1)

        params: dict[str, Any] = {
            "order": order,
            **(filters or {}),
            "part": "snippet",
            "type": "video",  # required by the video-specific filters
            "maxResults": PAGE_SIZE,
            "pageToken": next_page_token,
        }
        if keyword:
            params["q"] = keyword

        response = execute_with_retry(youtube.search().list(**params))
        if quota:
            quota.record("search.list")

        for item in response.get("items", []):
            rank += 1
            video_id = item["id"]["videoId"]

            # Results can shift between pages; keep the best (first) rank.
            if video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            videos.append(_discovery_row(video_id, item["snippet"], keyword, rank, item))

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    logger.info("Discovery completed. Retrieved %s videos for %s", len(videos), label)
    return videos


def trending_videos(
    max_pages: int = 1,
    youtube: Resource | None = None,
    quota: QuotaTracker | None = None,
    filters: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Read YouTube's Most Popular chart (videos.list chart=mostPopular).

    ``filters`` may contain ``regionCode`` and ``videoCategoryId``. Rank is
    the chart position. Each page costs 1 quota unit; the chart holds at most
    200 videos. Some region/category combinations have no chart: that is
    logged as a warning and returns no rows rather than failing the run.
    """
    youtube = youtube or get_youtube_client()
    label = f"trending chart {dict(filters or {})}"

    videos: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    rank = 0
    next_page_token = None

    for page in range(max_pages):
        logger.info("Reading %s, page %s", label, page + 1)

        request = youtube.videos().list(
            **{
                **(filters or {}),
                "part": "snippet",
                "chart": "mostPopular",
                "maxResults": PAGE_SIZE,
                "pageToken": next_page_token,
            }
        )
        try:
            response = execute_with_retry(request)
        except HttpError as error:
            if quota:
                quota.record("videos.list")
            if CHART_NOT_FOUND_REASONS.intersection(error_reasons(error)):
                logger.warning(
                    "No Most Popular chart for %s; this category may not "
                    "have a chart in this region. Skipping.", label,
                )
                return videos
            raise
        if quota:
            quota.record("videos.list")

        for item in response.get("items", []):
            rank += 1
            video_id = item["id"]
            if video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            videos.append(_discovery_row(video_id, item.get("snippet", {}), None, rank, item))

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    logger.info("Discovery completed. Retrieved %s videos for %s", len(videos), label)
    return videos
