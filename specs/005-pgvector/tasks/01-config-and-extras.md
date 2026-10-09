# 01 — Config fields, extras, system limit, project status

Spec: Config, Authentication (field names only), "What changes in the code" (`pyproject.toml`, `files.py`, `system.py`), D1, D3, D8, D12.

**Do**
- `pyproject.toml`: extras `pg = ["psycopg[binary]"]` and `rds = ["psycopg[binary]", "boto3"]`; add `psycopg` to the dev group the way boto3 is handled today so `ty` and tests can import it (check how boto3 is done and mirror it). Run `uv lock`/`uv sync --all-extras`; commit the lock file. Verify against the psycopg install docs that `psycopg[binary]` is the right extra and report it.
- `files.Config`: `backend: Literal["local", "s3", "pgvector"]`; optional fields `pg_table, pg_id_column, pg_text_column, pg_vector_column, pg_url_var, pg_search, pg_statement_timeout_s, pg_auth, pg_aws_region, pg_aws_profile` with `None` stored in the model and the spec's defaults applied when read (a small accessor or constants, not scattered literals). `pg_search` is `Literal["exact","index"]`, `pg_auth` is `Literal["url","rds_iam"]`. `write_config` must keep omitting `None`, so local and S3 configs are byte-for-byte unchanged. First look at what already validates the S3 fields; add a "pg_table required when backend is pgvector" validator only if S3 has the equivalent.
- `system.System`: `pg_max_result_mb: int = 512` (`0` = no limit). An old `system.json` without it loads with 512; `VERSION` stays 1.
- `system.project_status`: a pgvector project returns `OK (pgvector not checked)` with no network (mirror the S3 line).
- `keys.py`: only if needed, add the smallest public accessor so `search` can read a stored value for an arbitrary variable name (the spec says `os.environ.get(var) or keys._stored(var)`; prefer a public one-liner over importing a private name). `keys.VARS` and `load_into_env` stay unchanged.

**Tests (red first)**: old local and S3 configs load and re-write unchanged; a pgvector config round-trips and omits unset fields; invalid `pg_search`/`pg_auth` are rejected; old `system.json` loads with 512; `pg_max_result_mb` round-trips including `0`; `project_status` for pgvector; the accessor reads env first, then keyring (stubbed keyring, never the real one).

**Not in this task**: any database access, any UI.
