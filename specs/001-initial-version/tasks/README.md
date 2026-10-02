# Tasks for 001 — Initial version

Read `../spec.md` first, then your task file. The spec is the source of truth; if a task file disagrees with it, flag the conflict rather than guessing.

## Rules for every task

- Minimal implementation. No abstraction, base classes, registries or plugin systems (spec "Principles").
- Check every Pydantic AI and Textual API against the current docs before using it. Do not code from memory.
- Never call a real LLM or AWS API in tests (`TestModel` / `FunctionModel` / stubbed boto3).
- Each task ends with `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest` all passing, then one commit.
- If a task needs something only a human can do, stop, finish what you can, and list it under "Needs human" in your final message. Do not fake it.
- Files you create: keep one module per concern under `src/hunches/`. Don't split further than the task says.

## Order and dependencies

| # | Task | Depends on | Can run in parallel with |
|---|------|-----------|--------------------------|
| 01 | Project scaffold | — | — |
| 02 | CI/CD workflows | 01 | 03–07 |
| 03 | Project files (`.hunches/` I/O) | 01 | 02 |
| 04 | Cache and cost tracking | 03 | 05, 07 (metrics part) |
| 05 | Vector search (local + S3) | 03 | 04 |
| 06 | Candidate generation | 04, 05 | 07 |
| 07 | Classifier and metrics | 03, 04 | 05, 06 |
| 08 | App shell, header, resume | 03, 04 | 05–07 |
| 09 | Stage 1: brief and seeds | 08, 04 | 10 |
| 10 | Stage 2: search | 06, 08 | 09 |
| 11 | Stage 3: taxonomy and prompt | 09 | — |
| 12 | Stage 4: gold dev set | 07, 08, 11 | — |
| 13 | Stage 5: tuning loop | 12 | — |
| 14 | Stage 6: gold test set | 13 | — |
| 15 | Stage 7: threshold | 07, 10, 14 | — |
| 16 | Stage 8: full run | 15 | 17 |
| 17 | Stage 9: browse | 08 | 16 |
| 18 | End-to-end test, docs, first release | all | — |

Merge conflicts to expect: tasks 09–17 each add one screen and register it in `app.py`. Keep that registration to a single line per screen.

## Needs human (summary)

Each task file repeats the items relevant to it. Nothing below blocks tasks 01–17 except where noted; agents can finish all code and tests without any of it.

| When | Who does it | Action |
|------|-------------|--------|
| Before 02 can be validated | Chris | Confirm the PyPI project name `hunches` is free (or choose another) and change `name` in `pyproject.toml` if not. |
| Before the first release (task 18) | Chris | On PyPI, add a **pending trusted publisher**: owner `cmhac`, repo `hunches`, workflow `publish.yml`, environment `pypi`. In GitHub repo settings, create the environment `pypi`. |
| Before task 18 manual check | Chris | Provide `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` in the shell or a git-ignored `.env`. Not needed in CI. Never commit keys. |
| Before task 18 manual check | Chris | Provide a small embedded corpus in the local format (`vectors.npy`, `items.jsonl`, `meta.json`) built with a model you name. Agents cannot build one without the real corpus and a key. |
| Optional, S3 manual check | Chris | AWS credentials plus an S3 Vectors bucket/index (cosine) to try the S3 backend for real. Unit tests use stubs, so this is only for confidence. |
| Task 05 | Chris | Answer the open question: S3 Vectors `topK` maximum, if the implementer cannot verify it from AWS docs. |
| Sandbox sessions | Chris | If an agent runs in a restricted-network cloud container, allow `pypi.org`, `files.pythonhosted.org`, `huggingface.co` (local embedding models) and the LLM provider hosts. |
| Task 18 | Chris | Push the `v0.1.0` tag yourself (agents do not tag or publish). |
