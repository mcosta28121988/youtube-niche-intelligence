"""Remove credentials from text before it is logged or stored.

The Google API client puts the API key in the request URL (``?key=...``) and
``HttpError`` messages include that URL, so any error text can carry the key.
"""

from __future__ import annotations

import logging
import re

REDACTED = "REDACTED"

# key=... in a query string, and bare Google API keys anywhere.
_PATTERNS = (
    re.compile(r"([?&]key=)[^&\s\"'<>]+"),
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
)


def redact(text: str) -> str:
    """Return ``text`` with API keys replaced by ``REDACTED``."""
    text = _PATTERNS[0].sub(rf"\g<1>{REDACTED}", text)
    return _PATTERNS[1].sub(REDACTED, text)


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts the whole record, including tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))
