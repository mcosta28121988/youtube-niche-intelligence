# Runbook

How to set up, run and inspect the ingestion pipeline. For *why* things are
built this way, see [data_policy.md](data_policy.md) and
[../sql/README.md](../sql/README.md).

## 1. One-time setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt     # runtime + pytest + ruff
copy .env.example .env                  # then fill in the values
python -m src.warehouse.test_connection # checks role, warehouse, database, schema
```

`.env` holds the YouTube API key and Snowflake key-pair settings. It is
gitignored and must never be committed. `SNOWFLAKE_USER` must be the user's
**login name** (see `sql/README.md` → gotchas).

## 2. Running the pipeline

| Command | What it does | API cost |
|---|---|---|
| `python -m src.main --check-config` | Validates `config/searches.toml` and prints exactly what each search will send | None |
| `python -m src.main --list-categories --region AU` | Lists video categories for a region, and whether each is searchable | 1 unit |
| `python -m src.main --no-load` | Calls the API but writes nothing to Snowflake | Full run |
| `python -m src.main` | Full run: purge expired rows, extract, load RAW, record the run | Full run |
| `python -m src.main --max-pages 2` | Overrides `max_pages` for every search in this run | 2× search calls |
| `python -m src.main --purge-only` | Deletes RAW rows past the retention window; no API calls | None |

Exit code is `0` on success and `1` on failure; details go to the console and
`logs/pipeline.log` (API keys are redacted).

### Quota

| Allowance | Daily limit | Used by |
|---|---|---|
| search.list calls | 100 | each page of each `source = "search"` entry |
| Quota units | 10,000 | videos.list / channels.list (1 per 50 items), trending charts (1 per page), category lists (1) |

Both reset at **midnight Pacific Time** (about 6–7 pm in Sydney).
`--check-config` shows the planned usage for one run; the actual usage of each
run is recorded in `CONTROL.PIPELINE_RUNS`.

## 3. Configuring searches

Everything lives in `config/searches.toml`. `[defaults]` apply to every
`[[searches]]` entry, and each entry can override them. Run
`--check-config` after every edit.

```toml
# Keyword search with filters
[[searches]]
keyword = "history documentary"

# Category only: no keyword
[[searches]]
name = "AU education - category only"
category = "Education"            # name or ID from --list-categories

