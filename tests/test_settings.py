from datetime import UTC, datetime

import pytest

from config.settings import (
    DEFAULT_SEARCH_CONFIG,
    MAX_RETENTION_DAYS,
    SEARCH_CALLS_DAILY_LIMIT,
    PipelineSettings,
    SearchSpec,
    load_settings,
    read_search_config,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def write_config(tmp_path, text: str):
    path = tmp_path / "searches.toml"
    path.write_text(text, encoding="utf-8")
    return path


# --- SearchSpec ---------------------------------------------------------------


def test_name_defaults_to_keyword_and_is_stripped():
    spec = SearchSpec(keyword="  space documentary ")

    assert spec.keyword == "space documentary"
    assert spec.name == "space documentary"


def test_api_parameters_maps_filters_and_omits_any():
    spec = SearchSpec(
        keyword="kw",
        duration="long",
        published_within_days=7,
        region_code="AU",
        relevance_language="en",
        definition="any",
        caption="closedCaption",
        category="27",
    )

    assert spec.api_parameters(now=NOW) == {
        "order": "viewCount",
        "videoDuration": "long",
        "videoCaption": "closedCaption",
        "safeSearch": "moderate",
        "regionCode": "AU",
        "relevanceLanguage": "en",
        "publishedAfter": "2026-11-04T12:00:00Z",
        "videoCategoryId": "27",
    }


def test_category_name_requires_resolved_id():
    spec = SearchSpec(keyword="kw", category="Education")

    with pytest.raises(ValueError, match="resolved"):
        spec.api_parameters()
    assert spec.api_parameters(category_id="27")["videoCategoryId"] == "27"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"duration": "4min"}, "duration"),
        ({"order": "popularity"}, "order"),
        ({"region_code": "au"}, "region_code"),
        ({"region_code": "AUS"}, "region_code"),
        ({"relevance_language": "English"}, "relevance_language"),
        ({"published_within_days": 0}, "published_within_days"),
        ({"max_pages": 0}, "max_pages"),
        ({"event_type": "any"}, "event_type"),
        ({"keyword": "  "}, "keyword"),
    ],
)
def test_invalid_search_values_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        SearchSpec(**{"keyword": "kw", **kwargs})


# --- PipelineSettings ------------------------------------------------------------


def test_duplicate_search_names_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        PipelineSettings(searches=(SearchSpec("kw"), SearchSpec("KW")))


def test_same_keyword_allowed_with_distinct_names():
    settings = PipelineSettings(
        searches=(SearchSpec("kw"), SearchSpec("kw", name="kw - education"))
    )

    assert settings.planned_search_calls == 2


@pytest.mark.parametrize("days", [0, MAX_RETENTION_DAYS + 1, 30, 365])
def test_retention_outside_policy_window_is_rejected(days):
    with pytest.raises(ValueError, match="retention_days"):
        PipelineSettings(searches=(SearchSpec("kw"),), retention_days=days)


def test_search_call_budget_is_enforced():
    searches = tuple(SearchSpec(f"kw{i}", max_pages=2) for i in range(51))

    assert SEARCH_CALLS_DAILY_LIMIT < 51 * 2
    with pytest.raises(ValueError, match="daily limit"):
        PipelineSettings(searches=searches)


def test_with_max_pages_overrides_every_search_and_revalidates():
    settings = PipelineSettings(searches=(SearchSpec("a"), SearchSpec("b")))

    assert settings.with_max_pages(3).planned_search_calls == 6
    with pytest.raises(ValueError):
        settings.with_max_pages(60)


def test_run_parameters_record_every_filter():
    params = PipelineSettings(searches=(SearchSpec("kw", region_code="AU"),)).to_run_parameters()

    assert params["retention_days"] == 28
    assert params["searches"][0]["region_code"] == "AU"
    assert params["searches"][0]["name"] == "kw"


# --- TOML loading ----------------------------------------------------------------


def test_defaults_merge_into_searches_with_overrides(tmp_path):
    path = write_config(
        tmp_path,
        """
        [defaults]
        region_code = "AU"
        duration = "long"

        [[searches]]
        keyword = "history documentary"

        [[searches]]
        name = "space - science"
        keyword = "space documentary"
        duration = "medium"
        category = 28
    """,
    )

    first, second = read_search_config(path)

    assert (first.region_code, first.duration) == ("AU", "long")
    assert (second.region_code, second.duration) == ("AU", "medium")
    assert second.category == "28"  # integers in TOML become ID strings
    assert second.name == "space - science"


