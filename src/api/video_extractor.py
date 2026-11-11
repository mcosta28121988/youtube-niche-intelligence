"""Video enrichment via videos.list (statistics and metadata)."""

from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import Resource

from src.api.parsing import optional_int
from src.api.quota import QuotaTracker
from src.api.retry import execute_with_retry
from src.api.youtube_client import get_youtube_client

logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # videos.list maximum IDs per request


def get_video_statistics(
    video_ids: list[str],
    youtube: Resource | None = None,
    quota: QuotaTracker | None = None,
) -> list[dict[str, Any]]:
    """Fetch statistics for videos in batches of 50 (1 quota unit per batch)."""
    youtube = youtube or get_youtube_client()

    results: list[dict[str, Any]] = []

    unique_ids = list(dict.fromkeys(video_ids))

    for i in range(0, len(unique_ids), BATCH_SIZE):

        batch = unique_ids[i:i + BATCH_SIZE]

        logger.info("Extracting statistics for %s videos", len(batch))

        request = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(batch),
        )

        response = execute_with_retry(request)
        if quota:
            quota.record("videos.list")

        for item in response.get("items", []):

            snippet = item["snippet"]
            stats = item.get("statistics", {})
            details = item.get("contentDetails", {})

            results.append({
                "video_id": item["id"],
                "channel_id": snippet["channelId"],
                "title": snippet["title"],
                "category_id": snippet.get("categoryId"),
                "published_at": snippet["publishedAt"],
                "duration": details.get("duration"),
                "views": optional_int(stats.get("viewCount")),
                "likes": optional_int(stats.get("likeCount")),
                "comments": optional_int(stats.get("commentCount")),
                "raw_payload": item,
            })

    logger.info("Video enrichment completed: %s videos", len(results))

    return results