# Trending chart (Most Popular) for a region and category
[[searches]]
name = "AU trending - science & technology"
source = "trending"
category = "Science & Technology"
```

| Setting | Values | Notes |
|---|---|---|
| `source` | `search` (default), `trending` | Trending uses only `region_code`, `category`, `max_pages` (≤ 4) |
| `keyword` | text | Optional when `category` is set |
| `name` | text | Must be unique; defaults to the keyword |
| `category` | name or ID | Must be *searchable* in the region |
| `max_pages` | 1+ | 50 results per page |
| `order` | `viewCount`, `relevance`, `date`, `rating`, `title` | |
| `duration` | `any`, `short` (< 4 min), `medium` (4–20), `long` (> 20) | |
| `published_within_days` | 1+ | Omit for all time |
| `region_code` | `AU`, `US`, … | Videos viewable in, and ranked for, that country; *not* creators from it |
| `relevance_language` | `en`, … | |
| `safe_search` | `moderate`, `strict`, `none` | |
| `definition`, `caption`, `license`, `video_type`, `dimension`, `event_type` | see comments in the TOML | |

Things to know:

- **Neither source returns every video in a category.** Results are YouTube's
  ranked selection: up to ~500 per search, 200 per trending chart.
- **Not all categories can be searched.** In AU, *Documentary* (35), *Shorts*
  (42) and the other film/TV categories aren't searchable; use Education (27),
  Science & Technology (28) or Entertainment (24).
- **Not all categories have a trending chart.** In AU, Education (27) and
  Travel & Events (19) don't (checked Nov 2026). These are skipped with a
  warning.
- **Trending charts are loose.** Only about a third of the "Science &
  Technology" chart was tagged with that category.
- **Category-only searches need a date limit.** Without
  `published_within_days`, all-time hits (e.g. children's content) dominate.

## 4. Exploring the data

Open a Snowsight worksheet with role `YOUTUBE_INGEST_ROLE` and warehouse
`YOUTUBE_INGEST_WH`, and paste queries from
[`sql/checks/explore_raw.sql`](../sql/checks/explore_raw.sql):

1. Runs, newest first
2. What each search found in the latest run
3. Top 10 per search with video statistics
4. Latest snapshot of each channel
5. Unmodelled fields from `RAW_PAYLOAD` (tags, language, captions)
6. Row counts and data age per table

Or print all results in the terminal:

```powershell
python -m src.warehouse.run_sql sql/checks/explore_raw.sql
```

### Tables

| Table | One row per | Key columns |
|---|---|---|
| `CONTROL.PIPELINE_RUNS` | run | `STATUS`, `SEARCH_CALLS`, `API_QUOTA_UNITS_ESTIMATED`, `RUN_PARAMETERS`, `ERROR_MESSAGE` |
| `RAW.VIDEO_DISCOVERY` | run × search × video | `SEARCH_SOURCE`, `SEARCH_NAME`, `SEARCH_KEYWORD`, `SEARCH_RANK`, `SEARCH_FILTERS` |
| `RAW.VIDEO_SNAPSHOT` | run × video | `VIEW_COUNT`, `LIKE_COUNT`, `COMMENT_COUNT`, `DURATION`, `CATEGORY_ID` |
| `RAW.CHANNEL_SNAPSHOT` | run × channel | `SUBSCRIBER_COUNT`, `TOTAL_VIEWS`, `VIDEO_COUNT` |

Every table has a `RAW_PAYLOAD` column with the untouched API response.

### Quirks in RAW (cleaned up in dbt)

- **Search titles are HTML-escaped**, e.g. `&amp;`, `&#39;`.
- **`DURATION` is ISO 8601**, e.g. `PT1H2M10S`, not minutes.
- **`NULL` counts mean hidden**, not zero.
- **Videos repeat** across runs and searches, because each run is appended in
  full.
- **Trending rows** have no `SEARCH_KEYWORD`, and their `SEARCH_FILTERS`
  contain `chart = mostPopular`.

## 5. Data policy rules (summary)

Full detail in [data_policy.md](data_policy.md).

- RAW data is deleted after **28 days**, and the policy maximum is 30.
  This applies to *every* copy.
- **Don't export** YouTube data out of Snowflake (CSV, Excel, long-lived
  screenshots, Power BI imports kept beyond 30 days).
- **No derived scores or rankings across channels** from YouTube data.
  Simple per-video arithmetic is fine.
- Never commit `.env`, API keys or private keys. CI fails if you do.

## 6. Development

```powershell
pytest                 # unit tests; no API or Snowflake needed
ruff check . --fix     # lint
ruff format .          # format
```

GitHub Actions runs a credential guard, ruff and pytest on every push to
`main` and every pull request (`.github/workflows/ci.yml`).

### Snowflake changes

Schema changes are SQL files run with the project runner; see
[../sql/README.md](../sql/README.md). New changes go in
`sql/migrations/YYYYMMDD_NN_description.sql`, and `sql/setup/` is updated to
match.

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `JWT_TOKEN_INVALID_USER_IN_ISSUER` | `SNOWFLAKE_USER` is not the login name |
| `quotaExceeded` / `dailyLimitExceeded` | Daily allowance used up; wait for the midnight Pacific reset |
| `Unknown or non-searchable category` | Name typo, or not searchable in that region; run `--list-categories` |
| `No Most Popular chart for ...` warning | That category has no trending chart in the region; pick another |
| `search calls planned exceeds the daily limit` | Too many searches × `max_pages`; reduce them |
| Garbled characters in the terminal | Use Windows Terminal; the CLIs print UTF-8 |
