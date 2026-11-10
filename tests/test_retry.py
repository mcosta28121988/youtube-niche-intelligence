from unittest.mock import Mock

from src.api.retry import execute_with_retry


def test_execute_success():

    request = Mock()

    request.execute.return_value = {
        "items": []
    }

    result = execute_with_retry(request)

    assert result == {"items": []}

    request.execute.assert_called_once()