# AGENTS.md

## What this repo is

`hunches` is an interactive Textual TUI toolkit for content analysis over an already-embedded corpus: seed phrases → semantic search → candidates → LLM classifier validated against a hand-labelled gold set → classified output. An assistant model talks to the user; a classifier model does bulk classification (renamed from smart/cheap in 002). Python package `hunches`, console script `hunches`.

## Current state

001 (stages 1-9), 002 (system setup, projects, onboarding; tasks 01-09) and 003 (TUI redesign, tasks 01-18) are implemented. Still needed from a human: the manual terminal pass listed in `specs/003-tui-redesign/tasks/18-e2e-and-docs.md`.

- Source of truth for behaviour: `specs/001-initial-version/spec.md`, then `specs/002-onboarding-setup/spec.md` (which lists its explicit changes to 001), then `specs/003-tui-redesign/spec.md` (its "Behaviour that changes in 001 and 002" lists what it overrides)
- Implementation plans: `specs/<spec>/tasks/README.md` (dependency order, human-only actions) and one file per task. 001: `01-…` to `18-…`; 002: `01-…` to `09-…`; 003: `01-…` to `18-…`

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
uv run pytest                 # everything (CI runs this); parallel via pytest-xdist
uv run pytest -m "not ui"     # fast tier; this is what pre-commit runs
uv run pytest tests/test_x.py # targeted UI tests
uv run hunches          # run from a directory containing (or to create) .hunches/
```

Ruff, ty and the fast tests (`pytest -m "not ui"`) must pass before every commit (pre-commit enforces this). The slow Pilot UI tests (marked `ui` automatically in `tests/conftest.py` for any module that calls `run_test(`) are a CI requirement in GitHub Actions, not a pre-commit one. Locally, whenever a change touches a screen, modal, `app.py`, `theme.py`, `hunches.tcss` or anything a screen reads, run the relevant UI test files (targeted, e.g. `uv run pytest tests/test_tune_screen.py tests/test_sizes.py`) during development; run the full suite only when the change is broad. Do not wait on the full suite for every small change. If these commands don't exist yet, task 01 hasn't been done; do it first.

## Layout (target)

- `src/hunches/` — one module per concern (`files.py`, `cost.py`, `search.py`, `candidates.py`, `metrics.py`, `classifier.py`, `app.py`), screens in `src/hunches/screens/`
- System scope (per user, outside git): `system.py` (`system.json`, project/store lists, recommended models), `keys.py` (API keys: env > keyring), `models.py` (model list and prices for the pickers). `$HUNCHES_HOME` overrides the system directory
- Screens added by 002: `screens/system.py` (system settings, recommendation modal), `screens/projects.py`, `screens/new_project.py`, `screens/project_settings.py`, `screens/paths.py` (`PathInput`, `PathPicker`), `screens/model_picker.py`
- `screens/progress.py` (003): `LabelBar` (a labelled progress bar), `RunIndicator` (the centred run block with Stop/Resume/Start button), `eta_text`, `seconds_text`. The chat is `ChatPanel` in `app.py` (`send_context`, `record`, `ChatPanel.Submitted`, edits recorded without a model call via `files.edit_message`); there is no separate chat module
- Taxonomy versions (003 task 17): `files.taxonomy_in_use/labels_changed/list_versions/archive_version/start_new_version/restore_version`, archives in `.hunches/versions/<n>/` (never deleted), `VersionsScreen` in `screens/taxonomy.py`
- `HunchesApp.on_mount` runs the startup flow; always-on keys: `f3` project settings, `f4` Projects, `f5` System settings
- `src/hunches/theme.py` (colours, `label_tag`/`label_text`, the TextArea theme) and `src/hunches/hunches.tcss` (shared look); `screens/report.py` renders the metrics and disagreement tables shared by stages 5 and 6
- `tests/` — mirrors the modules; one Pilot smoke test per screen
- `examples/` — tiny sample project
- `specs/` — specs and task files

## TUI look

Visual design comes from a design handoff (dark theme, panels, stage stepper); `theme.py` and `hunches.tcss` implement it. Rules to keep:

- Every screen must work at 80×24; bigger terminals only grow the `1fr` regions. From 100 columns `StatusHeader` becomes a 26-column left rail (`app.rail` / `wide(app)`); below that it is one row on top. `tests/test_sizes.py` sweeps every screen and modal at 80×24, 100×30 and 120×36 (no clipped widget outside scroll areas); add new screens and modals there.
- Panels are borderless: `panel(widget, title, subtitle)` adds a one-row `PanelTitle` (change it with `retitle()`), `modal_box()` does the same for dialogs. One focus bar: only the focused panel gets the primary left bar (`.panel`, or `.-focused` for a region that has no focusable widget). App CSS beats `DEFAULT_CSS`, so shared look goes in `hunches.tcss` and per-screen layout in `DEFAULT_CSS`. No round or boxed borders.
- Every key has a button and every button shows its key: build them with `key_button(label, key)` ("Approve seeds  F2"); `AppFooter` drops the keys the rail already shows. One-line messages go through `say()` (hidden when empty). Run screens: `x` stops, `s` starts/resumes; `ctrl+s` saves an editor, `e` edits, `o` edits the prompt and `c` toggles Chat/Results on Tuning.
- Never colour alone: pair it with a word or glyph (PASS, FAIL, STALE, DIFFERS, ■ label).
- Labels render as `label_tag(...)` in Static markup and `label_text(...)` in DataTable cells (DataTable strings use Rich markup, Static uses Textual markup). Cost is `$0.0000`, unknown is `cost ?`.
- DataTable has no flex column: give the Text column a fixed width and resize it after layout (`report.fit_text_column`).

## Testing notes

- Textual: drive with `async with app.run_test() as pilot:`; `await pilot.pause()` before assertions that depend on a message being processed; default terminal is 80×24, pass `size=` when needed.
- Metrics tests compare against hand-computed values written in the test; never derive expected values by running the code under test.
- Use `tmp_path` and `monkeypatch.chdir` for `.hunches/` fixtures.
- "No model call" is proved by counting `FunctionModel` invocations (see `CALLS` in `tests/test_e2e.py`: labelling makes none, the first Tuning run makes one per dev item). `tests/conftest.py` has an autouse `no_real_models` guard that fails any un-stubbed model request, and stubs for the assistant turns screens send on mount (`stub_taxonomy_assistant`, `quiet_tune_assistant`).
- Pilot clicks on a button inside a panel that is not focused may need `offset=(2, 0)`. Importing any `hunches.screens.*` module on its own works (`screens/__init__.py` loads `hunches.app` first).

## Conventions

- Match surrounding code style; comments only where the why isn't obvious.
- One commit per task, descriptive message. Develop on the branch you were assigned; do not open a PR unless asked.
- Don't tag, release or publish. The user pushes tags; PyPI uses trusted publishing (no token in secrets).

## Needs a human (stop and report, don't fake)

API keys, a real embedded corpus, AWS credentials, PyPI trusted-publisher setup, the GitHub `pypi` environment, the `v0.1.0` tag, and (if you can't verify it from AWS docs) the S3 Vectors `topK` maximum. Full list: `specs/001-initial-version/tasks/README.md`.
