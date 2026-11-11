"""Command-line entry point for the YouTube ingestion pipeline.

Usage:
    python -m src.main                  # extract and load into Snowflake
    python -m src.main --no-load        # extract only (still uses API quota)
    python -m src.main --max-pages 2    # override pages per keyword
    python -m src.main --purge-only     # enforce retention, no API calls
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from config.settings import load_settings
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
    parser.add_argument(
        "--max-pages", type=int,
        help="Pages per keyword (overrides YOUTUBE_MAX_PAGES_PER_KEYWORD)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)

    try:
        settings = load_settings(max_pages_per_keyword=args.max_pages)

        if args.purge_only:
            run_retention(settings)
        else:
            run_pipeline(settings, load=not args.no_load)

    except Exception:
        logger.exception("Pipeline execution failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
