"""Command-line entry point for the YouTube ingestion pipeline.

Usage:
    python -m src.main                          # extract and load into Snowflake
    python -m src.main --no-load                # extract only (still uses API quota)
    python -m src.main --max-pages 2            # override pages for every search
    python -m src.main --purge-only             # enforce retention, no API calls
    python -m src.main --check-config           # validate searches.toml, no API calls
    python -m src.main --list-categories --region AU   # 1 quota unit
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from config.settings import PipelineSettings, load_settings
from src.api.categories import list_video_categories
from src.api.youtube_client import get_youtube_client
from src.ingestion.pipeline import run_pipeline, run_retention
from src.utils.logging_config import setup_logging

logger = logging.getLogger("pipeline")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YouTube ingestion pipeline")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--no-load", action="store_true",
        help="Extract from the API without writing to Snowflake",
    )
    mode.add_argument(
        "--purge-only", action="store_true",
        help="Only delete RAW rows older than the retention window",
    )
    mode.add_argument(
        "--check-config", action="store_true",
        help="Validate config/searches.toml and print the planned searches",
    )
    mode.add_argument(
        "--list-categories", action="store_true",
        help="List YouTube video categories for --region (1 quota unit)",
    )
    parser.add_argument(
        "--max-pages", type=int,
        help="Pages per search (overrides max_pages in searches.toml)",
    )
    parser.add_argument(
        "--region",
        help="Region for --list-categories (default: first search's region_code)",
    )
    return parser.parse_args(argv)


def print_plan(settings: PipelineSettings) -> None:
    print(f"\n{len(settings.searches)} searches, "
          f"up to {settings.planned_search_calls} search calls per run "
          f"(retention: {settings.retention_days} days)\n")
    for search in settings.searches:
        placeholder = None if search.category_is_id else f"<{search.category}>"
        params = search.api_parameters(category_id=placeholder)
        print(f"- {search.name}  (keyword: {search.keyword!r}, pages: {search.max_pages})")
        for key, value in params.items():
            print(f"      {key} = {value}")
    print("\nCategory names in <> are resolved against the live list at run time.")


def print_categories(region: str) -> None:
    categories = list_video_categories(get_youtube_client(), region)
    print(f"\nYouTube video categories for {region} (searchable ones usable in "
          "searches.toml as name or ID):\n")
    print(f"  {'ID':>4}  {'Category':<28} Searchable")
    for category in sorted(categories, key=lambda c: int(c.id)):
        print(f"  {category.id:>4}  {category.title:<28} "
              f"{'yes' if category.assignable else 'no'}")


def main(argv: Sequence[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)

    try:
        settings = load_settings(max_pages=args.max_pages)

        if args.check_config:
            print_plan(settings)
        elif args.list_categories:
            print_categories(
                args.region or settings.searches[0].region_code or "US"
            )
        elif args.purge_only:
            run_retention(settings)
        else:
            run_pipeline(settings, load=not args.no_load)

    except Exception:
        logger.exception("Pipeline execution failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
