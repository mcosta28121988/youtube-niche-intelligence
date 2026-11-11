from pathlib import Path

import pytest

from src.warehouse.run_sql import iter_statements, load_scripts, summarise

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_FILES = sorted((PROJECT_ROOT / "sql").rglob("*.sql"))


def test_iter_statements_strips_comments_and_splits():
    sql = """
    -- header comment
    USE ROLE SYSADMIN;
    /* block */
    SELECT 'a;b' AS literal;
    """

    assert list(iter_statements(sql)) == [
        "USE ROLE SYSADMIN;",
        "SELECT 'a;b' AS literal;",
    ]


def test_iter_statements_keeps_scripting_block_intact():
    sql = """
    EXECUTE IMMEDIATE $$
    BEGIN
        IF (1 > 0) THEN RETURN 'x'; END IF;
    END;
    $$;
    SELECT 1;
    """

    statements = list(iter_statements(sql))

    assert len(statements) == 2
    assert statements[0].startswith("EXECUTE IMMEDIATE $$")
    assert statements[0].rstrip().endswith("$$;")


def test_summarise_truncates_and_flattens():
    assert summarise("SELECT\n    1") == "SELECT 1"
    assert len(summarise("x" * 500, width=20)) == 20


def test_load_scripts_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_scripts([tmp_path / "missing.sql"])


def test_load_scripts_rejects_empty_file(tmp_path):
    empty = tmp_path / "empty.sql"
    empty.write_text("-- only a comment\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_scripts([empty])


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_repository_sql_files_parse(path):
    statements = list(iter_statements(path.read_text(encoding="utf-8")))

    assert statements, f"{path} has no statements"
    assert all(s.rstrip().endswith(";") for s in statements)
