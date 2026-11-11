"""Execute version-controlled SQL scripts against Snowflake.

Scripts are split into statements with the connector's splitter, which
understands quoted strings and ``$$`` Snowflake Scripting blocks. Execution
stops at the first failing statement.

Usage
-----
    # Preview statements without connecting
    python -m src.warehouse.run_sql sql/setup/01_raw_tables.sql --dry-run

    # Execute one or more files in order
    python -m src.warehouse.run_sql sql/migrations/<file>.sql sql/setup/01_raw_tables.sql

    # Connect with a specific initial role (scripts may switch with USE ROLE)
    python -m src.warehouse.run_sql sql/checks/verify_setup.sql --role SYSADMIN
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterator, Sequence
from dataclasses import replace
from io import StringIO
from pathlib import Path

# The public splitter (re-exported by the connector for compatibility).
from snowflake.connector.util_text import split_statements

from src.utils.logging_config import setup_logging
from src.warehouse.snowflake_connection import (
    SnowflakeConfig,
    get_snowflake_connection,
)

logger = logging.getLogger(__name__)

MAX_ROWS_DISPLAYED = 50


def iter_statements(sql_text: str) -> Iterator[str]:
    """Yield executable statements from a SQL script, without comments."""
    for statement, _is_put_get in split_statements(
        StringIO(sql_text), remove_comments=True
    ):
        statement = statement.strip()
        if statement and statement != ";":
            yield statement


def summarise(statement: str, width: int = 100) -> str:
    """Single-line preview of a statement for logs."""
    one_line = " ".join(statement.split())
    return one_line if len(one_line) <= width else one_line[: width - 3] + "..."


def load_scripts(paths: Sequence[Path]) -> list[tuple[Path, list[str]]]:
    """Read and split every script up front so syntax issues fail early."""
    scripts = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"SQL file not found: {path}")
        statements = list(iter_statements(path.read_text(encoding="utf-8")))
        if not statements:
            raise ValueError(f"No SQL statements found in {path}")
        scripts.append((path, statements))
    return scripts


def run_scripts(
    scripts: list[tuple[Path, list[str]]],
    config: SnowflakeConfig,
) -> None:
    conn = get_snowflake_connection(config)
    try:
        for path, statements in scripts:
            logger.info("Running %s (%s statements)", path, len(statements))
            for number, statement in enumerate(statements, start=1):
                logger.info("[%s/%s] %s", number, len(statements), summarise(statement))
                with conn.cursor() as cursor:
                    cursor.execute(statement)
                    _print_result(cursor)
            logger.info("Completed %s", path)
    finally:
        conn.close()


def _print_result(cursor) -> None:
    if not cursor.description:
        return
    columns = [column[0] for column in cursor.description]
    rows = cursor.fetchmany(MAX_ROWS_DISPLAYED)
    if not rows:
        return
    print("    " + " | ".join(columns))
    for row in rows:
        print("    " + " | ".join("" if v is None else str(v) for v in row))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("files", nargs="+", type=Path, help="SQL files, run in order")
    parser.add_argument("--role", help="Initial session role (default: SNOWFLAKE_ROLE)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the parsed statements without connecting",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)
    scripts = load_scripts(args.files)

    if args.dry_run:
        for path, statements in scripts:
            print(f"-- {path}: {len(statements)} statements")
            for number, statement in enumerate(statements, start=1):
                print(f"[{number}] {statement}\n")
        return 0

    config = SnowflakeConfig.from_env()
    if args.role:
        config = replace(config, role=args.role)

    try:
        run_scripts(scripts, config)
    except Exception:
        logger.exception("SQL execution failed; later statements were not run")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
