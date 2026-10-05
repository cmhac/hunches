# 17 — Taxonomy versions: change labels after gold exists without losing data

Spec: D12 and the "Taxonomy versions" section (read it first; it is the design). Not in the handoff: this is Chris's request (2026-10-05) and has no mock, so reuse existing modal and panel styling (task 01). `[behaviour]` + `[backend]`. Files: `files.py`, `screens/taxonomy.py`, `screens/gold.py` (pool/relabel wording only).

## Goal
A user can change the label set or mode after gold labelling has started. Nothing is deleted: the old version is archived whole, gold is relabelled on the same items, and any earlier version can be restored.

## Do

### A. `files.py` (plain functions, no classes)
- `taxonomy_in_use() -> bool`: any row in `gold.jsonl` has labels.
- `labels_changed(old: Taxonomy, new: Taxonomy) -> bool`: true when `old.mode != new.mode` or the **set** of label names differs. Order and descriptions are ignored.
- `list_versions() -> list[dict]`: the `meta.json` of each `.hunches/versions/<n>/`, ascending.
- `archive_version(note: str = "") -> int`: copy the live files named in the spec (those that exist) into the next `versions/<n>/`, write `meta.json` (`version`, `created_at` UTC ISO, `mode`, `labels` names, `dev_labelled`, `test_labelled`, `note`), return `n`. Never overwrites an existing directory; copies, does not move.
- `start_new_version(new: Taxonomy) -> int`: `archive_version()`; write the new taxonomy; rewrite `gold.jsonl` with the same ids, texts and splits and `labels=[]`; set `taxonomy_approved`, `dev_done`, `test_done`, `threshold_chosen` false; **move** `test_result.json`, `threshold.json`, `threshold_sample.json`, `results.jsonl` into the archive (they exist there from the copy; remove the live ones). `prompt.md` stays. Returns the archived version number. Order the steps so a crash after the archive never loses data (archive first, then mutate).
- `restore_version(n: int) -> None`: `archive_version(f"before restoring version {n}")`, then copy `versions/<n>/*` back over the live files and delete the live versionable files that version did not have (`test_result.json`, `threshold.json`, `threshold_sample.json`, `results.jsonl` when absent from it). Never touches `versions/`.
- `first_incomplete_stage` needs no change (cleared flags and unlabelled gold already send the user to stage 3, then 4).

### B. `screens/taxonomy.py`
- In `commit_taxonomy(new)` (the seam from task 08): if `taxonomy_in_use()` and `labels_changed(current, new)`, first show a `ConfirmScreen` with the spec's text (fill in the version number `N` that will be created: `len(list_versions()) + 1`); on confirm call `start_new_version(new)`, record an edit line for the agent ("Taxonomy version N+1 started: label set/mode changed; gold labels cleared on the same items; version N archived"), refresh the panels, and show a one-line `.note` "Version N archived. Approve to relabel the dev set." On cancel nothing changes and the draft stays open. Otherwise write normally.
- **Agent `write_taxonomy`** goes through the same function. When confirmation is needed the tool awaits the modal (`await self.app.push_screen_wait(...)`, D6, inside the chat worker) and returns "Written as version N+1; gold labels were cleared and will need relabelling." or "Not written: the user declined starting a new taxonomy version." If the panel is in edit mode the existing "Not written: the user is editing…" rule wins.
- **Versions UI.** Labels panel subtitle shows `version N` (current = archived count + 1). A **Versions** button (disabled when none are archived) opens a modal listing archived versions — number, date, mode, label names, `dev_labelled`/`test_labelled` — with **Restore** (confirmed) and **Close  Esc**. Restore calls `restore_version`, reloads the screen state, records an edit line for the agent ("Restored taxonomy version N; the previous state is archived as version M"), and the user continues from stage 3 (`first_incomplete_stage`). Restore is disabled while a panel is in edit mode.
- The F2 approve flow is unchanged: after a new version the user approves again and `GoldScreen` draws nothing new (the rows already exist, unlabelled).

### C. `screens/gold.py`
- On mount it already tops up to `SAMPLE_SIZE` and resumes at the first unlabelled row; with cleared labels this just works. Add one line to the subtitle or note when a version was started ("Relabelling for taxonomy version N"): derive from `list_versions()` non-empty and zero labelled rows; optional, skip if it complicates the screen.

## Tests (hand-built `tmp_path` projects; never a real model)
- `labels_changed`: rename, add, delete, mode change → true; description-only and reorder → false (hand-written cases).
- `start_new_version` on a fixture with 50 dev + 50 test labelled rows, a test result, a threshold and results: afterwards live gold has the same 100 ids/texts/splits with empty labels, the four derived files are gone from `.hunches/`, state flags are false, `first_incomplete_stage() == 3`, and `versions/1/` holds byte-identical copies of everything plus a correct `meta.json` (`dev_labelled == 50`).
- `restore_version(1)` then: live files equal the archived bytes; the pre-restore state exists as `versions/2/`; `versions/1/` unchanged; restoring twice never deletes anything (count the directories).
- UI (Pilot): editing a description with gold in use saves with no confirm; renaming a label shows the exact confirm; Cancel leaves files untouched and the draft open; Confirm archives and clears; the Versions modal lists the version and Restore works; an edit line is recorded in each case with **zero model calls**; agent `write_taxonomy` while in use awaits the confirm and returns the right strings for yes and no.
- With no labelled gold rows, a label change saves normally (no archive).

## Done when
- A user can change labels at any stage, relabel, and get any earlier version back byte-for-byte; no code path deletes anything under `.hunches/versions/`.
