import logging
import time

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

RETRYABLE_REASONS = {
    "rateLimitExceeded",
    "userRateLimitExceeded",
    "backendError"
}


def execute_with_retry(request, max_attempts=5):

    for attempt in range(1, max_attempts + 1):

        try:
            return request.execute()

        except HttpError as error:

            status = error.resp.status

            reasons = []

            if error.content:
                import json

                try:
                    payload = json.loads(error.content)
                    reasons = [
                        item.get("reason")
                        for item in payload.get(
                            "error", {}
                        ).get("errors", [])
                    ]
                except (ValueError, TypeError):
                    pass

            retryable = (
                status in RETRYABLE_STATUS_CODES
                or (
                    status == 403
                    and any(
                        reason in RETRYABLE_REASONS
                        for reason in reasons
                    )
                )
            )

            if not retryable or attempt == max_attempts:
                logger.exception(
                    "YouTube API request failed: status=%s",
                    status
                )
                raise

            wait_seconds = min(2 ** (attempt - 1), 30)

            logger.warning(
                "Temporary API error. "
                "Attempt %s/%s. Retrying in %s seconds.",
                attempt,
                max_attempts,
                wait_seconds
            )

            time.sleep(wait_seconds)