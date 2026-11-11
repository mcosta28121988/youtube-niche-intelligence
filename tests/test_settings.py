import pytest

from config.settings import (
    MAX_RETENTION_DAYS,
    SEARCH_CALLS_DAILY_LIMIT,
    PipelineSettings,
    load_settings,
    read_keywords,
)


def test_read_keywords_ignores_comments_blanks_and_duplicates(tmp_path):
    path = tmp_path / "keywords.txt"
    path.write_text(
        "# comment\n\nhistory documentary\nSpace Documentary  # inline\n"
        "History Documentary\n",
        encoding="utf-8",
    )

    assert read_keywords(path) == ("history documentary", "Space Documentary")


def test_read_keywords_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_keywords(tmp_path / "missing.txt")


@pytest.mark.parametrize("days", [0, MAX_RETENTION_DAYS + 1, 30, 365])
def test_retention_outside_policy_window_is_rejected(days):
    with pytest.raises(ValueError, match="retention_days"):
        PipelineSettings(keywords=("a",), retention_days=days)


def test_search_call_budget_is_enforced():
    keywords = tuple(f"kw{i}" for i in range(SEARCH_CALLS_DAILY_LIMIT // 2 + 1))

    with pytest.raises(ValueError, match="daily limit"):
        PipelineSettings(keywords=keywords, max_pages_per_keyword=2)


@pytest.mark.parametrize(
    "kwargs",
    [{"keywords": ()}, {"max_pages_per_keyword": 0}, {"search_order": "views"}],
)
def test_invalid_settings_rejected(kwargs):
    with pytest.raises(ValueError):
        PipelineSettings(**{"keywords": ("a",), **kwargs})


def test_load_settings_reads_env_and_applies_overrides(tmp_path, monkeypatch):
    path = tmp_path / "kw.txt"
    path.write_text("alpha\nbeta\n", encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_KEYWORDS_FILE", str(path))
    monkeypatch.setenv("YOUTUBE_MAX_PAGES_PER_KEYWORD", "2")
    monkeypatch.setenv("YOUTUBE_RETENTION_DAYS", "7")
    monkeypatch.delenv("YOUTUBE_SEARCH_ORDER", raising=False)

    settings = load_settings(max_pages_per_keyword=3, search_order=None)

    assert settings.keywords == ("alpha", "beta")
    assert settings.max_pages_per_keyword == 3  # override wins
    assert settings.retention_days == 7
    assert settings.search_order == "viewCount"
    assert settings.planned_search_calls == 6


def test_load_settings_rejects_non_integer_env(tmp_path, monkeypatch):
    path = tmp_path / "kw.txt"
    path.write_text("alpha\n", encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_KEYWORDS_FILE", str(path))
    monkeypatch.setenv("YOUTUBE_RETENTION_DAYS", "two weeks")

    with pytest.raises(ValueError, match="YOUTUBE_RETENTION_DAYS"):
        load_settings()


def test_run_parameters_are_json_friendly():
    settings = PipelineSettings(keywords=("a", "b"))

    assert settings.to_run_parameters() == {
        "keywords": ["a", "b"],
        "max_pages_per_keyword": 1,
        "search_order": "viewCount",
        "retention_days": 28,
    }
