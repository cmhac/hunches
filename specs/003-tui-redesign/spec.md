# 003 — TUI redesign: rail layout, structured editing, assistant context

Status: draft for implementation. Builds on `../001-initial-version/spec.md` and `../002-onboarding-setup/spec.md`, both implemented. Written 2026-10-05 against `main` at `2278ad0` ("Merge pull request #4 …system-and-project-setup").

**Source.** A design handoff from the frontend design agent (`Content_analysis_toolkit_spec.zip`). It is a change set against `main` at that same tree (`2278ad08fd5c`, verified), not a fresh design. The handoff is copied unmodified into [`design/`](design/) so tasks can cite it. This spec is the result of reading all of it, reading the code it targets, and checking its open questions against the installed Textual 8.2.8 and pydantic-ai 2.53.

**Read order for an implementer:** this spec → your task file → the handoff passages the task names (`design/README.md`, `design/BACKEND_CHANGES.md`, and the mock state ids in `design/reference/ui_kits/tui-rail/*.jsx`).

## What this is, in one paragraph

A visual and behavioural overhaul of every screen, plus the backend changes the design depends on. Visual: a 26-column left rail (stage list, destinations, cost) at ≥100 columns, borderless tinted panels with a left focus bar, one-row inputs and buttons, raised modals. Behavioural: every key action also has a button; Save/Create/Finish/Approve are disabled until valid instead of showing an error afterwards; Brief and Taxonomy lose their raw-file views in favour of structured read and edit modes with explicit Save and Discard; every classifier run shows one centred progress indicator with Stop and Resume. Backend: the assistant gets the same context the user has (taxonomy and tuning chats open with a context turn; every saved user edit is recorded in the agent's history; current state is in its per-run instructions); Tuning becomes a chat with two tools; the classifier returns reasoning; gold labelling no longer calls the classifier; search remembers which seeds it was built from.

## Principles

Same as 001 and 002 (minimal implementation; no abstraction, base class, registry or plugin system unless asked; plain files in `.hunches/` are the only state; check every Textual and Pydantic AI API against the installed version and current docs; never call a real LLM or AWS in tests; unknown cost is `?`, never `$0`). Additional rules for this spec:

- **Do not port the JSX.** Recreate the look with Textual widgets and TCSS. One mock cell is one terminal column by one row. Every screen works at 80×24, 100×30 and 120×36; bigger terminals only grow `1fr` regions.
- **A guard is never removed when its error message is.** The design replaces "press the key, read the error" with a disabled button. The `action_*` still checks the same condition and returns silently (the key can still be pressed).
- **The handoff's tags** are kept in task files: `[visual]` (TCSS/markup/composition only), `[behaviour]` (UI logic), `[backend]` (data, stored state, agent). Visual-only work must not change logic.
- Copy is exact where the handoff quotes it. Do not paraphrase quoted strings; tests assert them.

## Resolved decisions

The handoff leaves several questions to the implementer ("§6 Open questions"). Each was checked against the installed versions on 2026-10-05; the answers are decisions here, not suggestions.

| # | Question | Decision | Evidence |
|---|---|---|---|
| D1 | Does `border_title` render without a visible border? | **No.** Use a one-row title widget. | Probe on Textual 8.2.8: `border: none` and `hidden` render no title; `border: blank` renders it but costs a row at top and bottom and a column each side, and a subtitle cannot share the title's row. `Widget.compose_add_child(Static(...))` called inside `panel()` puts a one-row child first, so `panel(widget, title, subtitle)` keeps its signature. Subtitles with badges (`EDITING`, `UNSAVED`, `UPDATED BY ASSISTANT`, the Search threshold select) therefore render in that row. |
| D2 | Can the footer sit under the content column only, with the rail docked left? | **Yes, with an explicit width.** A `dock: left; height: 100%` rail offsets the content automatically. `Footer` docks bottom at full screen width and so runs under the rail; giving it `margin-left: 26` alone shifts it right but leaves its width at 100%, overflowing the screen (probe: x=10, width=40 on a 40-column screen). Set the footer's width to `screen width − 26` from `on_resize`. If that proves fragile, fall back to the rail ending one row above a full-width footer and tell the user. | Probe, same run. The width fix itself was not probed. |
| D3 | Hiding `q n p F3 F4 F5` from the footer in wide mode | Filter in a `Footer` subclass (or hide the `FooterKey`s after compose). **Not** via `check_action` returning `False`: that also disables the key, and the keys must keep working. | Reading `Footer.compose`: it lists every active binding with `show=True`. |
| D4 | How to mark context / update / edit turns in the chat history | `ModelRequest.metadata` (a dict field; round-trips through `ModelMessagesTypeAdapter`, verified). Convention: `{"hunches": "context" \| "update" \| "edit"}`. `agent.run_stream(..., metadata=...)` sets *run* metadata only, not the message's, so for model-backed context turns set `.metadata` on the first request in `result.new_messages()` before `files.save_chat`. Edit lines (no model call) are hand-built `ModelRequest(parts=[UserPromptPart(...)], metadata=...)`. No sentinel-prefix fallback needed. | Probe: `[ModelRequest, ModelRequest, ModelResponse]` runs fine, so two consecutive requests (an edit line then the user's next message) are accepted. |
| D5 | Per-run agent instructions | `@agent.instructions` exists in pydantic-ai 2.53 and is evaluated every run (verified: its text appears on the request). **Side effect:** `ModelRequest.instructions` is persisted, so `chat/<stage>.json` would carry the full current state on every turn. Clear `.instructions` on requests before `files.save_chat`; they are recomputed each run. | Probe. |
| D6 | Awaiting a modal inside an agent tool | `await self.app.push_screen_wait(...)` inside a worker. It exists on `App` only (not `Screen`) in Textual 8.2.8. `ChatPanel.reply` already runs in a worker. | Probe. |
| D7 | Wording of the Edit prompt modal note (handoff BACKEND §11.6 offers two) | "The dev set is classified again with the new prompt." The classifier's cache key hashes the whole system string (`classifier.system_prompt`), so any prompt edit invalidates every item. | `classifier.py`, `cost.cache_key`. |
| D8 | ETA when the cache skews the rate (BACKEND §8) | `classify_many` already reports it: `Prediction.cached`. ETA = `(total − done) × elapsed ÷ live_done`, shown only once `live_done ≥ 3`. | `classifier.Prediction.cached`. |
| D9 | What "leaving the screen" stops (BACKEND §12.4) | A stage switch (`goto_stage`, `switch_to`) removes the screen, which cancels its workers; make that explicit and test it. Overlays (Project settings F3, Projects F4, System F5) do not stop a run; `app.open_project` already asks before switching away from a running one. | `app.py`. |
| D10 | `include_reasoning` flag for the full run (BACKEND §10.5) | **Not added.** Reasoning is stored for dev and test runs only; `results.jsonl` is unchanged. Add the flag only if asked. | Minimal-implementation principle. |
| D11 | Which prompt counts as "tested" for the Full run hard block | The prompt recorded in `test_result.json` (`final.prompt_hash`, which already covers `prompt.md` plus the classifier model). There is no per-dev-run record to compare against and none is added. See Open item O2. | `final.py`, `run.py`. |

