"""Helpers for converting YouTube API response values."""

from __future__ import annotations

from typing import Any


def optional_int(value: Any) -> int | None:
    """Convert an API count to int, keeping missing values as None.

    YouTube omits counts that are hidden (likes, subscribers) or disabled
    (comments). Those must stay NULL rather than become 0.
    """
    if value is None or value == "":
        return None
    return int(value)
