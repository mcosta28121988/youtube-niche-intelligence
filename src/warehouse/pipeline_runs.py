"""Record pipeline executions in CONTROL.PIPELINE_RUNS."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from snowflake.connector import SnowflakeConnection

from src.utils.redaction import redact

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 4000


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass
class RunMetrics:
    videos_discovered: int = 0
    videos_enriched: int = 0
    channels_extracted: int = 0
    search_calls: int = 0
    quota_units: int = 0


class PipelineRunTracker:
    """Inserts a RUNNING row at start and updates it when the run finishes."""

    def __init__(
        self,
        conn: SnowflakeConnection,
        run_id: str,
        pipeline_name: str,
    ) -> None:
        self.conn = conn
        self.run_id = run_id
        self.pipeline_name = pipeline_name

    def start(self, parameters: dict[str, Any]) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO CONTROL.PIPELINE_RUNS "
                "(RUN_ID, PIPELINE_NAME, STATUS, STARTED_AT, RUN_PARAMETERS) "
                "SELECT %s, %s, %s, CURRENT_TIMESTAMP(), PARSE_JSON(%s)",
                (
                    self.run_id,
                    self.pipeline_name,
                    RunStatus.RUNNING.value,
                    json.dumps(parameters),
                ),
            )
        logger.info("Pipeline run %s started", self.run_id)

    def finish(
        self,
        status: RunStatus,
        metrics: RunMetrics,
        error_message: str | None = None,
    ) -> None:
        if error_message:
            error_message = redact(error_message)[:MAX_ERROR_LENGTH]
        with self.conn.cursor() as cursor:
            cursor.execute(
                "UPDATE CONTROL.PIPELINE_RUNS SET "
                "STATUS = %s, FINISHED_AT = CURRENT_TIMESTAMP(), "
                "VIDEOS_DISCOVERED = %s, VIDEOS_ENRICHED = %s, "
                "CHANNELS_EXTRACTED = %s, SEARCH_CALLS = %s, "
                "API_QUOTA_UNITS_ESTIMATED = %s, ERROR_MESSAGE = %s "
                "WHERE RUN_ID = %s",
                (
                    status.value,
                    metrics.videos_discovered,
                    metrics.videos_enriched,
                    metrics.channels_extracted,
                    metrics.search_calls,
                    metrics.quota_units,
                    error_message,
                    self.run_id,
                ),
            )
        logger.info("Pipeline run %s finished: %s", self.run_id, status.value)
