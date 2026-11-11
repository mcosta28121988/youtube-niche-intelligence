import json
from unittest.mock import MagicMock

import pytest

from src.warehouse.snowflake_loader import (
    RAW_TABLES,
    VIDEO_SNAPSHOT,
    build_insert_sql,
    load_run,
    purge_expired,
    row_values,
)


def fake_connection() -> tuple[MagicMock, MagicMock]:
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.__enter__.return_value = cursor
    return conn, cursor


def executed_sql(cursor: MagicMock) -> list[str]:
    return [c.args[0] for c in cursor.execute.call_args_list]


def test_build_insert_sql_casts_columns_and_repeats_rows():
    sql = build_insert_sql(VIDEO_SNAPSHOT, 2)

    assert sql.startswith("INSERT INTO RAW.VIDEO_SNAPSHOT (RUN_ID, VIDEO_ID,")
    assert "TO_TIMESTAMP_TZ(column6)" in sql  # PUBLISHED_AT
    assert "column8::NUMBER(38,0)" in sql  # VIEW_COUNT
    assert "PARSE_JSON(column11)" in sql  # RAW_PAYLOAD
    assert sql.count("(%s") == 2
    assert sql.count("%s") == 2 * len(VIDEO_SNAPSHOT.columns)


def test_build_insert_sql_requires_rows():
    with pytest.raises(ValueError):
        build_insert_sql(VIDEO_SNAPSHOT, 0)


def test_row_values_orders_by_columns_and_encodes_json():
    row = {
        "run_id": "r1",
        "video_id": "v1",
        "views": 5,
        "likes": None,
        "raw_payload": {"title": 'Café "quoted"'},
    }

    values = row_values(VIDEO_SNAPSHOT, row)

    names = [c.name for c in VIDEO_SNAPSHOT.columns]
    assert values[names.index("RUN_ID")] == "r1"
    assert values[names.index("LIKE_COUNT")] is None
    assert json.loads(values[names.index("RAW_PAYLOAD")]) == row["raw_payload"]


def test_load_run_is_transactional_and_idempotent():
    conn, cursor = fake_connection()
    rows = [{"video_id": f"v{i}"} for i in range(3)]

    loaded = load_run(conn, "run-1", [(VIDEO_SNAPSHOT, rows)], chunk_size=2)

    sql = executed_sql(cursor)
    assert sql[0] == "BEGIN"
    assert sql[1] == "DELETE FROM RAW.VIDEO_SNAPSHOT WHERE RUN_ID = %s"
    assert sum(s.startswith("INSERT INTO") for s in sql) == 2  # 2 chunks
    assert sql[-1] == "COMMIT"
    assert loaded == {"RAW.VIDEO_SNAPSHOT": 3}
    # run_id is injected into every row by the loader
    insert_params = cursor.execute.call_args_list[2].args[1]
    assert insert_params[0] == "run-1"


def test_load_run_rolls_back_on_error():
    conn, cursor = fake_connection()
    cursor.execute.side_effect = lambda sql, *a: (
        (_ for _ in ()).throw(RuntimeError("boom")) if sql.startswith("INSERT") else None
    )

    with pytest.raises(RuntimeError):
        load_run(conn, "run-1", [(VIDEO_SNAPSHOT, [{"video_id": "v"}])])

    assert executed_sql(cursor)[-1] == "ROLLBACK"


def test_load_run_with_no_rows_still_clears_run():
    conn, cursor = fake_connection()

    load_run(conn, "run-1", [(VIDEO_SNAPSHOT, [])])

    assert executed_sql(cursor) == [
        "BEGIN",
        "DELETE FROM RAW.VIDEO_SNAPSHOT WHERE RUN_ID = %s",
        "COMMIT",
    ]


def test_purge_expired_deletes_from_every_raw_table():
    conn, cursor = fake_connection()
    cursor.rowcount = 4

    deleted = purge_expired(conn, 28)

    assert set(deleted) == {spec.name for spec in RAW_TABLES}
    for call in cursor.execute.call_args_list:
        assert "DATEADD(day, -%s, CURRENT_TIMESTAMP())" in call.args[0]
        assert call.args[1] == (28,)


@pytest.mark.parametrize("days", [0, 30])
def test_purge_expired_rejects_out_of_policy_retention(days):
    conn, _ = fake_connection()

    with pytest.raises(ValueError):
        purge_expired(conn, days)
