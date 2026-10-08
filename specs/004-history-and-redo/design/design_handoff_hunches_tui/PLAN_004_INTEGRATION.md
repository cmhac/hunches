# Integrating the design with the history, stale-stage and gold-orphan spec (001–003)

Written for the agent that implements tasks 08, 09, 10 and 11 of the planning spec. Backend tasks 01–07 are not designed here; this file says what the UI needs from them. The click-through is `reference/ui_kits/tui-rail/index.html` (new states are listed below by id; group "History and redo plan" holds the two new modals). Rules in README.md sections 1 and 3 still apply: do not port the JSX, one mock cell is one terminal cell, everything works at 80×24.

## 0. Answers to the open questions marked for the design agent

| Q | Answer |
|---|---|
| **O4 keys** | `F6` Undo, `F7` Redo, `F8` History, `F9` Redo plan. F-keys are not bound by `TextArea` or `Input`, so they work while the cursor is in a text box. `ctrl+z`/`ctrl+y` keep their text-box meaning (undo typing in an open editor). Check F6–F9 against the installed Textual and common terminals; `F10` was avoided because many terminals take it. |
| **O5 redo plan** | A modal (`RedoPlanScreen`), opened with `F9` or the rail entry. After the user re-approves a stage while a plan is open, the plan reopens with the next stale stage selected and the primary button reads "Continue to <stage>". Nothing is approved for the user (D6). See section 5. |
| **O6 rail** | The rail shows a glyph per stage (`↻` stale, `◐` incomplete) in warning colour, plus a legend line (`↻ stale  ◐ incomplete`) under the stage list. Reasons do **not** fit in 26 columns; they live in the stage screen banner and the Redo plan. Add the reason as the row's tooltip if the installed Textual supports `tooltip`. Narrow header: the same glyphs in the stepper and a STALE or INCOMPLETE reverse badge after the stage name. |
| **O7 held-out wording** | See section 7. Quoted verbatim there. |
| **O2/O3** | Designed as the planner's default: `gold_removed.jsonl` kept (the removal modal says so) and the gold tools on the Tuning assistant only. If you add them to Taxonomy, reuse `tune/remove-gold`'s modal. |

## 1. Undo / Redo (spec item 1) [behaviour]

Buttons ("Undo  F6", "Redo  F7") sit next to the existing edit buttons. They are disabled when `can_undo` / `can_redo` is false and **while that editor has a draft open** (the draft is not in the history; F6 inside an open editor is a no-op). After use, one `.note` line under the buttons: `Undid: <summary>` / `Redid: <summary>`, using the log entry's one-line summary. Clear it on the next edit or screen change.

| Editor | Where | State ids |
|---|---|---|
| Seed list | Brief: in the centred button row, between Delete and Approve; note below | `brief/seeds`, `brief/edits-sent`, `brief/undone` |
| Labels panel | Taxonomy: after "Edit labels e"; wraps to a second row below ~40 columns | `taxonomy/drafted`, `taxonomy/edits-sent` |
| Prompt panel | Taxonomy: after "Edit prompt e", note below | `taxonomy/undone` |
| Prompt (Edit prompt modal) | Tuning: row under the text area, compact buttons | `tune/edit-prompt`, `tune/edit-prompt-changed`, `tune/edit-prompt-undone` |

- **Which stack the key hits:** on Taxonomy, `F6/F7` act on the **focused** panel (Labels or Prompt); the footer keys are dimmed when the chat has focus or the focused stack is empty. The buttons in each panel always act on their own panel.
- **Tuning modal:** F6/F7 step through saved versions of `prompt.md` and put the result in the text area. They are disabled while the text differs from the file (use `ctrl+z` for typing; the line under the buttons says so). After an undo the primary button reads **Re-run  F2** (not "Save and re-run") because the file already changed; it re-runs the dev set. `ctrl+s` is not used.
- **The agent is told.** An undo or redo is a file write and goes through §5 of BACKEND_CHANGES.md like any edit: a "YOU EDITED" line, summary `Undid: …`. Examples: `brief/undone`, `taxonomy/undone`.
- **NeedsVersion:** Undo on Labels when gold labels exist shows a modal "Undo changes the labels" with the diff, **Cancel  Esc** (focused) and **Archive as version 2 and undo**. The version number is the next number from the taxonomy-version code of 003 D12. → `taxonomy/needs-version`. The modal's wording assumes a confirmed undo archives first (as D12 does for other label-changing actions); change the sentence if the planner's flow differs.
- Footer: add `F6 Undo` and `F7 Redo` after the existing keys on Brief and Taxonomy (dimmed when disabled).
- Key list for the footer helper: `F8 History` is global (shown in the narrow footer and as a rail row; hidden from the wide footer). It is dimmed while any editor is open (`brief/history-blocked`).

