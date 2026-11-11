# Snowflake SQL

Infrastructure-as-code for the Snowflake environment. Every object the platform
depends on is defined here, so the warehouse can be rebuilt from the repository.

## Layout

| Path | Purpose | Idempotent |
|---|---|---|
| `setup/00_infrastructure.sql` | Role, warehouse, database, schemas | Yes |
| `setup/01_raw_tables.sql` | RAW landing tables and `CONTROL.PIPELINE_RUNS` | Yes |
| `setup/02_grant_ingest_role.sql` | Least-privilege grants for the pipeline role | Yes |
| `setup/03_resource_monitor.sql` | Optional monthly credit cap | Yes |
| `migrations/` | One-off changes to an existing account, named `YYYYMMDD_NN_description.sql` | No - run once |
| `checks/verify_setup.sql` | Read-only verification queries | Yes |

## Running scripts

Scripts are run with the project's runner, which reuses the key-pair connection
from `.env`, splits statements safely (including `$$` scripting blocks) and
stops at the first error:

```powershell
# Preview without connecting
python -m src.warehouse.run_sql sql/setup/01_raw_tables.sql --dry-run

# Fresh environment
python -m src.warehouse.run_sql sql/setup/00_infrastructure.sql sql/setup/01_raw_tables.sql sql/setup/02_grant_ingest_role.sql

# Verify
python -m src.warehouse.run_sql sql/checks/verify_setup.sql
```

Scripts switch roles with `USE ROLE`, so the connecting user must hold
`USERADMIN`, `SYSADMIN` and `SECURITYADMIN` (and `ACCOUNTADMIN` for the
resource monitor and migrations). Scripts can equally be pasted into a
Snowsight worksheet.

Before running `02_grant_ingest_role.sql` in another account, change the
pipeline user name in the script.

## Role model

```text
ACCOUNTADMIN
├── SECURITYADMIN ── manages grants
│   └── USERADMIN ── owns YOUTUBE_INGEST_ROLE
└── SYSADMIN ─────── owns YOUTUBE_INGEST_WH, YOUTUBE_DB and all schemas/tables
    └── YOUTUBE_INGEST_ROLE ── USAGE on WH/DB/schemas,
                               SELECT/INSERT/DELETE on RAW,
                               SELECT/INSERT/UPDATE on CONTROL
```

- The pipeline never runs as `ACCOUNTADMIN`.
- All tables are created by `SYSADMIN`. The pipeline role has no `CREATE`
  privileges: it can only read and write rows in existing tables.
- Future grants mean newly created tables are automatically accessible to the
  pipeline role.

## RAW table design

| Table | Grain | Source endpoint |
|---|---|---|
| `RAW.VIDEO_DISCOVERY` | run × configured search × video | `search.list` |
| `RAW.VIDEO_SNAPSHOT` | run × video | `videos.list` |
| `RAW.CHANNEL_SNAPSHOT` | run × channel | `channels.list` |
| `CONTROL.PIPELINE_RUNS` | run | pipeline |

- **Append-only**: each run inserts new rows tagged with `RUN_ID`; history is
  never updated in place. Deduplication and modelling happen in dbt.
- **`RAW_PAYLOAD VARIANT`** keeps the untouched API item so new attributes can
  be modelled without re-calling the API.
- **Nullable counts**: hidden like/subscriber counts are stored as `NULL`, not 0.
- Column-level descriptions live in the DDL as `COMMENT`s and are visible in
  Snowsight and `DESCRIBE TABLE`.

## Snowflake gotchas encountered

- **Key-pair auth uses `LOGIN_NAME`.** `SNOWFLAKE_USER` must be the user's
  login name (`DESCRIBE USER` → `LOGIN_NAME`), not the user object name, or
  authentication fails with `JWT_TOKEN_INVALID_USER_IN_ISSUER`.
- **Quoted identifiers are case-sensitive.** A user created as
  `"costamurillonow"` must be referenced with double quotes; unquoted names are
  upper-cased.
