# 004 — Edit history, undo/redo, and redoing downstream work

Status: draft for review by the frontend design agent, then for implementation. Builds on `../001-initial-version/spec.md`, `../002-onboarding-setup/spec.md` and `../003-tui-redesign/spec.md`, all implemented. Written 2026-10-08 against `main` at `b2d63ce` (merge of PR 5).

**Read order for an implementer:** this spec → your task file (not written yet; see "Tasks") → the code named in each section.

**Read order for the design agent:** "What this is" → "Resolved decisions" → "What the user can see and do" (the list of UI surfaces this spec needs) → "Open questions for the design agent". The backend sections are there so you know what data each surface can show.

## What this is, in one paragraph

`hunches` runs inside a git repo and the key files in `.hunches/` are meant to be committed, but users cannot be relied on to commit often. This spec gives the tool its own record of changes to the three files that define a project's analysis — the **seed phrases** (`seeds.csv`), the **taxonomy** (`taxonomy.yaml`) and the **prompt** (`prompt.md`) — so the user can undo and redo those changes without git. It also makes the pipeline notice, from content rather than from forward-only flags, when an earlier decision has changed and later work (candidates, tuning, the test result, the threshold, the full run) was made under the old one. The user can then go back, change something, see exactly what is out of date and what redoing it would cost, and redo it. The existing call cache is kept: because it is keyed by content, going back to an earlier prompt or redoing a run with unchanged inputs is free.

The tool still never runs git. Everything new is plain files in `.hunches/`.

## Principles

Same as 001–003 (minimal implementation; no abstraction, base class, registry or plugin system unless asked; plain files in `.hunches/` are the only state; check every Textual and Pydantic AI API against the installed version and current docs; never call a real LLM or AWS in tests; unknown cost is `?`, never `$0`). Additional rules for this spec:

- **Nothing is deleted by going back.** Undo, redo, restore and "this is stale" never remove a file or a gold label. Derived files stay in place, marked stale, until redoing the stage overwrites them (D3).
- **Approvals are human.** Redoing a stage recomputes its numbers; it never approves anything. The user re-approves (F2) after reviewing.
- **Staleness comes from content hashes, not timestamps.** A stage is stale when the digest of its inputs differs from the digest recorded when it was last computed or approved.
- **A project with no history works unchanged.** Old projects have no history log, no recorded digests and no `run` field on results. Missing means "current" (the same rule `candidates.seeds_changed` already uses for a missing meta file). The first run of the new code records a baseline; it never flags old work as stale.

## Resolved decisions

| # | Question | Decision | Who / when |
|---|----------|----------|------------|
| D1 | Which files get undo/redo history? | `seeds.csv`, `taxonomy.yaml`, `prompt.md`. **Gold labels are not in the history.** Taxonomy versions (003 task 17) keep protecting gold when the label set changes. | Chris, 2026-10-08 |
| D2 | When seeds change and some gold items are no longer in the candidate pool | **Keep the labelled items.** Warn the user, and give the assistant the same information. Provide an easy way for both the user and the assistant to remove the stale rows and draw new ones to label. Labels that are still relevant stay. | Chris, 2026-10-08 |
| D3 | Derived files (`test_result.json`, `threshold.json`, `threshold_sample.json`, `results.jsonl`) when their inputs change | **They stay in place until overwritten**, marked stale. They are reproducible from the cache anyway. | Chris, 2026-10-08 |
| D4 | Approvals in the history | **Yes.** Every approval is an event in the log, so the timeline reads as the story of the project. | Chris, 2026-10-08 |
| D5 | One undo stack or one per file | **One stack per file** (seeds, taxonomy, prompt), plus one combined timeline for viewing. Undo in the Prompt panel never reverts a seed edit. | Chris, 2026-10-08 ("artifact" here means these three files) |
| D6 | How redoing downstream work happens | There is no "redo everything" button that auto-approves. The app shows what is stale and what redoing would cost (cached calls are free, new calls are priced or `?`), and takes the user to the earliest stale stage; that stage recomputes (mostly from the cache) and the user re-approves. | Claude, to confirm |
| D7 | Who can change gold | The user labels gold. The assistant may list, remove (after the user confirms) and draw gold items, but never sets a gold label. | Claude, to confirm (O3) |

