"""Load extracted YouTube records into Snowflake RAW tables.

Design
------
* **Idempotent per run.** Each load deletes rows for its RUN_ID before
  inserting, inside one transaction across all tables, so a retried load never
  duplicates data and a failed load leaves nothing behind.
* **No staging objects.** Rows are inserted with ``INSERT ... SELECT ... FROM
  VALUES`` in chunks, which allows ``PARSE_JSON`` for VARIANT columns and
  needs only INSERT/DELETE privileges. Suitable for the low thousands of rows a
  run produces; switch to staged ``COPY INTO`` if volumes grow substantially.
* **Retention.** ``purge_expired`` enforces the YouTube 30-day storage limit
  (docs/data_policy.md).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from snowflake.connector import SnowflakeConnection

from config.settings import MAX_RETENTION_DAYS

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 50  # keeps statements well below Snowflake's size limit


class ColumnType(Enum):
    TEXT = "{}::VARCHAR"
    INTEGER = "{}::NUMBER(38,0)"
    TIMESTAMP = "TO_TIMESTAMP_TZ({})"
    JSON = "PARSE_JSON({})"


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    source: str
    type: ColumnType = ColumnType.TEXT


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[ColumnSpec, ...]
    retention_column: str


C = ColumnSpec
T = ColumnType

VIDEO_DISCOVERY = TableSpec(
    name="RAW.VIDEO_DISCOVERY",
    columns=(
        C("RUN_ID", "run_id"),
        C("SEARCH_KEYWORD", "keyword"),
        C("SEARCH_RANK", "search_rank", T.INTEGER),
        C("VIDEO_ID", "video_id"),
        C("CHANNEL_ID", "channel_id"),
        C("TITLE", "title"),
        C("DESCRIPTION", "description"),
        C("CHANNEL_TITLE", "channel_title"),
        C("PUBLISHED_AT", "published_at", T.TIMESTAMP),
        C("RAW_PAYLOAD", "raw_payload", T.JSON),
        C("DISCOVERED_AT", "extracted_at", T.TIMESTAMP),
    ),
    retention_column="DISCOVERED_AT",
)

VIDEO_SNAPSHOT = TableSpec(
    name="RAW.VIDEO_SNAPSHOT",
    columns=(
        C("RUN_ID", "run_id"),
        C("VIDEO_ID", "video_id"),
        C("CHANNEL_ID", "channel_id"),
        C("TITLE", "title"),
        C("CATEGORY_ID", "category_id"),
        C("PUBLISHED_AT", "published_at", T.TIMESTAMP),
        C("DURATION", "duration"),
        C("VIEW_COUNT", "views", T.INTEGER),
        C("LIKE_COUNT", "likes", T.INTEGER),
        C("COMMENT_COUNT", "comments", T.INTEGER),
        C("RAW_PAYLOAD", "raw_payload", T.JSON),
        C("SNAPSHOT_AT", "extracted_at", T.TIMESTAMP),
    ),
    retention_column="SNAPSHOT_AT",
)

CHANNEL_SNAPSHOT = TableSpec(
    name="RAW.CHANNEL_SNAPSHOT",
    columns=(
        C("RUN_ID", "run_id"),
        C("CHANNEL_ID", "channel_id"),
        C("CHANNEL_NAME", "channel_name"),
        C("PUBLISHED_AT", "published_at", T.TIMESTAMP),
        C("SUBSCRIBER_COUNT", "subscribers", T.INTEGER),
        C("TOTAL_VIEWS", "total_views", T.INTEGER),
        C("VIDEO_COUNT", "video_count", T.INTEGER),
        C("UPLOADS_PLAYLIST_ID", "uploads_playlist_id"),
        C("RAW_PAYLOAD", "raw_payload", T.JSON),
        C("SNAPSHOT_AT", "extracted_at", T.TIMESTAMP),
    ),
    retention_column="SNAPSHOT_AT",
)

RAW_TABLES: tuple[TableSpec, ...] = (VIDEO_DISCOVERY, VIDEO_SNAPSHOT, CHANNEL_SNAPSHOT)


def build_insert_sql(spec: TableSpec, row_count: int) -> str:
    """INSERT ... SELECT <casts> FROM VALUES (...) for ``row_count`` rows."""
    if row_count < 1:
        raise ValueError("row_count must be at least 1")

    column_names = ", ".join(column.name for column in spec.columns)
    select_list = ", ".join(
        column.type.value.format(f"column{position}")
        for position, column in enumerate(spec.columns, start=1)
    )
    row_placeholder = "(" + ", ".join(["%s"] * len(spec.columns)) + ")"
    values = ",\n".join([row_placeholder] * row_count)

    return (
        f"INSERT INTO {spec.name} ({column_names})\n"
        f"SELECT {select_list}\n"
        f"FROM VALUES\n{values}"
    )


def row_values(spec: TableSpec, row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Order a record's values by the table's columns; JSON-encode VARIANTs."""
    values = []
    for column in spec.columns:
        value = row.get(column.source)
        if column.type is ColumnType.JSON and value is not None:
            value = json.dumps(value, ensure_ascii=False)
        values.append(value)
    return tuple(values)


def _chunks(rows: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def load_run(
    conn: SnowflakeConnection,
    run_id: str,
    batches: Sequence[tuple[TableSpec, Sequence[Mapping[str, Any]]]],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, int]:
    """Atomically replace this run's rows in each table. Returns rows loaded."""
    loaded: dict[str, int] = {}
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        for spec, rows in batches:
            cursor.execute(f"DELETE FROM {spec.name} WHERE RUN_ID = %s", (run_id,))
            for chunk in _chunks(rows, chunk_size):
                params = [
                    value
                    for row in chunk
                    for value in row_values(spec, {**row, "run_id": run_id})
                ]
                cursor.execute(build_insert_sql(spec, len(chunk)), params)
            loaded[spec.name] = len(rows)
        cursor.execute("COMMIT")
    except Exception:
        cursor.execute("ROLLBACK")
        logger.error("Load for run %s rolled back", run_id)
        raise
    finally:
        cursor.close()

    for table, count in loaded.items():
        logger.info("Loaded %s rows into %s", count, table)
    return loaded


def purge_expired(
    conn: SnowflakeConnection,
    retention_days: int,
) -> dict[str, int]:
    """Delete RAW rows older than ``retention_days``. Returns rows deleted."""
    if not 1 <= retention_days <= MAX_RETENTION_DAYS:
        raise ValueError(f"retention_days must be between 1 and {MAX_RETENTION_DAYS}")

    deleted: dict[str, int] = {}
    with conn.cursor() as cursor:
        for spec in RAW_TABLES:
            cursor.execute(
                f"DELETE FROM {spec.name} "
                f"WHERE {spec.retention_column} < "
                "DATEADD(day, -%s, CURRENT_TIMESTAMP())",
                (retention_days,),
            )
            deleted[spec.name] = cursor.rowcount or 0

    logger.info(
        "Retention purge (older than %s days): %s",
        retention_days,
        ", ".join(f"{table}={count}" for table, count in deleted.items()),
    )
    return deleted
