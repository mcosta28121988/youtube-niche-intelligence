"""Channel enrichment via channels.list (statistics and metadata)."""

from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import Resource

from src.api.parsing import optional_int
from src.api.quota import QuotaTracker
from src.api.retry import execute_with_retry
from src.api.youtube_client import get_youtube_client

logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # channels.list maximum IDs per request


def get_channel_statistics(
    channel_ids: list[str],
    youtube: Resource | None = None,
    quota: QuotaTracker | None = None,
) -> list[dict[str, Any]]:
    """Fetch statistics for channels in batches of 50 (1 quota unit per batch)."""
    youtube = youtube or get_youtube_client()

    results: list[dict[str, Any]] = []

    unique_ids = list(dict.fromkeys(channel_ids))

    for i in range(0, len(unique_ids), BATCH_SIZE):
        batch = unique_ids[i : i + BATCH_SIZE]

        request = youtube.channels().list(
            part="snippet,statistics,contentDetails",
            id=",".join(batch),
        )

        response = execute_with_retry(request)
        if quota:
            quota.record("channels.list")

        for item in response.get("items", []):
            snippet = item["snippet"]
            stats = item.get("statistics", {})
            playlists = item.get("contentDetails", {}).get("relatedPlaylists", {})

            subscribers = (
                None
                if stats.get("hiddenSubscriberCount")
                else optional_int(stats.get("subscriberCount"))
            )

            results.append(
                {
                    "channel_id": item["id"],
                    "channel_name": snippet["title"],
                    "published_at": snippet["publishedAt"],
                    "subscribers": subscribers,
                    "total_views": optional_int(stats.get("viewCount")),
                    "video_count": optional_int(stats.get("videoCount")),
                    "uploads_playlist_id": playlists.get("uploads"),
                    "raw_payload": item,
                }
            )

    logger.info("Channel extraction completed: %s channels", len(results))

    return results
