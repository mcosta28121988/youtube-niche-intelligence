"""YouTube Data API v3 client factory."""

from __future__ import annotations

import os

import httplib2
from googleapiclient.discovery import Resource, build

import config.settings  # noqa: F401  (loads .env from the project root)

REQUEST_TIMEOUT_SECONDS = 30


def get_youtube_client() -> Resource:
    """Build an API-key authenticated client with a per-request timeout."""
    api_key = os.getenv("YOUTUBE_API_KEY")

    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is missing from .env")

    return build(
        "youtube",
        "v3",
        developerKey=api_key,
        http=httplib2.Http(timeout=REQUEST_TIMEOUT_SECONDS),
        cache_discovery=False,
    )