## Where things stand today (verified in code, 2026-10-08)

- Seeds, taxonomy and prompt are overwritten in place (`brief.write_seeds`, `taxonomy.commit_taxonomy`, `taxonomy.save_prompt`, `tune.accepted`, and the assistant tools `propose_seeds`, `write_taxonomy`, `write_prompt`, `propose_prompt`). No history.
- The only versioning is `files.archive_version / start_new_version / restore_version` (spec 003, D12). It snapshots the whole working set and only runs when the label set or mode changes while gold labels exist.
- Staleness is checked in two places: Search compares a digest of the seeds with `candidates.meta.json` (`candidates.seeds_changed`), and Stage 6 compares a hash of the prompt and classifier model with `test_result.json` (`final.prompt_hash`). Everything else relies on the booleans in `state.json`, which only move forward.
- **Existing gap this spec fixes:** `files.first_incomplete_stage` (`files.py:364`) and `run.pending` (`run.py:26`) treat a result as done if its item id appears in `results.jsonl`, without checking which prompt produced it. `tune.accepted` does not clear `dev_done`. So after a full run, going back to Tuning and changing the prompt leaves stages 7–9 looking complete.
- The classifier cache key is `sha256([model, system_prompt(prompt, taxonomy), text])` (`classifier.classify`); seed embeddings are keyed `(embedding_model, "embed_query", seed)` (`candidates.embed_seeds`). Both are content-addressed, so they stay correct across undo, redo and restore. Each entry stores the call's token usage. A classifier entry whose output is not a dict (the pre-reasoning list shape) counts as a miss.
- The Gold screen has no assistant. The assistants with tools today are Brief (`propose_seeds`), Taxonomy (`write_taxonomy`, `write_prompt`) and Tuning (`get_disagreements`, `propose_prompt`).

## Data

### New: `.hunches/history/`

| Path | Contents |
|------|----------|
| `history/objects/<sha256>` | A verbatim copy of one saved version of seeds, taxonomy or prompt, named by the SHA-256 of its UTF-8 bytes. Written once, never changed or deleted. Identical content is stored once. |
| `history/log.jsonl` | Append-only, one JSON object per line, in `seq` order. |

Log entry kinds (all have `seq`, `ts` (UTC ISO 8601), `kind`):

| `kind` | Extra fields | Written when |
|--------|--------------|--------------|
| `edit` | `artifact` (`"seeds"`, `"taxonomy"` or `"prompt"`), `before`, `after` (object hashes; `null` when the file did not exist), `source` (`user`, `assistant`, `external`, `baseline`, `undo`, `redo`, `restore`), `summary`, optional `group` | Any change to one of the three files |
| `approval` | `stage` (1–9), `flag` (a `State` field), `inputs` (the digest recorded for it; see "Input digests") | A `State` flag is set to true |
| `version` | `snapshot` (the archived version number) | `files.start_new_version` runs (taxonomy version started) |

`summary` is the same one-line string the screen passes to `ChatPanel.record` (the "YOU EDITED" line), so the timeline and the chat agree.

### Changed: existing files

| File | Change |
|------|--------|
| `state.json` | New field `inputs: dict[str, str]`: for each approved flag, the digest of its inputs at approval time. Absent = treated as current. |
| `candidates.meta.json` | Adds `embedding_model` next to `seeds_digest` and `floor`. Absent = unchanged. |
| `test_result.json` | `prompt_hash` is replaced by `run_digest` (see below). A file with only `prompt_hash` is still compared the old way. |
| `threshold.json`, `threshold_sample.json` | Each records `run_digest` and `candidates_digest` when written. Absent = current. |
| `results.jsonl` | Each success row gains `run` (the `run_digest` it was classified under). A row without `run` counts as current. |
| `gold_removed.jsonl` (new, append-only) | Every gold row the user or assistant removes, with its labels and a `reason` and timestamp. Never read except to exclude those ids from redrawing and to show a count. See O2. |

### Input digests

One definition each, in `files.py`, so every stage compares the same things:

