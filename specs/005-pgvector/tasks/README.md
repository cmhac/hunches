# Tasks for 005 — pgvector backend

Read `../spec.md` first (the source of truth), then your task file. If a task file and the spec disagree, flag it instead of guessing; if the spec is wrong or incomplete, say so and fix it in the same change. A task does only what its file says: later tasks own later behaviour. **Never implement beyond your task.**

## Rules for every task

- Repo rules in `/home/user/hunches/CLAUDE.md` apply: minimal implementation (a plain `if`, no base class, registry or plugin system), no real LLM, AWS, keyring or database in the default test run, check every psycopg, boto3 and Textual API against the installed version and the current docs before using it (do not code from memory), every screen works at 80×24.
- **Read-only against the database.** Every statement is a `SELECT` or a `SET LOCAL`; the connection is opened read-only. Identifiers are composed with `psycopg.sql.Identifier`, never string-formatted. Secrets (URL, password, IAM token) never reach `config.toml`, `system.json`, any `.hunches/` file, a log or an error message.
- **Red/green TDD, shown in the work.** Write the failing tests first and run them to see them fail for the right reason (not an import error you could have avoided); then implement until they pass. Report, per behaviour, the failing run (command and failure message) and the passing run. Expected values are hand-written in the tests, never derived by running the code under test.
- Tests use a stubbed `psycopg` (a fake `connect`, in the style of `FakeS3` in `tests/test_search.py`) and a stubbed `boto3`. The real-database tests live only in task 12 and are skipped unless `HUNCHES_TEST_PG_URL` is set.
- `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest` all pass before the commit (for UI tasks, run the targeted UI test files while developing and the full suite once at the end). Report their actual output summaries.
- One commit per task on branch `claude/intelligent-turing-asvhrl`; commit message `005/NN: ...`; do not open a PR; do not push (the overseer pushes).
- Update or delete existing tests the task breaks, in the same commit.
- Final report: what changed, files touched, red/green evidence, check outputs, deviations from the spec, anything only a human can do. Anything the spec marks "verify in the task" must be verified against the docs and the result written into the spec in the same commit.

## Order

| # | Task | Depends on |
|---|------|-----------|
| 01 | Config fields, `pg` / `rds` extras, `System.pg_max_result_mb`, `project_status` | — |
| 02 | Connection layer: URL lookup, read-only connect, scrubber, `rds_iam`, timeout, errors | 01 |
| 03 | Server probes: extension version, column type and schema, row/width estimates | 02 |
| 04 | `search_pg_exact`: the single query, cap, `NaN` guard, result assembly | 03 |
| 05 | Result-size guards, Stop (`cancel_safe`), progress callback | 04 |
| 06 | `search()` `index` mode and the `APPROXIMATE` flag | 03 |
| 07 | `build_candidates` branch and Search screen warnings and progress | 05, 06 |
| 08 | `check_store` function (no UI) | 03 |
| 09 | System settings: `pg_max_result_mb` | 01 |
| 10 | New project: third backend, URL status and save, Check store | 07, 08 |
| 11 | Project settings, Projects screen, `open_project` allow-list | 08, 10 |
| 12 | Integration tests, optional CI job, size sweep, manual checklist | all |
| 13 | Docs (README, AGENTS.md, 001/002 notes) | all |

Run strictly in order, one at a time. Needs a human: a real Postgres with pgvector, every managed service (RDS, Aurora, Supabase and their poolers), IAM authentication against a real instance (Chris tests this himself before the branch is merged), TLS, tables larger than memory. Agents report these and stop; they never fake them.
