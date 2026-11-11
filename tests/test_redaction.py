import logging

from src.utils.redaction import REDACTED, RedactingFormatter, redact

FAKE_KEY = "AIza" + "x" * 35


def test_redacts_key_query_parameter_and_bare_keys():
    url = f"https://youtube.googleapis.com/youtube/v3/videos?part=snippet&key={FAKE_KEY}&alt=json"

    assert redact(url) == (
        f"https://youtube.googleapis.com/youtube/v3/videos?part=snippet&key={REDACTED}&alt=json"
    )
    assert FAKE_KEY not in redact(f"key is {FAKE_KEY}.")


def test_text_without_secrets_is_unchanged():
    text = "status=404 reasons=['notFound'] monkey=1"
    assert redact(text) == text


def test_formatter_redacts_exception_tracebacks():
    try:
        raise RuntimeError(f"request failed: https://x/videos?key={FAKE_KEY}")
    except RuntimeError:
        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", None, True)
        import sys
        record.exc_info = sys.exc_info()

    output = RedactingFormatter("%(message)s").format(record)

    assert FAKE_KEY not in output
    assert REDACTED in output
