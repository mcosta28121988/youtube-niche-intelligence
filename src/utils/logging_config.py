import logging
import sys

from config.settings import PROJECT_ROOT
from src.utils.redaction import RedactingFormatter

LOG_DIRECTORY = PROJECT_ROOT / "logs"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

# Third-party libraries that are very chatty at INFO level.
NOISY_LOGGERS = ("snowflake", "googleapiclient", "urllib3", "botocore")


def use_utf8_console() -> None:
    """Print UTF-8 to the console instead of the Windows code page.

    Video titles contain emoji and non-Latin scripts; the default Windows
    console encoding (cp1252) raises UnicodeEncodeError on them.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def setup_logging(level: int = logging.INFO) -> None:
    """Log to logs/pipeline.log and the console; quieten third-party loggers.

    Every handler redacts API keys, including those inside exception
    tracebacks (HttpError messages contain the request URL with ?key=).
    """
    use_utf8_console()
    LOG_DIRECTORY.mkdir(exist_ok=True)

    handlers: list[logging.Handler] = [
        logging.FileHandler(LOG_DIRECTORY / "pipeline.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
    for handler in handlers:
        handler.setFormatter(RedactingFormatter(LOG_FORMAT))

    logging.basicConfig(level=level, handlers=handlers, force=True)

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
