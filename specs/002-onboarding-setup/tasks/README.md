# Tasks for 002 — System setup, projects and onboarding

Read `../spec.md` first, then your task file. The spec is the source of truth; if a task file disagrees with it, flag the conflict rather than guessing. 001 is implemented; these tasks modify that code.

## Rules for every task

Same as `../../001-initial-version/tasks/README.md` (minimal implementation; check every Pydantic AI, Textual and keyring API against current docs; never call a real LLM/AWS/keyring in tests; ruff check, ruff format --check, ty check and pytest all pass; one commit per task; list anything only a human can do under "Needs human").

Extra: from task 01 on, an autouse fixture in `tests/conftest.py` points `HUNCHES_HOME` at `tmp_path` and installs an in-memory keyring, so no test can reach the real system.

## Order and dependencies

| # | Task | Depends on | Can run in parallel with |
|---|------|-----------|--------------------------|
| 01 | System state file and recommendations (`system.py`), test isolation | — | 02, 03, 04 |
| 02 | API keys (`keys.py`) | 01 | 03, 04 |
| 03 | Rename to assistant/classifier, config migration, pinning, thinking, stale hash | — | 01, 02, 04 |
| 04 | `PathInput` and `PathPicker` | — | 01, 02, 03 |
| 05 | System settings screen and recommendation modal | 01, 02, 03 | 04 |
| 06 | New project screen (replaces `SetupScreen`) | 01–05 | 07 |
| 07 | Projects screen and `open_project` | 01, 03, 04 | 06 |
| 08 | Project settings screen | 03, 04, 06 | — |
| 09 | Startup flow, always-on keys, e2e, README/AGENTS/example | all | — |

Merge conflicts to expect: 03 touches every screen that reads a model field (one-line renames); 06 and 07 both edit `app.py` (keep each to a small, separate hunk).

## Needs human (summary)

| When | Who | Action |
|------|-----|--------|
| Task 01 | agent, then flag to Chris | Re-verify the four recommended model IDs resolve in `genai-prices` and provider docs; stop and report if not. |
| Task 02 | agent | Verify keyring headless behaviour from its docs. |
| Task 05 | Chris | Confirm what "medium" reasoning should be for OpenAI (see spec open items). |
| Task 09 manual check | Chris | Real API key in a real keyring (or env), and optionally AWS credentials with an S3 Vectors index. |
