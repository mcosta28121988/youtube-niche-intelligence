"""Smoke test: verify Snowflake connectivity and session context.

Usage:  python -m src.warehouse.test_connection
"""

from __future__ import annotations

import sys

from src.warehouse.snowflake_connection import (
    SnowflakeConfig,
    get_snowflake_connection,
)

CONTEXT_QUERY = """
    SELECT
        CURRENT_USER(),
        CURRENT_ROLE(),
        CURRENT_DATABASE(),
        CURRENT_SCHEMA(),
        CURRENT_WAREHOUSE()
"""


def main() -> int:
    config = SnowflakeConfig.from_env()
    expected = {
        "Role": config.role,
        "Database": config.database,
        "Schema": config.schema,
        "Warehouse": config.warehouse,
    }

    conn = get_snowflake_connection(config)
    try:
        with conn.cursor() as cursor:
            cursor.execute(CONTEXT_QUERY)
            user, role, database, schema, warehouse = cursor.fetchone()
    finally:
        conn.close()

    actual = {
        "Role": role,
        "Database": database,
        "Schema": schema,
        "Warehouse": warehouse,
    }

    print("\nSnowflake connection successful!")
    print(f"User:      {user}")
    for label, value in actual.items():
        status = "OK" if (value or "").upper() == expected[label].upper() else (
            f"MISMATCH (expected {expected[label]})"
        )
        print(f"{label + ':':<10} {value}  [{status}]")

    return 0 if all(
        (actual[k] or "").upper() == expected[k].upper() for k in expected
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
