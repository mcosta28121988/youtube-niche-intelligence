"""Central configuration for the YouTube ingestion pipeline.

Search definitions (keyword/category searches and trending charts) live in
``config/searches.toml``. Operational settings come from environment
variables (``.env``). Importing this module loads ``.env`` from the project
root.

``SearchSpec`` and ``PipelineSettings`` are the validated domain model; the
TOML file is just one way to populate them, so a future UI can reuse the same
validation by constructing these objects directly.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_SEARCH_CONFIG = PROJECT_ROOT / "config" / "searches.toml"

# YouTube Data API default daily allocation (see docs/data_policy.md, section 5).
SEARCH_CALLS_DAILY_LIMIT = 100
QUOTA_UNITS_DAILY_LIMIT = 10_000

# Developer Policies III.E.4.b/d: Non-Authorized Data may be stored for at most
# 30 days. One day is reserved for Snowflake Time Travel, which retains deleted
# rows for 1 day, so purged data is fully gone within the 30-day limit.
MAX_RETENTION_DAYS = 29
DEFAULT_RETENTION_DAYS = 28

# Allowed values per filter, mirroring search.list.
ALLOWED_VALUES: dict[str, frozenset[str]] = {
    "order": frozenset({"date", "rating", "relevance", "title", "viewCount"}),
    "duration": frozenset({"any", "short", "medium", "long"}),
    "definition": frozenset({"any", "high", "standard"}),
    "caption": frozenset({"any", "closedCaption", "none"}),
    "license": frozenset({"any", "creativeCommon", "youtube"}),
    "video_type": frozenset({"any", "episode", "movie"}),
    "dimension": frozenset({"any", "2d", "3d"}),
    "event_type": frozenset({"completed", "live", "upcoming"}),
    "safe_search": frozenset({"moderate", "none", "strict"}),
}

# Config field -> search.list parameter name.
API_PARAMETERS: dict[str, str] = {
    "order": "order",
    "duration": "videoDuration",
    "definition": "videoDefinition",
    "caption": "videoCaption",
    "license": "videoLicense",
    "video_type": "videoType",
    "dimension": "videoDimension",
    "event_type": "eventType",
    "safe_search": "safeSearch",
    "region_code": "regionCode",
    "relevance_language": "relevanceLanguage",
}

# Discovery sources:
#   search   - search.list; keyword and/or category plus filters. Each page
#              uses 1 of the 100 daily search calls.
#   trending - videos.list chart=mostPopular for a region (and optionally a
#              category). Each page costs 1 quota unit; the chart holds at
#              most 200 videos.
SOURCES = frozenset({"search", "trending"})
TRENDING_MAX_PAGES = 4

# Fields the trending chart understands; everything else is search-only.
TRENDING_FIELDS = frozenset({"source", "name", "max_pages", "region_code", "category"})

REGION_PATTERN = re.compile(r"^[A-Z]{2}$")
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


@dataclass(frozen=True)
class SearchSpec:
    """One configured discovery: a filtered search or a trending chart.

    A ``search`` needs a keyword, a category, or both. A ``trending`` chart
    takes only region_code and category.
    """

    keyword: str | None = None
    name: str = ""  # unique label; defaults to the keyword or source+category
    source: str = "search"
    max_pages: int = 1
    order: str = "viewCount"
    duration: str = "any"
    published_within_days: int | None = None
    region_code: str | None = None
    relevance_language: str | None = None
    category: str | None = None  # category ID ("27") or name ("Education")
    definition: str = "any"
    caption: str = "any"
    license: str = "any"
    video_type: str = "any"
    dimension: str = "any"
    event_type: str | None = None
    safe_search: str = "moderate"

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise ValueError(
                f"source={self.source!r} is invalid; use one of {sorted(SOURCES)}"
            )
        if self.keyword is not None:
            keyword = str(self.keyword).strip()
            if not keyword:
                raise ValueError("Search keyword must not be empty")
            object.__setattr__(self, "keyword", keyword)
        if self.category is not None:
            category = str(self.category).strip()
            if not category:
                raise ValueError("Search category must not be empty")
            object.__setattr__(self, "category", category)
        object.__setattr__(self, "name", (self.name or self._default_name()).strip())

        label = f"Search '{self.name}'"
        if self.source == "search" and self.keyword is None and self.category is None:
            raise ValueError(f"{label}: a search needs a keyword, a category, or both")
        if self.source == "trending":
            unsupported = [
                f.name for f in fields(self)
                if f.name not in TRENDING_FIELDS and getattr(self, f.name) != f.default
            ]
            if unsupported:
                raise ValueError(
                    f"{label}: {', '.join(unsupported)} not supported by the "
                    "trending chart (only region_code and category apply)"
                )
            if self.max_pages > TRENDING_MAX_PAGES:
                raise ValueError(
                    f"{label}: the trending chart holds at most "
                    f"{TRENDING_MAX_PAGES * 50} videos; max_pages must be "
                    f"<= {TRENDING_MAX_PAGES}"
                )
        if self.max_pages < 1:
            raise ValueError(f"{label}: max_pages must be at least 1")
        for field_name, allowed in ALLOWED_VALUES.items():
            value = getattr(self, field_name)
            if value is not None and value not in allowed:
                raise ValueError(
                    f"{label}: {field_name}={value!r} is invalid; "
                    f"use one of {sorted(allowed)}"
                )
        if self.published_within_days is not None and self.published_within_days < 1:
            raise ValueError(f"{label}: published_within_days must be at least 1")
        if self.region_code is not None and not REGION_PATTERN.match(self.region_code):
            raise ValueError(
                f"{label}: region_code must be a 2-letter upper-case ISO code, e.g. 'AU'"
            )
        if (
            self.relevance_language is not None
            and not LANGUAGE_PATTERN.match(self.relevance_language)
        ):
            raise ValueError(
                f"{label}: relevance_language must be an ISO 639-1 code, e.g. 'en'"
            )

    def _default_name(self) -> str:
        if self.source == "search" and self.keyword:
            return self.keyword
        name = f"{self.source}: {self.category or 'all categories'}"
        return f"{name} ({self.region_code})" if self.region_code else name

    @property
    def category_is_id(self) -> bool:
        return self.category is not None and self.category.isdigit()

    def api_parameters(
        self,
        category_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, str]:
        """API filter parameters (excluding q, chart, part, type and paging).

        For ``search`` these are search.list filters; for ``trending`` they
        are the videos.list chart filters (regionCode, videoCategoryId).
        ``category_id`` must be supplied when ``category`` is a name; it is
        resolved against the live category list (see src/api/categories.py).
        """
        params: dict[str, str] = {}
        for field_name, api_name in API_PARAMETERS.items():
            if self.source == "trending" and field_name not in TRENDING_FIELDS:
                continue
            value = getattr(self, field_name)
            if value is not None and value != "any":
                params[api_name] = value

        if self.published_within_days is not None:
            now = now or datetime.now(timezone.utc)
            published_after = now - timedelta(days=self.published_within_days)
            params["publishedAfter"] = published_after.strftime("%Y-%m-%dT%H:%M:%SZ")

        if self.category is not None:
            if self.category_is_id:
                params["videoCategoryId"] = self.category
            elif category_id:
                params["videoCategoryId"] = category_id
            else:
                raise ValueError(
                    f"Search '{self.name}': category {self.category!r} "
                    "must be resolved to an ID first"
                )
        return params


@dataclass(frozen=True)
class PipelineSettings:
    """Validated runtime settings for one pipeline execution."""

    searches: tuple[SearchSpec, ...]
    retention_days: int = DEFAULT_RETENTION_DAYS
    pipeline_name: str = "youtube_ingestion"

    def __post_init__(self) -> None:
        if not self.searches:
            raise ValueError("At least one search must be configured")

        seen: set[str] = set()
        for search in self.searches:
            key = search.name.casefold()
            if key in seen:
                raise ValueError(
                    f"Duplicate search name '{search.name}'; give each search "
                    "a unique 'name'"
                )
            seen.add(key)

        if not 1 <= self.retention_days <= MAX_RETENTION_DAYS:
            raise ValueError(
                f"retention_days must be between 1 and {MAX_RETENTION_DAYS} "
                "(YouTube Developer Policies III.E.4 - see docs/data_policy.md)"
            )
        if self.planned_search_calls > SEARCH_CALLS_DAILY_LIMIT:
            raise ValueError(
                f"{self.planned_search_calls} search calls planned exceeds the "
                f"daily limit of {SEARCH_CALLS_DAILY_LIMIT}"
            )

    @property
    def planned_search_calls(self) -> int:
        """Upper bound on search.list calls for one run."""
        return sum(s.max_pages for s in self.searches if s.source == "search")

    @property
    def planned_trending_units(self) -> int:
        """Upper bound on quota units used by trending charts for one run."""
        return sum(s.max_pages for s in self.searches if s.source == "trending")

    def with_max_pages(self, max_pages: int) -> PipelineSettings:
        """Copy with every search's max_pages overridden (e.g. from the CLI).

        Trending charts are capped at their maximum of TRENDING_MAX_PAGES.
        """
        def pages(search: SearchSpec) -> int:
            if search.source == "trending":
                return min(max_pages, TRENDING_MAX_PAGES)
            return max_pages

        return replace(
            self,
            searches=tuple(replace(s, max_pages=pages(s)) for s in self.searches),
        )

    def to_run_parameters(self) -> dict[str, Any]:
        """Run inputs recorded in CONTROL.PIPELINE_RUNS.RUN_PARAMETERS."""
        return {
            "retention_days": self.retention_days,
            "searches": [asdict(search) for search in self.searches],
        }


_SEARCH_FIELDS = frozenset(f.name for f in fields(SearchSpec))
_DEFAULT_FIELDS = _SEARCH_FIELDS - {"keyword", "name"}


def _check_keys(section: str, keys: set[str], allowed: frozenset[str]) -> None:
    unknown = sorted(keys - allowed)
    if unknown:
        raise ValueError(
            f"Unknown setting(s) in {section}: {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )


def read_search_config(path: Path) -> tuple[SearchSpec, ...]:
    """Parse searches.toml: ``[defaults]`` merged into each ``[[searches]]``.

    Trending entries only inherit the defaults the chart understands
    (region_code, category, max_pages), so search filters such as duration
    in ``[defaults]`` don't make them invalid.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Search config not found: {path}")

    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Invalid TOML in {path}: {error}") from error

    _check_keys(path.name, set(data), frozenset({"defaults", "searches"}))

    defaults = data.get("defaults", {})
    _check_keys("[defaults]", set(defaults), _DEFAULT_FIELDS)

    entries = data.get("searches", [])
    if not entries:
        raise ValueError(f"No [[searches]] defined in {path}")

    searches = []
    for position, entry in enumerate(entries, start=1):
        _check_keys(f"[[searches]] #{position}", set(entry), _SEARCH_FIELDS)
        inherited = defaults
        if entry.get("source", defaults.get("source")) == "trending":
            inherited = {k: v for k, v in defaults.items() if k in TRENDING_FIELDS}
        merged = {**inherited, **entry}
        if merged.get("category") is not None:
            merged["category"] = str(merged["category"])
        try:
            searches.append(SearchSpec(**merged))
        except ValueError as error:
            raise ValueError(f"[[searches]] #{position}: {error}") from error
    return tuple(searches)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from error


def load_settings(max_pages: int | None = None) -> PipelineSettings:
    """Build settings from searches.toml and the environment."""
    config_path = Path(os.getenv("YOUTUBE_SEARCH_CONFIG") or DEFAULT_SEARCH_CONFIG)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    settings = PipelineSettings(
        searches=read_search_config(config_path),
        retention_days=_env_int("YOUTUBE_RETENTION_DAYS", DEFAULT_RETENTION_DAYS),
    )
    return settings.with_max_pages(max_pages) if max_pages is not None else settings
