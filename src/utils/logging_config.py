import logging

from config.settings import PROJECT_ROOT
from src.utils.redaction import RedactingFormatter

LOG_DIRECTORY = PROJECT_ROOT / "logs"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

# Third-party libraries that are very chatty at INFO level.
NOISY_LOGGERS = ("snowflake", "googleapiclient", "urllib3", "botocore")


def setup_logging(level: int = logging.INFO) -> None:
    """Log to logs/pipeline.log and the console; quieten third-party loggers.

    Every handler redacts API keys, including those inside exception
    tracebacks (HttpError messages contain the request URL with ?key=).
    """
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
