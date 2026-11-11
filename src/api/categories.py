"""YouTube video categories (videoCategories.list) and name resolution.

Category titles are YouTube API data, so they are fetched live (1 quota unit
per region) rather than stored in the repository.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from googleapiclient.discovery import Resource

from src.api.quota import QuotaTracker
from src.api.retry import execute_with_retry

logger = logging.getLogger(__name__)

DEFAULT_REGION = "US"


@dataclass(frozen=True)
class VideoCategory:
    id: str
    title: str
    assignable: bool  # only assignable categories are used by videos


def list_video_categories(
    youtube: Resource,
    region_code: str = DEFAULT_REGION,
    quota: QuotaTracker | None = None,
    language: str = "en",
) -> list[VideoCategory]:
    """Fetch the video categories available in a region."""
    request = youtube.videoCategories().list(
        part="snippet",
        regionCode=region_code,
        hl=language,
    )
    response = execute_with_retry(request)
    if quota:
        quota.record("videoCategories.list")

    return [
        VideoCategory(
            id=item["id"],
            title=item["snippet"]["title"],
            assignable=bool(item["snippet"].get("assignable")),
        )
        for item in response.get("items", [])
    ]


def find_category_id(category: str, categories: list[VideoCategory]) -> str:
    """Resolve a category name (case-insensitive) or ID to an assignable ID."""
    usable = [c for c in categories if c.assignable]
    wanted = category.strip().casefold()
    for candidate in usable:
        if wanted in (candidate.id, candidate.title.casefold()):
            return candidate.id
    options = ", ".join(f"{c.title} ({c.id})" for c in usable)
    raise ValueError(f"Unknown or non-searchable category {category!r}. Options: {options}")


class CategoryResolver:
    """Resolves category names to IDs, fetching each region's list once."""

    def __init__(self, youtube: Resource, quota: QuotaTracker | None = None) -> None:
        self.youtube = youtube
        self.quota = quota
        self._cache: dict[str, list[VideoCategory]] = {}

    def resolve(self, category: str | None, region_code: str | None) -> str | None:
        if category is None:
            return None
        if category.isdigit():
            return category
        region = region_code or DEFAULT_REGION
        if region not in self._cache:
            self._cache[region] = list_video_categories(self.youtube, region, quota=self.quota)
        category_id = find_category_id(category, self._cache[region])
        logger.info("Category '%s' resolved to ID %s (%s)", category, category_id, region)
        return category_id