## 2. History modal (spec items 2, 6) [behaviour] [new screen]

`HistoryScreen(ModalScreen)`, same family as `VersionsScreen`. Open with `F8` or the rail row "History". Size: `width = terminal − 4`, `height = terminal − 2` (same as the proposal modal). Not available while an editor is open (the key does nothing, the rail row and footer key are dimmed). The `tests/test_sizes.py` entry is section 8.

- **Top row:** "file" Select (All files, seeds.csv, taxonomy.yaml, prompt.md) and "newest first · N entries".
- **Timeline** (`DataTable`, focused): columns Time, File, Source, Summary. The newest entry of each file ends with `  (current)`.
- **Source badges** (reverse-video words, one cell padding, same widget family as PASS/FAIL): YOU `-neutral` ($boost), ASSISTANT `-accent` ($accent bg), EXTERNAL `-stale` (warning), UNDO REDO RESTORE `-info`, BASELINE `-muted` ($panel bg, muted text). Add `.badge.-accent`, `.badge.-neutral`, `.badge.-muted` and `.badge.-primary` to hunches.tcss.
- **Event rows** (no file; File column shows `·`): APPROVAL `-pass` ("Approved: Tuning loop (dev accuracy 0.920, prompt version 3)") and VERSION `-primary` ("Taxonomy version 2 saved (50 dev labels kept)"). They are hidden when a single file is chosen.
- **Preview panel** below: default a diff against the file's previous entry (use the existing `Diff` rendering from `ProposalScreen`); `v` toggles to the full text at that time. Subtitle: "this is the current text" or "Restore this makes prompt.md match". Event rows show their details and no diff.
- **Buttons** (right-aligned): **Show text  v** / **Show diff  v** (disabled on event rows), **Restore this  r** (primary; disabled for event rows, for the current row, and for BASELINE), **Close  Esc** (focused).
- **Restore** writes the file through `history.save`/restore so a RESTORE row appears and the restore is itself undoable. Close the modal, show the note `Restored prompt.md to 14:31:07. Undo with F6.` on the screen underneath. If the restore changes labels with gold present it raises NeedsVersion and uses the modal in section 1.
- **Approvals (item 6):** approval rows come from the `approval` log entries of task 03. They are display only. The re-do is the normal approve action of the stage.
- → `history/list`, `history/text`, `history/filter-open`, `history/filtered`, `history/event`, `history/current`, `brief/history-blocked`.

## 3. External change notice (spec item 3) [behaviour]

