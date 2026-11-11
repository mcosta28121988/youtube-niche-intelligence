import json
from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from src.api.channel_extractor import get_channel_statistics
from src.api.quota import QuotaTracker
from src.api.video_extractor import get_video_statistics
from src.ingestion.discover_videos import search_videos, trending_videos


def search_item(video_id: str) -> dict:
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "channelId": "ch1",
            "title": f"Title {video_id}",
            "description": "desc",
            "channelTitle": "Channel",
            "publishedAt": "2026-01-01T00:00:00Z",
        },
    }


def test_search_ranks_across_pages_and_dedupes():
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute.side_effect = [
        {"items": [search_item("a"), search_item("b")], "nextPageToken": "p2"},
        {"items": [search_item("b"), search_item("c")]},
    ]
    quota = QuotaTracker()

    videos = search_videos("kw", max_pages=3, youtube=youtube, quota=quota)

    assert [(v["video_id"], v["search_rank"]) for v in videos] == [
        ("a", 1),
        ("b", 2),
        ("c", 4),
    ]
    assert videos[0]["raw_payload"] == search_item("a")
    assert videos[0]["keyword"] == "kw"
    assert quota.search_calls == 2  # stopped when no nextPageToken


def test_search_passes_filters_but_keeps_core_parameters():
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute.return_value = {"items": []}

    search_videos(
        "kw",
        youtube=youtube,
        filters={"order": "date", "regionCode": "AU", "videoDuration": "long", "type": "channel"},
    )

    kwargs = youtube.search.return_value.list.call_args.kwargs
    assert kwargs["order"] == "date"  # filters may override order
    assert kwargs["regionCode"] == "AU"
    assert kwargs["videoDuration"] == "long"
    assert kwargs["type"] == "video"  # core parameters cannot be overridden
    assert kwargs["q"] == "kw"


def test_video_hidden_counts_are_none_not_zero():
    youtube = MagicMock()
    item = {
        "id": "v1",
        "snippet": {"channelId": "ch1", "title": "T", "publishedAt": "2026-01-01T00:00:00Z"},
        "statistics": {"viewCount": "10"},  # likes hidden, comments disabled
        "contentDetails": {"duration": "PT1M"},
    }
    youtube.videos.return_value.list.return_value.execute.return_value = {"items": [item]}
    quota = QuotaTracker()

    [video] = get_video_statistics(["v1", "v1"], youtube=youtube, quota=quota)

    assert video["views"] == 10
    assert video["likes"] is None
    assert video["comments"] is None
    assert video["raw_payload"] == item
    assert quota.units == 1


def test_video_batches_of_fifty():
    youtube = MagicMock()
    youtube.videos.return_value.list.return_value.execute.return_value = {"items": []}
    quota = QuotaTracker()

    get_video_statistics([f"v{i}" for i in range(120)], youtube=youtube, quota=quota)

    assert quota.calls["videos.list"] == 3


def test_channel_hidden_subscriber_count_is_none():
    youtube = MagicMock()
    youtube.channels.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "ch1",
                "snippet": {"title": "C", "publishedAt": "2020-01-01T00:00:00Z"},
                "statistics": {
                    "viewCount": "500",
                    "videoCount": "5",
                    "subscriberCount": "0",
                    "hiddenSubscriberCount": True,
                },
                "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}},
            }
        ]
    }

    [channel] = get_channel_statistics(["ch1"], youtube=youtube)

    assert channel["subscribers"] is None
    assert channel["total_views"] == 500
    assert channel["uploads_playlist_id"] == "UU1"


def test_search_without_keyword_omits_q():
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute.return_value = {
        "items": [search_item("a")]
    }

    [video] = search_videos(youtube=youtube, filters={"videoCategoryId": "27"})

    kwargs = youtube.search.return_value.list.call_args.kwargs
    assert "q" not in kwargs
    assert kwargs["videoCategoryId"] == "27"
    assert video["keyword"] is None


def chart_item(video_id: str) -> dict:
    return {"id": video_id, **{k: v for k, v in search_item(video_id).items() if k != "id"}}


def test_trending_reads_chart_and_ranks_by_position():
    youtube = MagicMock()
    youtube.videos.return_value.list.return_value.execute.side_effect = [
        {"items": [chart_item("a"), chart_item("b")], "nextPageToken": "p2"},
        {"items": [chart_item("c")]},
    ]
    quota = QuotaTracker()

    videos = trending_videos(
        max_pages=4,
        youtube=youtube,
        quota=quota,
        filters={"regionCode": "AU", "videoCategoryId": "24"},
    )

    assert [(v["video_id"], v["search_rank"]) for v in videos] == [("a", 1), ("b", 2), ("c", 3)]
    assert videos[0]["keyword"] is None
    assert videos[0]["channel_id"] == "ch1"
    kwargs = youtube.videos.return_value.list.call_args.kwargs
    assert kwargs["chart"] == "mostPopular"
    assert kwargs["regionCode"] == "AU"
    assert quota.calls["videos.list"] == 2
    assert quota.search_calls == 0


def test_trending_missing_chart_is_skipped_not_fatal():
    youtube = MagicMock()
    content = json.dumps({"error": {"code": 404, "errors": [{"reason": "notFound"}]}}).encode()
    youtube.videos.return_value.list.return_value.execute.side_effect = HttpError(
        httplib2.Response({"status": 404}), content
    )

    assert trending_videos(youtube=youtube, filters={"videoCategoryId": "27"}) == []


def test_trending_other_errors_still_raise():
    youtube = MagicMock()
    content = json.dumps({"error": {"code": 403, "errors": [{"reason": "forbidden"}]}}).encode()
    youtube.videos.return_value.list.return_value.execute.side_effect = HttpError(
        httplib2.Response({"status": 403}), content
    )

    with pytest.raises(HttpError):
        trending_videos(youtube=youtube)
