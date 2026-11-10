from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.warehouse.snowflake_connection import (
    PROJECT_ROOT,
    REQUIRED_ENV_VARS,
    SnowflakeConfig,
    load_private_key_der,
)


@pytest.fixture
def snowflake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "SNOWFLAKE_ACCOUNT": "ORG-ACCT",
        "SNOWFLAKE_USER": "USER@EXAMPLE.COM",
        "SNOWFLAKE_ROLE": "ROLE",
        "SNOWFLAKE_WAREHOUSE": "WH",
        "SNOWFLAKE_DATABASE": "DB",
        "SNOWFLAKE_SCHEMA": "RAW",
        "SNOWFLAKE_PRIVATE_KEY_PATH": "key.p8",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", raising=False)


def test_config_resolves_relative_key_path_from_project_root(snowflake_env):
    config = SnowflakeConfig.from_env()

    assert config.private_key_path == PROJECT_ROOT / "key.p8"
    assert config.user == "USER@EXAMPLE.COM"
    assert config.private_key_passphrase is None


def test_config_reports_all_missing_variables(snowflake_env, monkeypatch):
    monkeypatch.delenv("SNOWFLAKE_ROLE")
    monkeypatch.delenv("SNOWFLAKE_USER")

    with pytest.raises(ValueError) as exc:
        SnowflakeConfig.from_env()

    assert "SNOWFLAKE_ROLE" in str(exc.value)
    assert "SNOWFLAKE_USER" in str(exc.value)
    assert len(REQUIRED_ENV_VARS) == 7


def _write_key(path: Path, passphrase: bytes | None) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encryption = (
        serialization.BestAvailableEncryption(passphrase)
        if passphrase
        else serialization.NoEncryption()
    )
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            encryption,
        )
    )


def test_load_private_key_der_unencrypted(tmp_path):
    key_file = tmp_path / "key.p8"
    _write_key(key_file, None)

    der = load_private_key_der(key_file)

    assert serialization.load_der_private_key(der, password=None)


def test_load_private_key_der_with_passphrase(tmp_path):
    key_file = tmp_path / "key.p8"
    _write_key(key_file, b"s3cret")

    der = load_private_key_der(key_file, "s3cret")

    assert serialization.load_der_private_key(der, password=None)


def test_load_private_key_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_private_key_der(tmp_path / "missing.p8")
