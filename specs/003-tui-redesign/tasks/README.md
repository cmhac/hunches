# Tasks for 003 — TUI redesign

Read `../spec.md` first, then your task file, then the handoff passages it names (`../design/README.md`, `../design/BACKEND_CHANGES.md`, state ids in `../design/reference/ui_kits/tui-rail/*.jsx`). The spec is the source of truth; if a task file and the spec or handoff disagree, flag the conflict rather than guessing. 001 and 002 are implemented; these tasks modify that code.

## Rules for every task

Same as `../../002-onboarding-setup/tasks/README.md` (minimal implementation; check every Textual and Pydantic AI API against the installed version and current docs; never call a real LLM/AWS/keyring in tests; `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest` all pass; one commit per task; list anything only a human can do under "Needs human"). Extra:

- Every task leaves the app runnable and every screen working at 80×24. Tasks are ordered so a half-finished redesign never ships a broken screen.
- A task that removes a visible error message keeps the guard behind it (spec "Principles").
- Update or delete the existing tests the task breaks, in the same commit. The task lists the known ones (found by grepping `tests/` on 2026-10-05); grep for others.
- Mock state ids (`gold/single`, `tune/below`, …) are in the `.jsx` files under `../design/reference/ui_kits/tui-rail/`. Each has a `when:` line. Serve the catalogue with `cd ../design/reference && python -m http.server` and open `ui_kits/tui-rail/index.html` (click-through) or `states.html` (gallery). It loads React from unpkg, so it needs network.
- Measurements in the handoff were taken from mocks, not from Textual. Treat pixel-level claims ("half a row above the footer") as targets and decide on whole rows when you see it.

## Order and dependencies

| # | Task | Depends on | Can run in parallel with |
|---|------|-----------|--------------------------|
| 01 | Global styles: `panel()` title row, components, buttons, modals, not-ready | — | 10 |
| 02 | Rail shell and footer | 01 | 03–05, 10 |
| 03 | Chat panel as widgets; context, edit and tool lines; edit recording | 01 | 02, 04, 05, 10 |
| 04 | Settings family: System, recommendation modal, New project, Project settings, pickers | 01 | 02, 03, 05, 10 |
| 05 | Projects screen and RemoveModal | 01 | 02–04, 10 |
| 06 | Brief: seed list editor, buttons, edits sent | 01, 03 | 07, 09 |
| 07 | Search: staleness, progress, buttons, bands as bars, top seeds | 01 | 06, 09 |
| 08 | Taxonomy: context turn, mode select, structured view and edit | 03, 07 | 09 |
| 09 | Gold: no classification, pool errors, progress block, finish gating | 01 | 06–08 |
| 10 | Classifier returns reasoning | — | 01–09 |
| 11 | `RunIndicator`, ETA, Stop and Resume | 01 | 06–09 |
| 12 | Threshold: band selection, run indicator | 11 | 13, 14 |
| 13 | Test evaluation: buttons, run indicator, reasoning | 10, 11 | 12, 14 |
| 14 | Full run: one centred block, untested-prompt block | 11, 13 | 12 |
| 15 | Tuning results column, buttons, Edit prompt modal, run indicator | 10, 11 | 12–14 |
| 16 | Tuning chat: tools, context, proposal cards, layout, tabs | 03, 08, 15 | — |
| 17 | End-to-end, size sweep, docs | all | — |

Merge conflicts to expect: 01 and 02 both edit `app.py` and `hunches.tcss` (keep hunks separate); 03 and 16 both touch `ChatPanel`; 11 moves `seconds_text` out of `screens/run.py` (12–14 import the new location); 15 and 16 both rewrite most of `screens/tune.py` (16 starts from 15's result); 06 and 08 both add to `files.py` only through 03's helper.

## Needs human (summary)

| When | Who | Action |
|------|-----|--------|
| Task 02 | agent, then flag | If the explicit-width footer (spec D2) is fragile and the fallback is used, tell Chris and the design owner. |
| Before/after task 08 | Chris | Spec Open item O1: should Taxonomy lock once labels are used by gold rows? Default: no. |
| Before task 14 | Chris | Spec Open item O2: where the Full run block's button goes (Tuning vs Test). Default: Tuning, as designed. |
| Task 17 manual check | Chris | A real terminal at 80×24, 100×30 and 120×36 with a real key and a small real corpus; check `ctrl+s` in tmux (spec O4). |
