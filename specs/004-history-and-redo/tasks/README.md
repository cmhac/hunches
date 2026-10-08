# Tasks for 004 — history, undo/redo and redoing downstream work

Read `../spec.md` first (the source of truth), then your task file. UI tasks (08-10) also read `../design/design_handoff_hunches_tui/PLAN_004_INTEGRATION.md`, `README.md`, `BACKEND_CHANGES.md` §13-16 and the `.jsx` mocks under `reference/ui_kits/tui-rail/`; where the spec's "Design handoff: what this spec changes" differs from the handoff, the spec wins. If a task file and the spec disagree, flag it instead of guessing; if the spec is wrong or incomplete, say so and fix it in the same change.

## Rules for every task

- Repo rules in `/home/user/hunches/CLAUDE.md` apply (minimal implementation, no real LLM/AWS/keyring in tests, check Textual and Pydantic AI APIs against the installed version, 80x24 sizes).
- **Red/green TDD, shown in the work.** Write the failing tests first and run them to see them fail for the right reason; then implement until they pass. Report, per behaviour, the failing run (command and failure message) and the passing run. Expected values are hand-written in the tests.
- `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest` all pass before the commit. Report their actual output summaries.
- One commit per task on branch `claude/stoic-davinci-ymhjjd`; commit message `004/NN: ...`; do not open a PR; do not push (the overseer pushes).
- Update or delete existing tests the task breaks, in the same commit.
- Final report: what changed, files touched, red/green evidence, check outputs, deviations from the spec, anything only a human can do.

## Order

| # | Task | Depends on |
|---|------|-----------|
| 01 | history.py core | — |
| 02 | Route writers through history.save; NeedsVersion | 01 |
| 03 | files.approve, State.inputs | 01 |
| 04 | Components, run_digest, stage_status | 03 |
| 05 | classifier.is_cached, redo_plan | 04 |
| 06 | Gold orphans and removal | 04 |
| 07 | Assistant context and gold tools | 04, 06 |
| 08 | UI: undo/redo, History modal, external notice | 02 |
| 09 | UI: stale markers, Redo plan, embedding warning, Tuning `r` | 04, 05 |
| 10 | UI: gold orphan handling | 06 |
| 11 | Docs, e2e, size sweep | all |

Run strictly in order.
