# 08 — App shell, header and resume

Spec section: Stages (preamble), Cost and timing.

## Goal
The Textual app that hosts all stage screens, shows the persistent header, and starts at the first incomplete stage.

## Do
- Read the Textual docs for `Screen`, `Header`/custom header widget, reactive attributes, workers and `push_screen`/`switch_screen` first.
- `app.py`: `HunchesApp` with a custom header: project name (cwd name), current stage name and number, total cost from `cost.total()`. Unknown cost is shown as `?` with a prominent warning style and a text such as "cost unknown for <model>". Never `$0`. The header refreshes after every recorded call (a reactive value or a message posted by the cost recorder).
- Stage registry is a plain list/dict of `(number, name, ScreenClass)`; no plugin mechanism. Until later tasks land, use a placeholder screen per stage.
- First-run flow: if `.hunches/` does not exist, a small setup screen asks for backend and data location, smart/cheap model strings and writes `config.toml` (task 03). Keep it to a form.
- On start, call `first_incomplete_stage()` and show that screen. Keys: next/previous stage with a short key set, `q` quits. Navigating backwards is always allowed.
- Reusable bits that stages need and that belong here, nothing more: a chat panel widget (`RichLog` + `Input`) that streams an agent reply into the log and persists history to `chat/<stage>.json`; a confirm-approve helper that sets a `state.json` flag.
- Tests with Pilot: starts at the right stage for each state; header shows `?` when an unknown-cost record exists; cost updates after a recorded call (`await pilot.pause()`); quit works.

## Done when
- Smoke tests pass; `uv run hunches` in a scratch dir walks through setup into stage 1 placeholder.