## Conflicts and corrections in the handoff

Found while cross-reading. Resolutions are binding for the tasks.

1. **README §2 says `theme.py` and `hunches.tcss` "match `textual/`". They do not.** `main` is newer (it has `label_tag`/`label_text`/`editor`, `ConfirmScreen`/`PathPicker`/`Bar`/`SelectionList`/`ProgressBar` rules, `.panel.-focused`). Keep `main`'s files; ignore `design/…/textual/` (not copied).
2. **Newest-first change log beats the §5 per-screen lists** where they disagree. §5 was not fully updated:
   - Threshold: §5 says "Save cutoff next to the cutoff input; disabled until the input is a number". The change log removes the input: the cutoff is chosen by selecting a band row. **Follow the change log** (task 12).
   - Tuning controls: §5 lists a target select row, then Propose / Done. The change log has row 1 = target select, `−`, value, `+`; row 2 = `Propose edit  e`, `Edit prompt  o`, `Done  F2`. **Follow the change log** (task 15).
   - Full run: §5 keeps the estimate and run panels and a Start/Stop button pair. The change log reduces it to one centred block. **Follow the change log** (task 14).
   - Keys: §2 says the only new keys are `ctrl+s` and Enter/Esc in editors. The change log adds `o` (Edit prompt), `c` (Tuning chat/results tab), and `x`/`s` (Stop/Resume) on Tuning, Test and Threshold. **The list in §2 is out of date.**
