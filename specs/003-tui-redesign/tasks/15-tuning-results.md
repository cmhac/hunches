# 15 — Stage 5 Tuning: results column, buttons, Edit prompt modal, run indicator

Spec: conflict 2, D7. Handoff: `design/README.md` §5 "5 Tuning (`screens/tune.py`): assistant chat" (layout bullets only) and "5 Tuning buttons"; the change-log entries on Tuning controls, `Edit prompt  o`, reasoning, spacing, time remaining; `design/BACKEND_CHANGES.md` §8, §10 (UI part), §11 (modal part); mock `ui_kits/tui-rail/Tune.jsx`; states `tune/below`, `tune/pass`, `tune/first-run`, `tune/rerun`, `tune/stopped`, `tune/failed-item`, `tune/metric`, `tune/edit-prompt`, `tune/edit-prompt-changed`, `tune/rerun-manual`, `tune/not-ready`. `[behaviour]` + `[visual]`. File: `screens/tune.py`.

## Goal
Rework the results side of Tuning (everything except the assistant chat, which is task 16): controls as buttons, a manual prompt edit, the centred run indicator, reasoning in the detail panel. The one-shot `propose()` stays working until task 16 replaces it.

## Do
- **Layout (results column).** Order: dev-set metrics panel (summary line + per-label table + trend), then the disagreements `DataTable` with the selected item's text panel, then the action row. At 120 columns and wider the table and text panel are stacked and share the height 5:4 so the text and reasoning stay visible; under 120 they sit side by side. The text panel is a `VerticalScroll` (long text and reasoning scroll at 80×24). Toggle in `on_resize` as `BrowseScreen` does.
- **Controls** (change-log version): a `Vertical` with `height: 3; align: center middle`, both rows centred horizontally in the results column, half a row apart (decide whole rows). Row 1: a **Target** `Select` (the metric; `m` opens/cycles), `−` button, the value (`target_score`, 2 dp), `+` button — all compact; no caption. Row 2: **Propose edit  e** (disabled without disagreements, while running, or while a reply streams), **Edit prompt  o**, **Done  F2** (success when the target is met, default otherwise; disabled before the first result). Buttons call `action_next_metric`/`action_score(±0.01)`/`action_propose`/`action_edit_prompt`/`action_done`. The panel subtitle no longer lists `m metric · +/- score`.
- **Remove** the "Dev run finished, cost $…" note and the "Asking the assistant…" note (the reply will stream in the chat, task 16; until then `propose()` keeps a short note). The note line is `display: none` when empty.
- **Run indicator.** While the dev run is in progress or stopped (first run, re-run after an accepted proposal, re-run after a manual edit): hide the metrics and table panels and show `RunIndicator` (task 11): title "Running the dev set", counts from `done` in `run_dev`, ETA per D8, `Stop  x` / `Resume  s`. The chat (task 16) hides with them. On failure show the existing panels (or empty state) with the failure note `Dev run failed: …`. Hide with `display = False` toggled by `self.running`/`self.stopped` so state survives.
- **Reasoning.** The detail panel is titled "text · classifier reasoning": item text, then a bold teal `classifier reasoning` heading and the reasoning (`Prediction.reasoning`, task 10), kept in a per-run `self.reasoning: dict[int, str]` next to `self.errors`. Failed items show only the existing "Model failed: …" line.
- **Edit prompt (`o`, BACKEND §11).** `Binding("o", "edit_prompt", "Edit prompt")`. A new `PromptEditScreen(ModalScreen[str | None])` (reuse `ProposalScreen`'s layout without the diff): an editable line-numbered `TextArea` (markdown) loaded with `prompt.md`, a caption, the note "The dev set is classified again with the new prompt." (D7), and buttons **Cancel  Esc** (dismiss `None`) and **Save and re-run  F2**, disabled until the text differs from the file (compare on `TextArea.Changed`). Disabled while a run is in progress or before the first result; single-letter keys do not fire while the chat input has focus (task 16). On save: `files.write_text("prompt.md", text)`, `self.prompt = text`, then the same `rerun()` that `accepted()` uses. **No model call except the re-run itself.** (Telling the assistant and superseding pending proposals is task 16.)
- `ProposalScreen` keeps its content, restyled by task 01.
- Footer: `Propose / Metric / Done` short labels at <120 columns (README's chat-tab bullet), `c Chat` is added by task 16.

## Tests
- Controls: buttons mirror their actions (target select changes `config.target_metric` and writes `config.toml`; `+`/`−` step ±0.01 clamped to [0, 1]); Done is success-variant only when `met()` and disabled before a result; Propose disabled without disagreements.
- Edit prompt: Save disabled until text differs; saving writes `prompt.md`, sets `self.prompt` and starts a re-run (call counter on the classifier); Cancel writes nothing.
- Run indicator: panels hidden while running/stopped, shown after; Stop/Resume per task 11; `done` and ETA render.
- Reasoning: detail panel shows heading and text for a disagreement with reasoning; failed item shows no reasoning.
- Layout switch at 119 vs 120 columns (side by side vs stacked).
- Breakers in `tests/test_tune_screen.py`: `#note` run text, `Dev run finished`, `Asking the assistant`, subtitle text, `border_title`.

## Done when
- `tune/*` results states match at the three sizes; the screen still works end to end with the old one-shot proposal.
