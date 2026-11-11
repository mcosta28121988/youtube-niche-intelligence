from unittest.mock import MagicMock, patch

import pytest

from config.settings import PipelineSettings, SearchSpec
from src.ingestion import pipeline
from src.warehouse.pipeline_runs import RunStatus

SETTINGS = PipelineSettings(searches=(
    SearchSpec("kw1", region_code="AU", duration="long"),
    SearchSpec("kw2", name="kw2 - education", category="Education"),
))


def discovery(video_id: str, channel_id: str, keyword: str) -> dict:
    return {"video_id": video_id, "channel_id": channel_id, "keyword": keyword}


@pytest.fixture
def mocks():
    with (
        patch.object(pipeline, "get_youtube_client"),
        patch.object(pipeline, "get_snowflake_connection") as connect,
        patch.object(pipeline, "PipelineRunTracker") as tracker_cls,
        patch.object(pipeline, "purge_expired", return_value={}) as purge,
        patch.object(pipeline, "load_run", return_value={}) as load,
        patch.object(pipeline, "search_videos") as search,
        patch.object(pipeline, "trending_videos") as trending,
        patch.object(pipeline, "get_video_statistics") as videos,
        patch.object(pipeline, "get_channel_statistics") as channels,
        patch.object(pipeline, "CategoryResolver") as resolver_cls,
    ):
        resolver_cls.return_value.resolve.side_effect = (
            lambda category, region: "27" if category else None
        )
        search.side_effect = lambda keyword, **kw: [
            discovery("v1", "c1", keyword),
            discovery("v2" if keyword == "kw1" else "v3", "c2", keyword),
        ]
        trending.side_effect = lambda **kw: [
            {"video_id": "v9", "channel_id": "c9", "keyword": None},
        ]
        videos.side_effect = lambda ids, **kw: [
            {"video_id": i, "channel_id": "c1" if i == "v1" else "c2"} for i in ids
        ]
        channels.side_effect = lambda ids, **kw: [{"channel_id": i} for i in ids]
        yield {
            "connect": connect,
            "tracker": tracker_cls.return_value,
            "purge": purge,
            "load": load,
            "search": search,
            "trending": trending,
            "videos": videos,
            "channels": channels,
        }


def test_successful_run_loads_and_records_metrics(mocks):
    result = pipeline.run_pipeline(SETTINGS)

    # discovery keeps one row per keyword x video; enrichment dedupes IDs
    assert mocks["videos"].call_args.args[0] == ["v1", "v2", "v3"]
    assert mocks["channels"].call_args.args[0] == ["c1", "c2"]
    assert result.metrics.videos_discovered == 3
    assert result.metrics.channels_extracted == 2

    batches = mocks["load"].call_args.args[2]
    assert [len(rows) for _, rows in batches] == [4, 3, 2]
    assert all("extracted_at" in row for _, rows in batches for row in rows)

    discovery_rows = batches[0][1]
    assert {r["search_name"] for r in discovery_rows} == {"kw1", "kw2 - education"}
    kw1_filters = next(r["search_filters"] for r in discovery_rows if r["search_name"] == "kw1")
    assert kw1_filters["q"] == "kw1"
    assert kw1_filters["regionCode"] == "AU"
    assert kw1_filters["videoDuration"] == "long"
    kw2_filters = next(r["search_filters"] for r in discovery_rows if r["search_name"] != "kw1")
    assert kw2_filters["videoCategoryId"] == "27"

    mocks["purge"].assert_called_once()
    mocks["tracker"].start.assert_called_once()
    status, metrics = mocks["tracker"].finish.call_args.args[:2]
    assert status is RunStatus.SUCCEEDED
    mocks["connect"].return_value.close.assert_called_once()


def test_failed_run_is_recorded_and_reraised(mocks):
    mocks["videos"].side_effect = RuntimeError("API down")

    with pytest.raises(RuntimeError):
        pipeline.run_pipeline(SETTINGS)

    args = mocks["tracker"].finish.call_args.args
    assert args[0] is RunStatus.FAILED
    assert "API down" in args[2]
    assert args[1].videos_discovered == 3  # partial progress kept
    mocks["purge"].assert_called_once()  # retention ran before extraction
    mocks["load"].assert_not_called()
    mocks["connect"].return_value.close.assert_called_once()


def test_no_load_mode_never_touches_snowflake(mocks):
    result = pipeline.run_pipeline(SETTINGS, load=False)

    mocks["connect"].assert_not_called()
    mocks["load"].assert_not_called()
    assert result.metrics.videos_enriched == 3


def test_category_only_search_and_trending_chart(mocks):
    settings = PipelineSettings(searches=(
        SearchSpec("kw1"),
        SearchSpec(category="Education", region_code="AU"),
        SearchSpec(source="trending", category="24", region_code="AU"),
    ))

    pipeline.run_pipeline(settings)

    category_call = mocks["search"].call_args_list[1].kwargs
    assert category_call["keyword"] is None
    assert category_call["filters"]["videoCategoryId"] == "27"
    assert mocks["trending"].call_args.kwargs["filters"] == {
        "regionCode": "AU", "videoCategoryId": "24",
    }

    rows = mocks["load"].call_args.args[2][0][1]
    by_name = {r["search_name"]: r for r in rows}
    assert by_name["kw1"]["search_source"] == "search"
    assert "q" not in by_name["search: Education (AU)"]["search_filters"]
    trending_row = by_name["trending: 24 (AU)"]
    assert trending_row["search_source"] == "trending"
    assert trending_row["search_filters"]["chart"] == "mostPopular"
    assert "v9" in mocks["videos"].call_args.args[0]
