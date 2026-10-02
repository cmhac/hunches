# AGENTS.md

## What this repo is

`hunches` is an interactive Textual TUI toolkit for content analysis over an already-embedded corpus: seed phrases → semantic search → candidates → LLM classifier validated against a hand-labelled gold set → classified output. A smart model talks to the user; a cheap model does bulk classification. Python package `hunches`, console script `hunches`.

## Current state

Spec and plan only. No code exists yet. Implementation follows the task files.

- Source of truth for behaviour: `specs/001-initial-version/spec.md`
- Implementation plan: `specs/001-initial-version/tasks/README.md` (dependency order, human-only actions) and one file per task, `01-…` to `18-…`

**Before starting any work: read the spec, then your task file.** If a task file and the spec disagree, flag it instead of guessing. If the spec is wrong or incomplete, say so and update it in the same change.

## Principles (non-negotiable)

- Absolute minimal implementation. No abstraction, base class, registry or plugin system unless the user explicitly asks. Where two behaviours must coexist (local vs S3 vector search), use a plain `if` in one function.
- Plain files in `.hunches/` are the only state. The tool itself never runs git; the user commits.
- Check every Pydantic AI and Textual API against the current docs before using it. Do not code from memory. Pydantic AI docs are under https://pydantic.dev/docs/ai/ (`llms.txt` index there); Textual testing guide: https://textual.textualize.io/guide/testing/
- Never call a real LLM or AWS API in tests. Use pydantic-ai `TestModel` / `FunctionModel`, stubbed boto3 responses and tiny hand-built vectors.
- Never show a cost of $0 when the price is unknown. Unknown is `?` with a prominent warning.
- Never commit API keys. Keys come from the environment or a git-ignored `.env`.

## Stack

Python 3.12+, `uv`, `pydantic-ai` (Agent, Embedder), `textual`, `numpy`, `genai-prices`, `pyyaml`, optional extra `s3` (`boto3`). Lint/format `ruff`, types `ty`, tests `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`).

## Commands (once task 01 has landed)

```
uv sync --all-extras
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
uv run hunches          # run from a directory containing (or to create) .hunches/
```

All of ruff, ty and pytest must pass before every commit. If these commands don't exist yet, task 01 hasn't been done; do it first.

## Layout (target)

- `src/hunches/` — one module per concern (`files.py`, `cost.py`, `search.py`, `candidates.py`, `metrics.py`, `classifier.py`, `app.py`), screens in `src/hunches/screens/`
- `tests/` — mirrors the modules; one Pilot smoke test per screen
- `examples/` — tiny sample project
- `specs/` — specs and task files

## Testing notes

- Textual: drive with `async with app.run_test() as pilot:`; `await pilot.pause()` before assertions that depend on a message being processed; default terminal is 80×24, pass `size=` when needed.
- Metrics tests compare against hand-computed values written in the test; never derive expected values by running the code under test.
- Use `tmp_path` and `monkeypatch.chdir` for `.hunches/` fixtures.

## Conventions

- Match surrounding code style; comments only where the why isn't obvious.
- One commit per task, descriptive message. Develop on the branch you were assigned; do not open a PR unless asked.
- Don't tag, release or publish. The user pushes tags; PyPI uses trusted publishing (no token in secrets).

## Needs a human (stop and report, don't fake)

API keys, a real embedded corpus, AWS credentials, PyPI trusted-publisher setup, the GitHub `pypi` environment, the `v0.1.0` tag, and (if you can't verify it from AWS docs) the S3 Vectors `topK` maximum. Full list: `specs/001-initial-version/tasks/README.md`.
