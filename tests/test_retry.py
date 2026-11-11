import json
from unittest.mock import Mock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError

from src.api.retry import backoff_seconds, execute_with_retry


def http_error(status: int, reason: str | None = None) -> HttpError:
    response = httplib2.Response({"status": status})
    content = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode() if reason else b""
    return HttpError(response, content)


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("src.api.retry.time.sleep") as sleep:
        yield sleep


def test_execute_success():
    request = Mock()
    request.execute.return_value = {"items": []}

    assert execute_with_retry(request) == {"items": []}
    request.execute.assert_called_once()


def test_retries_server_error_then_succeeds(no_sleep):
    request = Mock()
    request.execute.side_effect = [http_error(503), {"items": [1]}]

    assert execute_with_retry(request) == {"items": [1]}
    assert request.execute.call_count == 2
    no_sleep.assert_called_once()


def test_retries_network_timeout():
    request = Mock()
    request.execute.side_effect = [TimeoutError(), ConnectionError(), {"ok": True}]

    assert execute_with_retry(request) == {"ok": True}
    assert request.execute.call_count == 3


def test_retries_rate_limited_403():
    request = Mock()
    request.execute.side_effect = [http_error(403, "rateLimitExceeded"), {"ok": 1}]

    assert execute_with_retry(request) == {"ok": 1}


@pytest.mark.parametrize(
    "error",
    [http_error(400, "badRequest"), http_error(403, "quotaExceeded"), http_error(404)],
)
def test_permanent_errors_are_not_retried(error, no_sleep):
    request = Mock()
    request.execute.side_effect = error

    with pytest.raises(HttpError):
        execute_with_retry(request)

    request.execute.assert_called_once()
    no_sleep.assert_not_called()


def test_gives_up_after_max_attempts():
    request = Mock()
    request.execute.side_effect = http_error(500)

    with pytest.raises(HttpError):
        execute_with_retry(request, max_attempts=3)

    assert request.execute.call_count == 3


def test_backoff_grows_and_is_capped():
    assert 1 <= backoff_seconds(1) <= 2
    assert 4 <= backoff_seconds(3) <= 5
    assert 30 <= backoff_seconds(20) <= 31
