# 06 — Stage 1 Brief: seed list editor, buttons, edits sent to the agent

Handoff: `design/README.md` §5 "1 Brief and seeds"; `design/BACKEND_CHANGES.md` §3 (Brief bullet), §4 (Brief), §5 (Brief rows); mock `ui_kits/tui-rail/Brief.jsx`; states `brief/empty`, `brief/seeds`, `brief/editing`, `brief/adding`, `brief/confirm`, `brief/edits-sent`, `brief/tool-open`. `[behaviour]` + `[backend]`. File: `screens/brief.py`.

## Goal
Seeds are a numbered list titled "Seeds" with a count. Edit and add are explicit (Save/Discard). Every saved change reaches the agent.

## Do
- **Seeds panel.** Title "Seeds" with the count in the subtitle (not `seeds.csv · N`). Replace the `DataTable` with a `ListView` or a `VerticalScroll` of rows (a `DataTable` cannot embed an `Input`): number column `#`, then the phrase. Selection/cursor via the arrow keys as today.
- **Edit (`e`).** The selected row becomes an `Input` holding its text. Show "Editing seed N", a `was: …` line, an `UNSAVED` badge (`.badge.-stale`) once the text differs, and two buttons **Save  Enter** and **Discard  Esc**. Save is disabled while the text is empty or unchanged. Other rows are dimmed and not selectable; Approve is hidden. Nothing is written until Save.
- **Add (`a`).** Appends an empty `Input` row; buttons **Add  Enter** and **Discard  Esc**; Discard removes the row. Nothing is written until Add.
- Remove the shared `#seed-input` and the `self.editing` index juggling; the editor state lives in the edited row.
- **Buttons for every key action**, one centred wrapping row: **Add seed  a**, **Edit  e**, **Delete  d** (Edit and Delete disabled with no seeds) and **Approve seeds  F2** (disabled with no seeds; hidden while editing). The status line `"Add at least one seed first."` and `#status` are removed; keep the guard in `action_approve` (silent return).
- **Confirm text:** "Approve N seeds and start searching?" (was "…and continue to search?").
- **Empty states.** Chat: `empty="Describe what concepts you want to search for and the assistant will help you generate seed phrases"`. Seeds panel: the existing "No seeds yet…" text, centred.
- **`propose_seeds` while editing.** The tool only appends, so an edited row keeps its index. If the user is mid-edit when the agent appends, append silently and do not touch the draft.
- **Agent knows the seeds (BACKEND §5).**
  - Register `@self.agent.instructions` returning the current seed list (read from the screen's `self.seeds`, not the file), so the agent never reasons from a stale view. Keep `INSTRUCTIONS` as the static text.
  - On every Save, Add and Delete call `chat.record(summary, body)` (task 03; no model call): "Seed N edited" with was/now; "Seed added" with text and number; "Seed N deleted" with the text. Body follows the task 03 shape with `# Current seeds` holding the full numbered list. Discard records nothing; the agent's own `propose_seeds` is already in history and is not repeated.
  - `BriefScreen` handles `ChatPanel.Submitted` (task 03) to write `brief.md` from the first message, verbatim, as it does today.
- Writes remain `write_seeds(self.seeds)`; the seeds-approved flag is untouched here (changing seeds after approval is handled by Search's staleness, task 07).

## Tests
- Pilot: `e` turns the row into an input with "Editing seed N" and the `was:` line; typing shows UNSAVED; Save disabled while unchanged/empty; Enter saves and writes `seeds.csv`; Esc discards and writes nothing. `a` appends an input row; Discard removes it; Add writes.
- Delete: removes the row, writes the file, records a "Seed N deleted" edit line (history gains one `edit` request, **zero model calls**).
- Approve disabled with no seeds and hidden while editing; `action_approve` with no seeds is a silent no-op; confirm text exact.
- Mid-edit append: `propose_seeds` called while editing keeps the draft text and index.
- The dynamic instruction contains the current seeds (inspect the `FunctionModel` request).
- Breakers in `tests/test_brief.py`: `#seed-input`, `Add at least one seed first`, `#status`, `seeds.csv ·` title, `#log`/`#live`.

## Done when
- `brief/*` states match at the three sizes; `seeds.csv` format unchanged.
