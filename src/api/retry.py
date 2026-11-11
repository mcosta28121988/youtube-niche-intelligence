"""Retry YouTube API requests on transient failures with exponential backoff."""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Protocol

import httplib2
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

RETRYABLE_REASONS = {
    "rateLimitExceeded",
    "userRateLimitExceeded",
    "backendError",
}

# Network-level failures (timeouts, dropped connections, DNS) worth retrying.
TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    TimeoutError,
    ConnectionError,
    httplib2.HttpLib2Error,
)

MAX_BACKOFF_SECONDS = 30


class ExecutableRequest(Protocol):
    def execute(self) -> dict[str, Any]: ...


def error_reasons(error: HttpError) -> list[str]:
    """Extract the ``reason`` codes from a Google API error payload."""
    if not error.content:
        return []
    try:
        payload = json.loads(error.content)
    except (ValueError, TypeError):
        return []
    return [
        item.get("reason")
        for item in payload.get("error", {}).get("errors", [])
        if item.get("reason")
    ]


def is_retryable(error: HttpError) -> bool:
    status = error.resp.status
    if status in RETRYABLE_STATUS_CODES:
        return True
    # 403 is usually permanent (e.g. quotaExceeded), except rate limiting.
    return status == 403 and any(
        reason in RETRYABLE_REASONS for reason in error_reasons(error)
    )


def backoff_seconds(attempt: int) -> float:
    """Exponential backoff (1, 2, 4 ... capped) plus up to 1s of jitter."""
    return min(2 ** (attempt - 1), MAX_BACKOFF_SECONDS) + random.uniform(0, 1)  # noqa: S311 - jitter, not crypto


def execute_with_retry(
    request: ExecutableRequest,
    max_attempts: int = 5,
) -> dict[str, Any]:
    """Execute a request, retrying transient HTTP and network errors."""
    for attempt in range(1, max_attempts + 1):
        try:
            return request.execute()

        except HttpError as error:
            status = error.resp.status
            reasons = error_reasons(error)

            if not is_retryable(error) or attempt == max_attempts:
                if "quotaExceeded" in reasons:
                    logger.error(
                        "YouTube API daily quota exhausted; it resets at "
                        "midnight Pacific Time"
                    )
                logger.error(
                    "YouTube API request failed: status=%s reasons=%s "
                    "attempt=%s/%s",
                    status, reasons, attempt, max_attempts,
                )
                raise
            cause = f"HTTP {status}"

        except TRANSIENT_EXCEPTIONS as error:
            if attempt == max_attempts:
                logger.error(
                    "YouTube API request failed after %s attempts: %s",
                    max_attempts, type(error).__name__,
                )
                raise
            cause = type(error).__name__

        wait_seconds = backoff_seconds(attempt)
        logger.warning(
            "Transient YouTube API error (%s). Attempt %s/%s. "
            "Retrying in %.1f seconds.",
            cause, attempt, max_attempts, wait_seconds,
        )
        time.sleep(wait_seconds)

    raise RuntimeError("unreachable")  # pragma: no cover
