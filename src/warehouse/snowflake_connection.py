"""Snowflake connection factory using RSA key-pair (JWT) authentication.

Notes
-----
* ``SNOWFLAKE_USER`` must be the user's **LOGIN_NAME**, not the user object
  NAME. Snowflake builds the JWT issuer as
  ``<ACCOUNT>.<LOGIN_NAME>.SHA256:<fingerprint>``; using the object name when
  it differs from LOGIN_NAME fails with ``JWT_TOKEN_INVALID_USER_IN_ISSUER``.
  Check with ``DESCRIBE USER <name>`` -> ``LOGIN_NAME``.
* ``SNOWFLAKE_ACCOUNT`` uses the ``<ORG>-<ACCOUNT_NAME>`` identifier form.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv
from snowflake.connector import SnowflakeConnection

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

REQUIRED_ENV_VARS: tuple[str, ...] = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
    "SNOWFLAKE_PRIVATE_KEY_PATH",
)


@dataclass(frozen=True)
class SnowflakeConfig:
    """Connection settings loaded from environment variables."""

    account: str
    user: str
    role: str
    warehouse: str
    database: str
    schema: str
    private_key_path: Path
    private_key_passphrase: str | None = None

    @classmethod
    def from_env(cls) -> SnowflakeConfig:
        missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
        if missing:
            raise ValueError(
                "Missing Snowflake environment variables: "
                + ", ".join(missing)
            )

        key_path = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"])
        if not key_path.is_absolute():
            key_path = PROJECT_ROOT / key_path

        return cls(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            role=os.environ["SNOWFLAKE_ROLE"],
            warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
            database=os.environ["SNOWFLAKE_DATABASE"],
            schema=os.environ["SNOWFLAKE_SCHEMA"],
            private_key_path=key_path,
            private_key_passphrase=(
                os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
            ),
        )


def load_private_key_der(
    key_path: Path,
    passphrase: str | None = None,
) -> bytes:
    """Read a PEM private key and return it as unencrypted PKCS#8 DER bytes."""
    if not key_path.is_file():
        raise FileNotFoundError(f"Snowflake private key not found: {key_path}")

    private_key = serialization.load_pem_private_key(
        key_path.read_bytes(),
        password=passphrase.encode() if passphrase else None,
    )

    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_snowflake_connection(
    config: SnowflakeConfig | None = None,
) -> SnowflakeConnection:
    """Open a Snowflake connection using key-pair authentication."""
    config = config or SnowflakeConfig.from_env()

    logger.info(
        "Connecting to Snowflake account=%s role=%s warehouse=%s target=%s.%s",
        config.account,
        config.role,
        config.warehouse,
        config.database,
        config.schema,
    )

    return snowflake.connector.connect(
        account=config.account,
        user=config.user,
        private_key=load_private_key_der(
            config.private_key_path, config.private_key_passphrase
        ),
        role=config.role,
        warehouse=config.warehouse,
        database=config.database,
        schema=config.schema,
        enable_server_session_keep_alive_auto_detection=False,
    )
