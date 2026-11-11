from unittest.mock import MagicMock

import pytest

from src.api.categories import (
    CategoryResolver,
    VideoCategory,
    find_category_id,
    list_video_categories,
)
from src.api.quota import QuotaTracker

CATEGORIES = [
    VideoCategory("27", "Education", True),
    VideoCategory("28", "Science & Technology", True),
    VideoCategory("30", "Movies", False),
]


def youtube_with_categories() -> MagicMock:
    youtube = MagicMock()
    youtube.videoCategories.return_value.list.return_value.execute.return_value = {
        "items": [
            {"id": c.id, "snippet": {"title": c.title, "assignable": c.assignable}}
            for c in CATEGORIES
        ]
    }
    return youtube


def test_list_video_categories_parses_and_counts_quota():
    youtube = youtube_with_categories()
    quota = QuotaTracker()

    categories = list_video_categories(youtube, "AU", quota=quota)

    assert categories == CATEGORIES
    youtube.videoCategories.return_value.list.assert_called_once_with(
        part="snippet", regionCode="AU", hl="en"
    )
    assert quota.units == 1


@pytest.mark.parametrize("value", ["education", "EDUCATION", " Education ", "27"])
def test_find_category_by_name_or_id(value):
    assert find_category_id(value, CATEGORIES) == "27"


@pytest.mark.parametrize("value", ["Cooking", "Movies"])
def test_unknown_or_non_searchable_category_lists_options(value):
    with pytest.raises(ValueError, match="Education \\(27\\)"):
        find_category_id(value, CATEGORIES)


def test_resolver_fetches_each_region_once_and_skips_ids():
    youtube = youtube_with_categories()
    resolver = CategoryResolver(youtube)

    assert resolver.resolve(None, "AU") is None
    assert resolver.resolve("24", "AU") == "24"  # IDs need no API call
    youtube.videoCategories.assert_not_called()

    assert resolver.resolve("Education", "AU") == "27"
    assert resolver.resolve("science & technology", "AU") == "28"
    assert youtube.videoCategories.return_value.list.call_count == 1

    resolver.resolve("Education", None)  # falls back to US
    assert youtube.videoCategories.return_value.list.call_count == 2