- `run_digest(prompt, taxonomy, model)` = `sha256(json.dumps([model, classifier.system_prompt(prompt, taxonomy)]))`. This is exactly what the classifier cache key hashes (minus the item text), so **equal digests mean the cache would hit**. It replaces `final.prompt_hash`. Whitespace-only edits to the ends of the prompt do not change it, which matches the classifier.
- `candidates_digest` = sha256 of the sorted candidate ids.
- `seeds_digest` already exists (`candidates.seeds_digest`).

| Stage | Recorded when | Stale when the current value differs |
|-------|---------------|--------------------------------------|
| 1 Seeds | Never stale (it is the root). | — |
| 2 Search | `candidates.meta.json` is written | `seeds_digest` or `embedding_model` |
| 3 Taxonomy and prompt | Never stale from prompt edits (the prompt is tuned later). A label-set change already goes through taxonomy versions. | — |
| 4 Gold dev | Not stale. It can have **orphaned rows** (see "Gold after seeds change"). | — |
| 5 Tuning | `dev_done` approved: `state.inputs["dev_done"] = run_digest` | `run_digest` |
| 6 Gold test | `test_result.json` and `test_done` approved | `run_digest` |
| 7 Threshold | `threshold.json` and `threshold_sample.json` written, `threshold_chosen` approved | `run_digest` or `candidates_digest` |
| 8 Full run | each `results.jsonl` row | row's `run` ≠ current `run_digest` (that row is not done) |
| 9 Browse | — | shows a notice if any row's `run` is not current |

A stage is **stale** only if it was complete and its recorded digest differs. It is **incomplete** if its completion rule from `first_incomplete_stage` is not met. Otherwise **current**.

## Backend

### `history.py` (new)

```python
save(artifact, text, source, summary="", group=None) -> bool   # False if unchanged
sync() -> list[dict]                                            # log external changes
entries(artifact=None) -> list[dict]
can_undo(artifact) -> bool;  can_redo(artifact) -> bool
undo(artifact) -> dict | None;  redo(artifact) -> dict | None
restore(artifact, seq) -> dict                                  # make the file as it was after entry `seq`
approval(stage, flag, inputs) -> None
```

- **`save`** is the only way the three files are written by the app. Order: write the object (if absent), write the file (temp file + `os.replace`), append the log line. If the process dies between the second and third step, the next `sync()` sees a file that does not match the log and records it as `external`, so nothing is lost. A save of identical content is a no-op and writes no entry.
- **`sync`** hashes the three files and compares each to the `after` of its last entry. A difference (the user edited in an editor, ran `git checkout`, `git pull` or `git stash`) is logged as `source="external"`. A project with no log gets one `baseline` entry per existing file. `sync` runs at project open, on entering every stage screen, and at the start of `undo`, `redo` and `restore`. It reads three small files.
- **Stacks are derived from the log; there is no extra state.** Replay one artifact's entries: `edit` entries with source `user`, `assistant`, `external`, `restore` or `baseline` push onto the undo stack and clear the redo stack; an `undo` entry moves the top of the undo stack to the redo stack; `redo` moves it back. Entries sharing a `group` pop together (one assistant proposal that adds ten seeds is one undo).
- **Undo and redo append entries; they never rewrite the log.** An undo writes the target's `before` through the same write path with `source="undo"`.
- **Restore** (from the timeline) makes the file match its state after a chosen entry and appends a `restore` entry. It is a normal edit: undoable.
- **Taxonomy and gold.** A taxonomy change that alters the label set or mode while gold labels exist is not a plain text edit (003 D12). So:
  - Undoing a `version` entry calls `files.restore_version(n)`, which archives the current state as a new version `m` first. The undo entry records `snapshot=m`; **redo** of it is `restore_version(m)`. Gold comes back with the labels, and nothing is lost.
  - Any other undo, redo or restore that would change the label set or mode while `files.taxonomy_in_use()` raises `NeedsVersion`; the screen asks the user (the existing version confirmation) and then calls `files.start_new_version`. This covers the rare case of an `external` edit (such as a `git checkout`) that changed the labels.