3. **BACKEND §11.7 says "labels stay locked once gold labelling has started". Nothing in the code locks them** (`p` reaches Taxonomy at any time and the screen is editable). This spec does not add a lock. See Open item O1.
4. **BACKEND §10 changes the string the cache hashes** (`classifier.system_prompt`). Consequence for existing projects: the first dev/test/threshold run after upgrading re-classifies everything and is billed. `final.prompt_hash` does *not* cover the system sentence, so an existing `test_result.json` is not marked STALE. It also has no `reasoning` key in its disagreements, so the Test and Tune detail panels must tolerate a missing one (task 13).
5. **Removing classification from Gold (BACKEND §6) removes the cache warm-up** Gold used to give Tuning, so the first Tuning run costs the full dev set. Intended; nothing to do, but state it in the README (task 17).
6. **BACKEND §4 relies on `ChatPanel`'s Input bubbling `Input.Submitted`** (today `BriefScreen.on_input_submitted` writes `brief.md` from the first chat message). The new `ChatPanel` has a send button too, so it must post its own message (task 3) and Brief handles that instead.
7. **`run.seconds_text` prints `0m14s`** (BACKEND §8 notes it). It moves with `RunIndicator` and drops the leading `0m` (task 11).
8. **Gold milestone wording.** README §5 quotes "Halfway there. 25 to go."; the mock (`Gold.jsx`) renders "Halfway. 25 to go.", and gives names only for the other milestones. The README's string is used for 50 %; "A quarter of the way there." and "Three quarters of the way there." follow it (task 09). Confirm with the design owner if exact copy matters.
9. **Rail/footer copy.** The System settings note "the header shows actual spend" becomes "the sidebar shows actual spend" at ≥100 columns and keeps "header" below.

## Layout and file changes

| Area | Files | Task |
|---|---|---|
| Global styles, `panel()` title row, buttons, modals, not-ready | `hunches.tcss`, `app.py` | 01 |
| Rail shell, footer under content column | `app.py` (`StatusHeader`), `hunches.tcss` | 02 |
| Chat panel as widgets, context/edit/tool lines, edit recording | `app.py` (`ChatPanel`; may move to `chat.py`), `files.py` | 03 |
| System settings, recommendation modal, New project, Project settings, pickers | `screens/system.py`, `new_project.py`, `project_settings.py`, `model_picker.py`, `paths.py` | 04 |
| Projects, RemoveModal | `screens/projects.py` | 05 |
| Brief: seed list editor, buttons | `screens/brief.py` | 06 |
| Search: staleness, progress, buttons, bands as bars | `screens/search.py`, `candidates.py` | 07 |
| Taxonomy: context turn, mode select, view/edit with drafts | `screens/taxonomy.py` | 08 |
| Gold: no classification, pool errors, progress block, finish gating | `screens/gold.py` | 09 |
| Classifier reasoning | `classifier.py`, `cost.py` (cache shape), `files.py` | 10 |
| `RunIndicator`, ETA, Stop/Resume | new `screens/progress.py` | 11 |
| Threshold: band selection, run indicator | `screens/threshold.py` | 12 |
| Test evaluation | `screens/final.py` | 13 |
| Full run | `screens/run.py` | 14 |
| Tuning results column, buttons, Edit prompt modal, run indicator | `screens/tune.py` | 15 |
| Tuning chat, tools, context, proposal cards | `screens/tune.py` | 16 |
| E2E, size sweep, docs | `tests/`, `README.md`, `AGENTS.md` | 17 |

## New and changed stored data

All additive; nothing needs migrating by hand.

| File | Change |
|---|---|
| `.hunches/candidates.meta.json` (new) | `{"seeds_digest": "...", "written_at": "...", "floor": 0.6}`, written by `build_candidates` with `candidates.jsonl`. Absent (old projects) means "unknown": treat as *seeds unchanged* so existing results don't flash a false "seeds changed" (task 07). |
| `.hunches/chat/taxonomy.meta.json` (new) | `{"context_digest": "...", "sent_at": "...", "seeds": [...], "n_candidates": N, "items_won": {seed: n}}` (BACKEND §1). The digest is only a change detector; the snapshot is what lets the UPDATED message say what changed ("seeds: 2 added, 1 removed", "candidates: 3,612 → 4,019"), which the handoff asks for but does not store. |
| `.hunches/chat/tuning.meta.json` (new) | `{"context_digest": "...", "sent_at": "...", "metrics": {...}}` (BACKEND §9.3); same reasoning: the snapshot of the last-sent metrics lets the UPDATED line show before/after. |
| `.hunches/chat/<stage>.json` | History now contains `ModelRequest`s with `metadata={"hunches": …}` (D4), and never persists `instructions` (D5). Old files load unchanged. |
| `.hunches/test_result.json` | Each disagreement may carry `"reasoning": str`. Readers tolerate its absence. |
| Classifier cache entries | `{"output": labels, "reasoning": str}`. An entry without `reasoning` is a miss. The system-string change already invalidates old keys. |
| `candidates.jsonl`, `gold.jsonl`, `state.json`, `config.toml`, `threshold.json`, `results.jsonl`, `system.json` | Unchanged. |

## Behaviour that changes in 001 and 002 (explicit list)