When `sync()` finds an outside edit, show **once** (per detected change) a tinted block at the top of the content column of the screen the user is on: bold `prompt.md changed outside hunches.` and a button row **Undo  F6**, **History  F8**, **Dismiss  Esc**. Dismiss or any navigation clears it; it is not shown again for the same log entry. Undo reverts to the entry before the EXTERNAL one. The rail then shows the stale marks (section 4). → `taxonomy/external` (the same block can appear on any screen; mount it from the screen base class or `app.py`'s content column).

## 4. Stale markers and banners (spec item 4) [visual] [behaviour]

Source of truth is the planner's `stage_status` (`current` / `stale` / `incomplete`, with a reason string).

- **Rail** (`StatusHeader.-rail`): replace the stage mark with `↻` (stale) or `◐` (incomplete), warning colour, name in warning colour (current stage keeps strong bold on the $panel bar). Under the stage list, one legend row naming only the kinds present: `↻ stale  ◐ incomplete`. In the app items, below System settings, add **History  F8**, and, only when something is stale or incomplete, **↻ Redo plan  F9** (warning). Tooltip per stage row: `5 Tuning loop · STALE: prompt changed` if `tooltip` is available.
- **Narrow header** (<100 columns): same glyphs in the stepper, and a reverse warning badge (STALE or INCOMPLETE) after the stage name. The footer gains `F9 Redo plan` while anything is stale.
- **Stage banners, stages 5–9:** full-width tinted block with a left bar and bold text, the same `.banner.-stale` as the existing Stage 6 banner, one or two lines. Pattern: `STALE: <what changed>. <what the user does>. F9 shows the redo plan.` (Browse uses the warning banner and no "STALE:" prefix, per the spec's "notice".) Wording used in the mocks:
  - 5 Tuning, `tune/stale`: "STALE: prompt.md changed outside hunches since the dev set ran. These results are from the earlier prompt. Press r to re-run, then approve again."  It adds **Re-run  r** (primary, in the action row) and disables **Done  F2** until the dev set has run with the current prompt. `r` is a new binding on Tuning.
  - 6 Test, `final/stale`: existing copy, unchanged.
  - 7 Threshold, `threshold/stale`: "STALE: prompt.md changed since the cutoff 0.650 was saved. The rates below are for the current prompt. Choose a band and save the cutoff again."
  - 8 Full run, `run/stale`: "STALE: results.jsonl was made with an earlier prompt. Re-run classifies every item again; items already cached cost nothing." The Start button reads **Re-run  s**. (The existing `run/untested` hard block still applies first.)
  - 9 Browse, `browse/stale`: "Results come from an older prompt: prompt.md changed after the full run. Press p to go to Full run and re-run."
- **Search** (stage 2, `search/seeds-changed`) keeps its existing "Seeds changed, rerun needed" status; it only gains the rail mark.
- **Order of messages on a stage screen:** stale banner first, then the screen's own notes.

## 5. Redo plan (spec items 5, 6) [new screen]

`RedoPlanScreen(ModalScreen)`, opened by `F9` or the rail row. Width `min(92, terminal − 4)`, height `min(terminal − 2, 24)`.

- Intro line (one of): "These stages were approved before something upstream changed. Nothing is approved for you; each stage needs your approval again." / after a re-approval: "Tuning loop approved again. Next stale stage: Gold test set. …" / when empty: "All stages are current." (success).
- Table "stages in order": mark (`↻` stale, `◐` incomplete, `▸` the next one, `✓` approved again), Stage, Why (`STALE · prompt changed`), **Live**, **Cached**, **Cost**. Rows with no model calls (Search, Gold) show `·`. A last row "Still to do" sums the rows not yet approved.
- **Counts:** Live = calls the model must make, Cached = `classifier.is_cached` true (free). Cost is the live calls only. **Unknown price shows `?`** in the row and in the total, with a warning line naming the model; never `$0.0000`. → `redo/plan-unpriced`.
- **Buttons:** **Close  Esc**, and a primary **Go to <earliest stage>  Enter** (focused). Enter closes the modal and switches to that stage's screen. After the user re-approves a stage **while a plan was started**, open the plan again with the primary button **Continue to <next stage>  Enter**. Track "plan in progress" in memory on the app (set when Enter is pressed from the plan, cleared when the plan is empty or the user closes it twice without progress). When no stage is left, the plan shows "All stages are current." and only Close.
- Never approve for the user: the plan only navigates. The approve action on each stage is unchanged (confirm modal then `files.approve`).
- → `redo/plan`, `redo/plan-seeds`, `redo/plan-unpriced`, `redo/plan-progress`, `redo/plan-done`. The mock numbers are illustrative; Live and Cached must come from `redo_plan`.

## 6. Gold after a seeds change (spec item 7) [behaviour]

- **Search**, after a re-run (`search/gold-orphans`): a one-line warning Notice under the button row: "6 of your 50 dev items are no longer in the candidate pool. Review them on the Gold screen (stage 4)." Show a second sentence for the test split when it also has orphans ("2 of your 50 test items are no longer in the pool."). Source: `orphaned_gold`.
- **Gold screen** (stages 4 and 6; the same code, `split` differs). New states are listed with a `gold/` and `test/` twin:
  - `gold/orphans`: a warning banner at the top of the left column: `ORPHANED: 6 of 50 dev rows are no longer in the candidate pool (4 labelled).` with **Remove stale rows  x** under it. The counts panel subtitle adds `· 6 orphaned`. When the item on screen is orphaned its panel subtitle shows an `ORPHANED` badge. Orphaned rows keep their labels and count as labelled until removed, so progress and Finish gating are unchanged.
  - A new button **Rows  r** under Draw in the right column opens the rows modal (`gold/rows`): every row with Pool status (`ORPHANED` badge or "in pool"), labels and text, and **Remove row  Del** for the selected row (any row, orphaned or not), **Remove stale rows  x**, **Close  Esc**.
  - **Removal is always confirmed** (`gold/remove-confirm`, `test/remove-confirm`): "6 rows are no longer in the candidate pool. 4 of them are labelled; those 4 labels are discarded. The rows are kept in gold_removed.jsonl and are never drawn again." Buttons **Cancel  Esc** (focused) and **Remove 6 rows** (error). For a single row, same modal with n = 1.
  - After removal (`gold/orphans-removed`): an info banner "Removed 6 stale rows (4 labels discarded). The set has 44 of 50 rows. Draw 6 replacements to continue.", **Finish** disabled, and the Draw button becomes **Draw 6 replacements  d** (primary, same `d` key and action as Draw 10 more, with the count set to what is missing). Stage 4 or 6 shows `◐` incomplete in the rail until 50 rows are labelled; "resume goes back to stage 4 or 6" is that status.
- **Held-out warning (O7, test rows only)**, added to the removal confirm, warning colour: "Test rows are held out so that the test result is an honest estimate. Replacing labelled test rows changes the items the result is measured on, and the test evaluation has to be run again. Do not remove rows because the classifier got them wrong." Show it whenever the split is `test`, even if only unlabelled rows are removed. After test removal the info banner adds "The test result is stale until you re-run it." (`test/orphans-removed`).

## 7. Assistant (spec item 8) [behaviour] [backend]

On Tuning (O3 default):
- New context sections **# Status** (one line per stage with its stale reason) and **# Gold coverage** (rows, in pool, orphaned, labelled) arrive as the existing collapsed context line, with an UPDATED summary such as "Status · 4 stages stale · 6 of 50 dev rows orphaned" and a short assistant reply. → `tune/status-context`.
- New read-only tool for coverage renders as a normal expandable tool line (the mock calls it `get_gold_coverage`; use the planner's name). → `tune/gold-coverage`.
- `remove_gold` returns "Waiting for the user to confirm." and shows the tool line `remove_gold  waiting for your confirmation`; the **same removal modal** as the Gold screen opens, titled "The assistant wants to remove 6 dev rows", with **Reject  Esc** (focused) and **Remove 6 rows**. Nothing is removed until Remove is pressed. → `tune/remove-gold`.
- No tool sets a label; none of the mocks shows one.

## 8. Sizes to add to `tests/test_sizes.py` (task 11)

Each new screen at 80×24, 100×30, 120×36: `HistoryScreen` (list, text, filter open), `RedoPlanScreen` (plan, unpriced), the gold rows modal, the removal confirm (dev and test, the test one has the longest text), the NeedsVersion modal, the external-change block on Taxonomy at 100 columns (right column is about 31 wide: button row wraps to two rows), Brief and Taxonomy button rows with Undo and Redo, Tuning with the stale banner (four buttons in the second action row), Gold with the orphan banner at 80×24 (progress block, banner, item, labels must still fit; item panel may shrink to 2 rows).

## 9. Not designed

- Search warning when `candidates.meta.json` has a different `embedding_model` (backend records it; no UI asked).
- A history badge or counter on the rail.
- Restore preview of three-way diffs for EXTERNAL rows (diff against previous is enough).
