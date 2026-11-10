import logging
from pathlib import Path


def setup_logging():

    log_directory = Path("logs")
    log_directory.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
        handlers=[
            logging.FileHandler(
                log_directory / "pipeline.log",
                encoding="utf-8"
            ),
            logging.StreamHandler()
        ],
        force=True
    )