@pytest.mark.parametrize(
    "text, message",
    [
        ('[defaults]\nregoin_code = "AU"\n[[searches]]\nkeyword = "a"', "regoin_code"),
        ('[defaults]\nkeyword = "a"\n[[searches]]\nkeyword = "b"', "keyword"),
        ('[[searches]]\nname = "no keyword"', "keyword, a category, or both"),
        ('[defaults]\nregion_code = "AU"', "No \\[\\[searches\\]\\]"),
        ('[filters]\nx = 1\n[[searches]]\nkeyword = "a"', "filters"),
        ('[[searches]\nkeyword = "a"', "Invalid TOML"),
    ],
)
def test_config_errors_are_reported_clearly(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        read_search_config(write_config(tmp_path, text))


def test_missing_config_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_search_config(tmp_path / "missing.toml")


def test_repository_config_is_valid():
    searches = read_search_config(DEFAULT_SEARCH_CONFIG)

    assert searches
    assert all(s.region_code == "AU" for s in searches)


def test_load_settings_uses_env_path_and_cli_override(tmp_path, monkeypatch):
    path = write_config(tmp_path, '[[searches]]\nkeyword = "a"\n[[searches]]\nkeyword = "b"')
    monkeypatch.setenv("YOUTUBE_SEARCH_CONFIG", str(path))
    monkeypatch.setenv("YOUTUBE_RETENTION_DAYS", "7")

    settings = load_settings(max_pages=2)

    assert [s.keyword for s in settings.searches] == ["a", "b"]
    assert settings.retention_days == 7
    assert settings.planned_search_calls == 4


def test_load_settings_rejects_non_integer_env(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "YOUTUBE_SEARCH_CONFIG", str(write_config(tmp_path, '[[searches]]\nkeyword = "a"'))
    )
    monkeypatch.setenv("YOUTUBE_RETENTION_DAYS", "two weeks")

    with pytest.raises(ValueError, match="YOUTUBE_RETENTION_DAYS"):
        load_settings()


# --- Category-only searches and trending charts --------------------------------


def test_category_only_search_is_valid_and_sends_no_keyword():
    spec = SearchSpec(category="27", region_code="AU")

    assert spec.keyword is None
    assert spec.name == "search: 27 (AU)"
    assert spec.api_parameters()["videoCategoryId"] == "27"


def test_search_needs_keyword_or_category():
    with pytest.raises(ValueError, match="keyword, a category, or both"):
        SearchSpec(region_code="AU")


def test_trending_chart_parameters_and_default_name():
    spec = SearchSpec(source="trending", category="Education", region_code="AU")

    assert spec.name == "trending: Education (AU)"
    assert spec.api_parameters(category_id="27") == {
        "regionCode": "AU",
        "videoCategoryId": "27",
    }


def test_trending_without_category_reads_the_overall_chart():
    assert SearchSpec(source="trending").api_parameters() == {}


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"keyword": "kw"}, "keyword"),
        ({"duration": "long"}, "duration"),
        ({"published_within_days": 7}, "published_within_days"),
        ({"max_pages": 5}, "max_pages"),
        ({"source": "chart"}, "source"),
    ],
)
def test_invalid_trending_values_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        SearchSpec(**{"source": "trending", **kwargs})


def test_trending_pages_do_not_count_against_search_budget():
    settings = PipelineSettings(
        searches=(
            SearchSpec("kw", max_pages=2),
            SearchSpec(source="trending", max_pages=4),
        )
    )

    assert settings.planned_search_calls == 2
    assert settings.planned_trending_units == 4
    capped = settings.with_max_pages(10)
    assert [s.max_pages for s in capped.searches] == [10, 4]


def test_trending_entries_ignore_search_only_defaults(tmp_path):
    path = write_config(
        tmp_path,
        """
        [defaults]
        region_code = "AU"
        duration = "long"
        published_within_days = 7

        [[searches]]
        category = "Education"

        [[searches]]
        source = "trending"
        category = 24
    """,
    )

    category_search, trending = read_search_config(path)

    assert category_search.keyword is None
    assert category_search.duration == "long"
    assert trending.source == "trending"
    assert (trending.region_code, trending.duration) == ("AU", "any")
    assert trending.published_within_days is None


def test_trending_entry_with_explicit_search_filter_is_rejected(tmp_path):
    path = write_config(tmp_path, '[[searches]]\nsource = "trending"\nduration = "long"')

    with pytest.raises(ValueError, match=r"#1.*duration"):
        read_search_config(path)
