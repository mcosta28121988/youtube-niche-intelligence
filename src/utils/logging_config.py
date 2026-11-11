import logging

from config.settings import PROJECT_ROOT

LOG_DIRECTORY = PROJECT_ROOT / "logs"

# Third-party libraries that are very chatty at INFO level.
NOISY_LOGGERS = ("snowflake", "googleapiclient", "urllib3", "botocore")


def setup_logging(level: int = logging.INFO) -> None:
    """Log to logs/pipeline.log and the console; quieten third-party loggers."""
    LOG_DIRECTORY.mkdir(exist_ok=True)

    logging.basicConfig(
        level=level,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
        handlers=[
            logging.FileHandler(
                LOG_DIRECTORY / "pipeline.log",
                encoding="utf-8"
            ),
            logging.StreamHandler()
        ],
        force=True
    )

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