1. 001 stage 1: the seeds file is no longer shown or named in the UI; edit and add are explicit (Save/Discard); approval is a button; confirm text "Approve N seeds and start searching?".
2. 001 stage 2: re-running with unchanged seeds asks for confirmation; changed seeds show "Seeds changed, rerun needed"; the "Done…" paragraph is gone; the S3 cap warning text changes.
3. 001 stage 3: no raw YAML/markdown editing; nothing is written per keystroke; the agent is told about every saved edit and starts with context; the mode is a user choice in the UI. Approve is a button; confirm text "Approve taxonomy (single, 3 labels) and prompt, and start labelling?".
4. 001 stage 4 and 6 (labelling): the classifier no longer runs while labelling; finishing requires every row labelled; a too-small candidate pool is a blocking error.
5. 001 stage 5: the one-shot proposal call is replaced by a chat with `get_disagreements` and `propose_prompt`; manual prompt edit (`o`); the metric target is controlled by buttons.
6. 001 stage 6 test evaluation: classifier runs show a centred progress view with Stop/Resume; disagreements show classifier reasoning.
7. 001 stage 7: the cutoff is a band's lower bound chosen by selection; the free-number input and its parsing are removed (arbitrary in-between cutoffs are no longer enterable).
8. 001 stage 8: an untested or changed prompt is a hard block (no "press s again to start anyway"); the estimate/run panels and failed-item list are replaced by one centred block.
9. 002: Save/Create are disabled until valid (their error paths remain as guards); `DIFFERS from recommended` and the separate price-warning line are replaced by per-row markers.
10. Every classifier run (Tuning dev run, Test run, Threshold sampling, Full run) can be stopped and resumed.

## Testing

- Existing tests assert on `border_title`, `#seed-input`, `#prediction`, the `Model:` line, `"Cannot approve"`, `"N items still unlabelled."`, `"Add at least one seed first."`, `"ERROR: save at least one API key first"`, `"Searching..."`, `#cutoff`, `"press s again"`, and the old chat `RichLog`. Each task lists the ones it breaks; update or delete them in the same commit. Do not leave skipped tests.
- New logic gets unit tests with hand-computed expectations (milestone arithmetic, ETA, top-seeds threshold counts, digests, the staleness rules). Never derive an expected value by running the code under test (AGENTS.md).
- Chat and agent behaviour: `TestModel`/`FunctionModel` only. Assert "no model call" for edit recording by counting `FunctionModel` invocations.
- Every restyled screen keeps its Pilot smoke test and runs it at 80×24, plus one run at 100×30 (rail) and 120×36 where the layout differs. Task 17 adds the sweep.
- No snapshot tests of colours; assert words and glyphs (PASS, FAIL, STALE, `■`, `●`) per the "never colour alone" rule.

## Out of scope

- Any change to stage order, `first_incomplete_stage`, `state.json` fields, `metrics.py`, cost tracking, the keyring, or `files.Config`.
- A light theme. Mouse-only affordances beyond the buttons the design lists.
- The optional early warning on Search ("Only N candidates found. Labelling needs at least 100", BACKEND §7). The design owner has not signed it off; see Open item O3.
- Porting any JSX, `reference/ui_kits/tui` (superseded) or the old `textual/` drop-ins.

## Open items to flag, not guess

- **O1 — Taxonomy lock.** BACKEND §11.7 assumes labels are locked once gold labelling starts; the code does not lock them, and editing labels after gold rows exist silently invalidates them. Decide: add a lock (small: `TaxonomyScreen` read-only once `gold.jsonl` has labelled rows) or leave as is. This spec leaves it as is. *Needs Chris.*
- **O2 — "Tested prompt" for the Full run block.** D11 uses `test_result.json`'s hash. Consequence: after the user changes the prompt in Tuning post-test, Full run is blocked until Test is re-run, and the block's button reads "Go to Tuning loop" per the design, though the next step after tuning is Test. Decide whether the button should go to stage 6 instead. *Needs Chris.*
- **O3 — Early pool warning on Search.** Not designed; not built. *Needs the design owner.*
- **O4 — `ctrl+s`.** The design saves Brief/Taxonomy edits with `ctrl+s`. Textual runs the terminal in raw mode so it should arrive, but verify in a real terminal and inside tmux/screen; pick an alternative if swallowed (as with the F-keys in 002).
- **O5 — Footer under content column (D2).** If the explicit-width approach is fragile across Textual versions, the fallback changes the look slightly. Confirm with the design owner if the fallback is used.
- **Needs a human:** the manual pass at the end of task 17 (a real terminal at 80×24, 100×30, 120×36; a real key; a real small corpus). Agents cannot fake it.
