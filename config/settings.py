"""Central configuration for the YouTube ingestion pipeline.

Values come from environment variables (``.env``) with safe defaults. Search
keywords live in ``config/keywords.txt`` so they can be edited without code
changes. Importing this module loads ``.env`` from the project root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_KEYWORDS_FILE = PROJECT_ROOT / "config" / "keywords.txt"

# YouTube Data API default daily allocation (see docs/data_policy.md, section 5).
SEARCH_CALLS_DAILY_LIMIT = 100
QUOTA_UNITS_DAILY_LIMIT = 10_000

# Developer Policies III.E.4.b/d: Non-Authorized Data may be stored for at most
# 30 days. One day is reserved for Snowflake Time Travel, which retains deleted
# rows for 1 day, so purged data is fully gone within the 30-day limit.
MAX_RETENTION_DAYS = 29
DEFAULT_RETENTION_DAYS = 28

VALID_SEARCH_ORDERS = frozenset(
    {"date", "rating", "relevance", "title", "viewCount"}
)


@dataclass(frozen=True)
class PipelineSettings:
    """Validated runtime settings for one pipeline execution."""

    keywords: tuple[str, ...]
    max_pages_per_keyword: int = 1
    search_order: str = "viewCount"
    retention_days: int = DEFAULT_RETENTION_DAYS
    pipeline_name: str = "youtube_ingestion"

    def __post_init__(self) -> None:
        if not self.keywords:
            raise ValueError("At least one search keyword is required")
        if self.max_pages_per_keyword < 1:
            raise ValueError("max_pages_per_keyword must be at least 1")
        if self.search_order not in VALID_SEARCH_ORDERS:
            raise ValueError(
                f"search_order must be one of {sorted(VALID_SEARCH_ORDERS)}"
            )
        if not 1 <= self.retention_days <= MAX_RETENTION_DAYS:
            raise ValueError(
                f"retention_days must be between 1 and {MAX_RETENTION_DAYS} "
                "(YouTube Developer Policies III.E.4 - see docs/data_policy.md)"
            )
        if self.planned_search_calls > SEARCH_CALLS_DAILY_LIMIT:
            raise ValueError(
                f"{self.planned_search_calls} search calls planned "
                f"({len(self.keywords)} keywords x {self.max_pages_per_keyword} "
                f"pages) exceeds the daily limit of {SEARCH_CALLS_DAILY_LIMIT}"
            )

    @property
    def planned_search_calls(self) -> int:
        """Upper bound on search.list calls for one run."""
        return len(self.keywords) * self.max_pages_per_keyword

    def to_run_parameters(self) -> dict[str, Any]:
        """Run inputs recorded in CONTROL.PIPELINE_RUNS.RUN_PARAMETERS."""
        return {
            "keywords": list(self.keywords),
            "max_pages_per_keyword": self.max_pages_per_keyword,
            "search_order": self.search_order,
            "retention_days": self.retention_days,
        }


def read_keywords(path: Path) -> tuple[str, ...]:
    """Read one keyword per line; ignore blanks, ``#`` comments and duplicates."""
    if not path.is_file():
        raise FileNotFoundError(f"Keywords file not found: {path}")

    keywords: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        keyword = line.split("#", 1)[0].strip()
        if keyword and keyword.casefold() not in seen:
            seen.add(keyword.casefold())
            keywords.append(keyword)
    return tuple(keywords)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from error


def load_settings(**overrides: Any) -> PipelineSettings:
    """Build settings from the environment; non-None overrides win (e.g. CLI)."""
    keywords_file = Path(
        os.getenv("YOUTUBE_KEYWORDS_FILE") or DEFAULT_KEYWORDS_FILE
    )
    if not keywords_file.is_absolute():
        keywords_file = PROJECT_ROOT / keywords_file

    settings = PipelineSettings(
        keywords=read_keywords(keywords_file),
        max_pages_per_keyword=_env_int("YOUTUBE_MAX_PAGES_PER_KEYWORD", 1),
        search_order=os.getenv("YOUTUBE_SEARCH_ORDER") or "viewCount",
        retention_days=_env_int("YOUTUBE_RETENTION_DAYS", DEFAULT_RETENTION_DAYS),
    )

    applied = {key: value for key, value in overrides.items() if value is not None}
    return replace(settings, **applied) if applied else settings
