# 17 — End-to-end, size sweep, docs

Depends on all earlier tasks.

## Do
- **E2E (`tests/test_e2e.py`).** Update the full flow through all nine stages for the new behaviour, with stubbed models and a tiny hand-built corpus: approve seeds via the button → run search (button, no confirmation on first run) → taxonomy context turn then Save labels and prompt → Approve → label the dev set by keys with **no model calls** during labelling → Tuning first run (indicator, then results) → Done → label the test set → Test run → Accept → Threshold (choose a band, Save) → Full run (Start button) → Browse. Include the pool-short blocked path once (a corpus under 50 candidates).
- **Size sweep.** One parametrised Pilot test that mounts every screen (all nine stages, Projects, System settings, New project, Project settings, and each modal) at 80×24, 100×30 and 120×36 and asserts no unhandled exception, that the rail is present at ≥100 and absent below, and that no widget is clipped (`widget.region` inside `screen.region`) except scroll areas.
- **Docs.**
  - `AGENTS.md`: update "Current state" (003 implemented), the layout list (`screens/progress.py`, `chat.py` if created), "TUI look" (rail at ≥100, borderless panels with a title row, buttons-for-every-key rule, one focus bar, `panel()`/`retitle()`/`key_button()`/`say()` helpers, `LabelBar`/`RunIndicator`) and the testing notes (counting `FunctionModel` calls to prove "no model call").
  - `README.md`: the new layout and keys (`ctrl+s`, `o`, `c`, `x`/`s` on run screens); that labelling no longer classifies so the first Tuning run classifies the whole dev set; that the classifier now returns reasoning and the **first run after upgrading is billed again because the cache key changed** (spec conflict 4); that Threshold cutoffs are band edges.
  - `specs/001-initial-version/spec.md` and `specs/002-onboarding-setup/spec.md`: add a one-line pointer to 003's "Behaviour that changes in 001 and 002" list at the top (do not rewrite history).
  - `examples/sample/`: confirm it still opens and runs through the stages by hand if a key is available (no change expected).
- **Cleanup.** Delete dead CSS (round-border rules), unused imports and unused helpers left by earlier tasks (`build_instructions`, `show_prediction`, old `seconds_text` location). `uv run ruff check`, `ruff format --check`, `ty check` and `pytest` all clean.

## Needs human
- Manual pass in a real terminal at 80×24, 100×30 and 120×36 with a real API key and a small real corpus: rail, footer, every stage, a Stop/Resume mid-run, `ctrl+s` inside tmux (spec O4), F-keys (spec 002 O-item), the D2 footer geometry.
- Spec Open items O1, O2, O3, O5 decisions.

## Done when
- CI-equivalent commands pass; docs match behaviour; the human pass is listed in the final message.