- **Callers after an undo or redo:** reload their widgets from the files, and call `ChatPanel.record(summary, body)` so the assistant is told (no model call), exactly as `taxonomy.restore` does today. For `prompt`, the Tuning screen supersedes pending proposals and re-runs, as `tune.accepted` does today (a re-run of a previously seen prompt is all cache hits).

### Where `save` replaces existing writes

| Today | After |
|-------|-------|
| `brief.write_seeds` | `history.save("seeds", …, source="user")`; `propose_seeds` uses `source="assistant"` and a shared `group` |
| `taxonomy.commit_taxonomy` / `files.write_taxonomy` (no version case) | `history.save("taxonomy", …)` |
| `files.start_new_version` | writes a `version` entry, and its `write_taxonomy` goes through `save` |
| `taxonomy.save_prompt`, `write_prompt` tool, `tune.accepted` | `history.save("prompt", …)` |

### Approvals

`confirm_approve` (`app.py`), `tune.action_done`, `final.accept` and `threshold` each set a `State` flag by hand. Replace with one `files.approve(flag, stage)` that sets the flag, stores `state.inputs[flag]` (the stage's current digest from the table above) and calls `history.approval`. Un-approving never happens automatically (D3).

### `files.stage_status()` and resume

```python
stage_status() -> dict[int, tuple[Literal["current", "incomplete", "stale"], str]]   # str: the reason, "" if current
first_incomplete_stage() -> int      # now the lowest stage whose status is not "current"
```

- `first_incomplete_stage` keeps its 1–9 return value and its current completion rules; it additionally returns the lowest **stale** stage. `run.pending` counts only rows whose `run` is current. This fixes the gap described above.
- `final.prompt_hash` is replaced by `files.run_digest`.

### Redo plan

```python
redo_plan(from_stage=1) -> list[dict]
# {stage, status, reason, live_calls, cached_calls, dollars: float | None, price_unknown: bool}
```

For each stale or incomplete stage that does model work, count how many calls would be live and how many would be cache hits **without calling anything**, by building the same cache keys the stage would use:

- Stage 2: one embedding per seed (`cost.cache_key(embedding_model, "embed_query", seed)`).
- Stage 5: the labelled dev rows. Stage 6: the labelled test rows. Stage 7: the ids in `threshold_sample.json`. Stage 8: the candidates at or above the threshold with no current-digest row.
- A classifier hit is an entry whose `output` is a dict (`classifier.classify` treats the old list shape as a miss). Add one helper, `classifier.is_cached(text, prompt, taxonomy, model)`, so the rule lives in one place.
- Dollars for the live calls use the existing estimate in `screens/run.py::estimate` (average tokens per call from `cost.breakdown()`; move it to `cost.py` if both modules need it). Unknown price → `dollars=None`, `price_unknown=True`, shown as `?` with the usual warning. Never `$0`.

### Gold after seeds change (D2)

```python
files.orphaned_gold(split=None) -> list[GoldRow]    # gold rows whose id is not in candidates.jsonl
files.gold_coverage() -> dict                       # {"dev": {"labelled", "orphaned", "orphaned_by_label": {...}}, "test": {...}}
gold.remove(ids, reason) -> int                     # moves rows to gold_removed.jsonl, returns how many
gold.draw(split, n)                                 # existing; now also excludes ids in gold_removed.jsonl
```

- "Orphaned" means the item is no longer in the candidate pool after Search was re-run. Its labels are still valid; only its representativeness changed. The default is to keep it (D2).
- Removing rows lowers the labelled count, so `first_incomplete_stage` returns 4 (dev) or 6 (test) until the split is back to `SAMPLE_SIZE` labelled rows. `draw` tops it up; the new rows start unlabelled.
- Removing or replacing **test** rows after the test result was viewed weakens the held-out guarantee. The confirmation says so.
- `draw`'s RNG seed uses the number of gold rows, so a draw after a removal is deterministic but different from the original; that is fine.

### What the assistant is told and can do

All three assistants (Brief, Taxonomy, Tuning) already get per-run `instructions` that are recomputed every run. Add two sections to each:

```
# Pipeline status
1 Brief and seeds: current
2 Search: STALE — seeds changed since the candidates were built (12 added, 3 removed)
5 Tuning: STALE — the prompt changed since tuning was accepted
…
# Gold coverage
dev: 50 labelled, 6 orphaned (no longer in the candidate pool: ids …, with the first 80 characters of text and the labels)
test: 50 labelled, 0 orphaned
```

The orphan list is capped (suggest 10 rows) with a total count. Undo, redo and restore are recorded in each assistant's history as edit lines with no model call, the same mechanism as every other user edit.

New tools, on the **Tuning** assistant (it already works with the dev gold through `get_disagreements`; see O3 for the Gold screen):

- `list_orphaned_gold(split="dev")` → rows with id, text, labels.
- `remove_gold(ids, reason)` → asks the user to confirm (the `ConfirmScreen` flow used by `write_taxonomy`), then calls `gold.remove`.
- `draw_gold(split, n)` → calls `gold.draw`; the new rows are unlabelled and the **user** labels them.

The assistant has no tool that sets a gold label (D7).

### Cache

Unchanged, apart from the `classifier.is_cached` helper above. Notes for the README: a description-only edit to a label changes the system prompt and therefore re-classifies everything, which is correct; `history/` is small text and should be committed; `cache/` may be git-ignored if it grows.

## What the user can see and do (UI surfaces for the design agent)

The backend above exposes data; these are the places it must show up. Keys must follow the existing rules (every key has a button, every button shows its key, no colour alone, works at 80×24, 100×30, 120×36).

1. **Undo / Redo** for each of the three editors: the seed list (Brief), the Labels panel and the Prompt panel (Taxonomy), and the prompt (Tuning's Edit prompt). Buttons with keys, disabled when `can_undo` / `can_redo` is false, and a one-line note after use naming what changed ("Undid: Prompt: edited by the user"). `ctrl+z` is taken inside `TextArea` and `Input`; the design agent chooses keys that do not clash.
2. **History** (a modal, like `VersionsScreen`): the combined timeline, newest first. Each row: time, file, a source badge (YOU, ASSISTANT, EXTERNAL, UNDO, REDO, RESTORE, BASELINE), the one-line summary, and approval and taxonomy-version events as their own row types. Filter by file. Selecting a row previews the text or a diff; **Restore this** makes that file match. It is not available while an editor is open (same rule as Versions).
3. **External change notice:** when `sync()` finds an outside edit, say so once, with an Undo ("prompt.md changed outside hunches").
4. **Stale markers:** in the stage list/stepper (rail), a STALE or INCOMPLETE word or glyph per stage, with the reason visible (rail tooltip, or a line on the stage screen). Never colour alone. Stage screens 5–9 get a banner when stale, in the style of the existing Stage 6 STALE banner. Browse shows a notice when results come from an older prompt.
5. **Redo plan:** a view (modal or panel) listing the stale stages in order with live versus cached call counts and dollars or `?`, and a button that jumps to the earliest stale stage. After the user re-approves that stage there is a way to continue to the next stale one. It never auto-approves (D6).
6. **Approvals** appear in the History modal and are what the user re-does after a stale stage.
7. **Gold after a seeds change:**
   - Search, after a re-run, says how many gold items are no longer in the pool ("6 of your 50 dev items are no longer in the candidate pool").
   - The Gold screen marks orphaned rows (a word or glyph), shows the orphan count, and offers **Remove stale rows** and **Draw replacements** (and per-row remove for any row). Removal is confirmed and says how many labels are discarded; for test rows it adds the held-out warning. Progress and finish gating already follow from the labelled count.
8. **Assistant:** the new context sections arrive as the existing context line; the new tools render as tool lines; `remove_gold` shows the confirmation modal.

## Behaviour that changes in 001–003

- `first_incomplete_stage` also returns the lowest stale stage (001 rules otherwise unchanged).
- `run.pending` and the Stage 8 "done" rule require a current `run` on each row.
- `final.prompt_hash` is replaced by `run_digest`; a legacy `prompt_hash` file is still compared the old way.
- Setting a `State` flag goes through `files.approve`, which records the digest and an `approval` log entry.
- `candidates.meta.json` records `embedding_model`.
- `gold.draw` skips ids in `gold_removed.jsonl`.
- 003 D12 (taxonomy versions) is unchanged. Its archives still copy `gold.jsonl`, results and the other derived files.
- The gap noted above (prompt change after a full run leaving stage 8/9 looking complete) is closed.

## Tasks

Task files are written after the design agent's pass. The planned order:

| # | Task | Depends on |
|---|------|-----------|
| 01 | `history.py`: objects, log, `save`, `sync`, undo/redo/restore, tests | — |
| 02 | Route the three files' writers through `history.save`; edit recording; taxonomy-version link and `NeedsVersion` | 01 |
| 03 | `files.approve`, `State.inputs`, `approval` and `version` entries | 01 |
| 04 | `run_digest`, per-stage digests, `stage_status`, new `first_incomplete_stage`, `run.pending`, `final` switch | 03 |
| 05 | `classifier.is_cached`, `redo_plan` | 04 |
| 06 | Gold: `orphaned_gold`, `gold_coverage`, `gold.remove`, `draw` exclusion, `gold_removed.jsonl` | 04 |
| 07 | Assistant context sections and the three gold tools | 04, 06 |
| 08 | UI: undo/redo buttons and the History modal | 02, design |
| 09 | UI: stale markers, banners, redo plan | 04, 05, design |
| 10 | UI: gold orphan handling | 06, design |
| 11 | README, `AGENTS.md`/`CLAUDE.md` current-state update, end-to-end test, size sweep for new modals | all |

## Tests

All offline; no real model, AWS or keyring. Expected values are written by hand in the test, never computed by the code under test.

- **History:** a sequence of saves, undos and redos yields the hand-written file contents at each step; a new edit after an undo clears redo; `group` entries undo together; a no-op save writes no entry; a file changed behind the app's back is logged as `external`; a crash between file write and log append (simulated) is recovered by `sync`; a project with no log gets baseline entries; the log is append-only (earlier lines unchanged).
- **Taxonomy:** undoing a `version` entry restores gold labels; redo restores the new version; a label-changing undo with gold labelled raises `NeedsVersion`.
- **Digests and status:** changing the prompt marks stages 5–8 stale and leaves 1–4 current; changing seeds marks 2 and 7 stale; restoring the old prompt makes them current again; a project with no recorded digests is all current; `first_incomplete_stage` returns the lowest stale stage.
- **Redo plan:** with `FunctionModel` call counting, the plan's cached and live counts equal what a real run then does, and a second run makes zero calls; an unpriced model gives `?`, never `0`.
- **Gold:** orphans are exactly the rows missing from the pool; `remove` writes `gold_removed.jsonl` and `draw` never returns those ids; removing below 50 labelled sends resume back to stage 4 or 6.
- **Assistant:** the status and gold-coverage sections appear in the instructions; `remove_gold` does nothing until confirmed; no tool sets a label.
- **UI:** one Pilot smoke test per new screen/modal, and each new modal added to `tests/test_sizes.py`.

## Open questions

For Chris:

- **O1 — Undo scope.** Resolved: per-file stacks (D5).
- **O2 — `gold_removed.jsonl`.** A small append-only file that keeps removed gold rows so human labelling is never silently lost and removed items are not redrawn. D1 says gold is not in the history; this is a safety net for deletions only. Keep it, or drop it and delete outright.
- **O3 — Where the assistant's gold tools live.** The Gold screen has no assistant. This spec puts the tools on the Tuning assistant. Alternatives: also add them to the Taxonomy assistant, or add a chat to the Gold screen.

For the design agent:

- **O4 — Keys** for undo/redo and History that do not clash with `TextArea`/`Input` bindings.
- **O5 — How the redo plan is presented** and how "continue to the next stale stage" works after each re-approval.
- **O6 — How much of the timeline the rail can show** at 100 columns; whether stale reasons fit there or only on the stage screen.
- **O7 — Wording** for the held-out warning when test rows are replaced.

## Needs a human

Nothing in this spec needs credentials or a real corpus. After implementation, a manual terminal pass: edit seeds, a label description and the prompt; undo and redo each; run `git checkout` on `prompt.md` and confirm the external-change notice; change the prompt after a full run and confirm stages 5–9 show stale and the redo plan counts match the real run.
