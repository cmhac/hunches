# 01 — Project scaffold

Spec sections: Stack, Testing.

## Goal
An empty but fully wired project: installs, lints, type-checks, tests, and launches a blank Textual app.

## Do
- `uv init --package`, name `hunches`, Python `>=3.12`, `src/hunches/` layout, console script `hunches = hunches.app:main`.
- Dependencies: `pydantic-ai` (check the current slim/extras names for Anthropic, OpenAI and Sentence Transformers embeddings; this is a spec open item, record what you find in a comment in `pyproject.toml`), `textual`, `numpy`, `genai-prices`, `pyyaml`, `python-dotenv`. Optional extra `s3 = ["boto3"]`. Optional extra for local embeddings if pydantic-ai provides one.
- Dev group: `pytest`, `pytest-asyncio` (`asyncio_mode = "auto"` in `pyproject.toml`), `pytest-textual-snapshot`, `ruff`, `ty`, `pre-commit`.
- `.pre-commit-config.yaml`: ruff (lint + format) and ty. Prefer local hooks that call `uv run` so versions match the lockfile.
- `.gitignore`: Python basics, `.env`, `.venv`. Do **not** ignore `.hunches/` (it is tracked by design).
- `src/hunches/app.py` with a `HunchesApp(App)` showing an empty screen and a `main()` that runs it. Load `.env` with `python-dotenv` in `main()`.
- One smoke test: the app starts under `run_test()` and quits on `q`.
- Short `README.md` (what it is, install, run). Expand in task 18.

## Done when
- `uv sync`, `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run pre-commit run --all-files` pass.
- `uv run hunches` opens and quits cleanly.

## Needs human
- Confirm the PyPI name `hunches` is available (check https://pypi.org/project/hunches/). If taken, stop and ask which name to use.
