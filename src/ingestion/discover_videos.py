"""Video discovery via search.list."""

from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import Resource

from src.api.quota import QuotaTracker
from src.api.retry import execute_with_retry
from src.api.youtube_client import get_youtube_client

logger = logging.getLogger(__name__)

PAGE_SIZE = 50  # search.list maximum results per page


def search_videos(
    keyword: str,
    max_pages: int = 1,
    youtube: Resource | None = None,
    quota: QuotaTracker | None = None,
    order: str = "viewCount",
) -> list[dict[str, Any]]:
    """Search videos for a keyword.

    Returns one record per unique video with its 1-based ``search_rank``
    across pages. Each page costs one search.list call.
    """
    youtube = youtube or get_youtube_client()

    videos: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    rank = 0
    next_page_token = None

    for page in range(max_pages):

        logger.info("Searching keyword '%s', page %s", keyword, page + 1)

        request = youtube.search().list(
            part="snippet",
            q=keyword,
            type="video",
            maxResults=PAGE_SIZE,
            order=order,
            pageToken=next_page_token,
        )

        response = execute_with_retry(request)
        if quota:
            quota.record("search.list")

        for item in response.get("items", []):
            rank += 1
            video_id = item["id"]["videoId"]

            # Results can shift between pages; keep the best (first) rank.
            if video_id in seen_ids:
                continue
            seen_ids.add(video_id)

            snippet = item["snippet"]
            videos.append({
                "video_id": video_id,
                "channel_id": snippet["channelId"],
                "title": snippet["title"],
                "description": snippet["description"],
                "channel_title": snippet["channelTitle"],
                "published_at": snippet["publishedAt"],
                "keyword": keyword,
                "search_rank": rank,
                "raw_payload": item,
            })

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    logger.info(
        "Discovery completed. Retrieved %s videos for '%s'",
        len(videos),
        keyword,
    )

    return videos
