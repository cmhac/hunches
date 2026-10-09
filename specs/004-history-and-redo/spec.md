# 004 — Edit history, undo/redo, and redoing downstream work

Status: draft; revised 2026-10-08 after the design agent's response (`design/design_handoff_hunches_tui/PLAN_004_INTEGRATION.md`). Builds on `../001-initial-version/spec.md`, `../002-onboarding-setup/spec.md` and `../003-tui-redesign/spec.md`, all implemented. Written against `main` at `b2d63ce` (merge of PR 5).

**Read order for an implementer:** this spec → your task file (not written yet; see "Tasks") → the design handoff passages the task names (`design/design_handoff_hunches_tui/PLAN_004_INTEGRATION.md`, `BACKEND_CHANGES.md` §13–16, and the mock state ids in `reference/ui_kits/tui-rail/*.jsx`, group "History and redo plan") → the code named in each section. Where the design handoff and this spec disagree, this spec wins; the places where they differ are listed under "Design handoff: what this spec changes".

## What this is, in one paragraph

`hunches` runs inside a git repo and the key files in `.hunches/` are meant to be committed, but users cannot be relied on to commit often. This spec gives the tool its own record of changes to the three files that define a project's analysis — the **seed phrases** (`seeds.csv`), the **taxonomy** (`taxonomy.yaml`) and the **prompt** (`prompt.md`) — so the user can undo and redo those changes without git. It also makes the pipeline notice, from content rather than from forward-only flags, when an earlier decision has changed and later work (candidates, tuning, the test result, the threshold, the full run) was made under the old one. The user can then go back, change something, see exactly what is out of date and what redoing it would cost, and redo it. The existing call cache is kept: because it is keyed by content, going back to an earlier prompt or redoing a run with unchanged inputs is free.

The tool still never runs git. Everything new is plain files in `.hunches/`.

## Principles

Same as 001–003 (minimal implementation; no abstraction, base class, registry or plugin system unless asked; plain files in `.hunches/` are the only state; check every Textual and Pydantic AI API against the installed version and current docs; never call a real LLM or AWS in tests; unknown cost is `?`, never `$0`). Additional rules for this spec:

- **Nothing is deleted by going back.** Undo, redo, restore and "this is stale" never remove a file or a gold label. Derived files stay in place, marked stale, until redoing the stage overwrites them (D3).
- **Approvals are human.** Redoing a stage recomputes its numbers; it never approves anything. The user re-approves (F2) after reviewing.
- **Staleness comes from content hashes, not timestamps.** A stage is stale when the recorded inputs it was computed or approved under differ from the current ones.
- **A project with no history works unchanged.** Old projects have no history log, no recorded inputs and no `run` field on results. Missing means "current" (the same rule `candidates.seeds_changed` already uses for a missing meta file). The first run of the new code records a baseline; it never flags old work as stale.

## Resolved decisions

| # | Question | Decision | Who / when |
|---|----------|----------|------------|
| D1 | Which files get undo/redo history? | `seeds.csv`, `taxonomy.yaml`, `prompt.md`. **Gold labels are not in the history.** Taxonomy versions (003 task 17) keep protecting gold when the label set changes. | Chris, 2026-10-08 |
| D2 | When seeds change and some gold items are no longer in the candidate pool | **Keep the labelled items.** Warn the user, and give the assistant the same information. Provide an easy way for both the user and the assistant to remove the stale rows and draw new ones to label. Labels that are still relevant stay. | Chris, 2026-10-08 |
| D3 | Derived files (`test_result.json`, `threshold.json`, `threshold_sample.json`, `results.jsonl`) when their inputs change | **They stay in place until overwritten**, marked stale. They are reproducible from the cache anyway. | Chris, 2026-10-08 |
| D4 | Approvals in the history | **Yes.** Every approval is an event in the log, so the timeline reads as the story of the project. | Chris, 2026-10-08 |
| D5 | One undo stack or one per file | **One stack per file** (seeds, taxonomy, prompt), plus one combined timeline for viewing. Undo in the Prompt panel never reverts a seed edit. | Chris, 2026-10-08 ("artifact" here means these three files) |
| D6 | How redoing downstream work happens | No "redo everything" button that auto-approves. A Redo plan modal shows what is stale and what redoing costs (cached calls are free, new calls are priced or `?`) and takes the user to the earliest stale stage; that stage recomputes (mostly from the cache) and the user re-approves. | Claude; designed by the design agent |
| D7 | Who can change gold | The user labels gold. The assistant may inspect, remove (after the user confirms) and draw gold items, but never sets a gold label. | Claude; accepted by the design agent |
| D8 | Naming and numbering of prompt versions | **None.** The history does not number or name prompt versions and the user never names them. A history entry is identified by its time, its file, its source and its one-line summary. The "prompt version N" counter that already exists on the Tuning screen (`len(self.history)`, an automatic count of the prompts tried in that screen) is unchanged and is not part of this feature. | Chris, 2026-10-08 |
| D9 | Does the assistant speak up when the pipeline status or gold coverage changes? | **Yes.** On the Tuning screen an UPDATED context line is added and the assistant replies briefly, as the Taxonomy context update does in 003. This is a model call; revisit if cost becomes a problem. | Chris, 2026-10-08 |
| D10 | Warning when the embedding model changes | **Yes**, a visible warning on Search, a STALE mark on stage 2 and the information in the assistant's status. See "Embedding model change". | Chris, 2026-10-08 |

## Where things stand today (verified in code, 2026-10-08)

- Seeds, taxonomy and prompt are overwritten in place (`brief.write_seeds`, `taxonomy.commit_taxonomy`, `taxonomy.save_prompt`, `tune.accepted`, and the assistant tools `propose_seeds`, `write_taxonomy`, `write_prompt`, `propose_prompt`). No history.
- The only versioning is `files.archive_version / start_new_version / restore_version` (spec 003, D12). It snapshots the whole working set and only runs when the label set or mode changes while gold labels exist.
- Staleness is checked in two places: Search compares a digest of the seeds with `candidates.meta.json` (`candidates.seeds_changed`), and Stage 6 and the Stage 8 "untested prompt" block compare a hash of the prompt and classifier model with `test_result.json` (`final.prompt_hash`, imported by `run.py`). Everything else relies on the booleans in `state.json`, which only move forward.
- **Existing gap this spec fixes:** `files.first_incomplete_stage` (`files.py:364`) and `run.pending` (`run.py:26`) treat a result as done if its item id appears in `results.jsonl`, without checking which prompt produced it. `tune.accepted` does not clear `dev_done`. So after a full run, going back to Tuning and changing the prompt leaves stages 7–9 looking complete.
- The classifier cache key is `sha256([model, system_prompt(prompt, taxonomy), text])` (`classifier.classify`); seed embeddings are keyed `(embedding_model, "embed_query", seed)` (`candidates.embed_seeds`). Both are content-addressed, so they stay correct across undo, redo and restore. Each entry stores the call's token usage. A classifier entry whose output is not a dict (the pre-reasoning list shape) counts as a miss.
- `search.py` already refuses to search a local corpus whose `meta.json` embedding model differs from `config.toml` (the "Fix: set embedding_model…" error on the Search screen). Nothing records which embedding model the existing candidates were built with.
- The Gold screen has no assistant. The assistants with tools today are Brief (`propose_seeds`), Taxonomy (`write_taxonomy`, `write_prompt`) and Tuning (`get_disagreements`, `propose_prompt`). `write_taxonomy` already asks the user inside the tool call with `await self.app.push_screen_wait(ConfirmScreen(...))` and returns the outcome to the model.

## Data

### New: `.hunches/history/`

| Path | Contents |
|------|----------|
| `history/objects/<sha256>` | A verbatim copy of one saved version of seeds, taxonomy or prompt, named by the SHA-256 of its UTF-8 bytes. Written once, never changed or deleted. Identical content is stored once. |
| `history/log.jsonl` | Append-only, one JSON object per line, in `seq` order. |

Log entry kinds (all have `seq`, `ts` (UTC ISO 8601), `kind`, `summary`):

| `kind` | Extra fields | Written when |
|--------|--------------|--------------|
| `edit` | `artifact` (`"seeds"`, `"taxonomy"` or `"prompt"`), `before`, `after` (object hashes; `null` when the file did not exist), `source` (`user`, `assistant`, `external`, `baseline`, `undo`, `redo`, `restore`), optional `group`, optional `snapshot` (see "Taxonomy and gold") | Any change to one of the three files |
| `approval` | `stage` (1–9), `flag` (a `State` field), `inputs` (the components recorded for it; see "Recorded inputs") | A `State` flag is set to true |
| `version` | `snapshot` (the archived version number) | `files.start_new_version` runs (taxonomy version started) |

`summary` is one line, composed by the caller: for an edit it is the same string the screen passes to `ChatPanel.record` (the "YOU EDITED" line), so the timeline and the chat agree; for an approval the approving screen knows the numbers ("Approved: Tuning loop (dev accuracy 0.920)"); for a version it is read from the archive's `meta.json` ("Taxonomy version 2 started (version 1 holds 50 dev labels)"). **Summaries never contain a prompt version number** (D8).

### Changed: existing files

| File | Change |
|------|--------|
| `state.json` | New field `inputs: dict[str, dict[str, str]]`: for each approved flag, the components of its inputs at approval time (see "Recorded inputs"). Absent = treated as current. |
| `candidates.meta.json` | Adds `embedding_model` next to `seeds_digest` and `floor`. Absent = unchanged. |
| `test_result.json` | `prompt_hash` is replaced by `inputs` (the components, see below). A file with only `prompt_hash` is still compared the old way. |
| `threshold.json`, `threshold_sample.json` | Each records `inputs` when written. Absent = current. |
| `results.jsonl` | Each success row gains `run` (the `run_digest` it was classified under). A row without `run` counts as current. |
| `gold_removed.jsonl` (new, append-only) | Every gold row the user or assistant removes, with its labels, a `reason` and a timestamp. Never read except to exclude those ids from redrawing and to show a count. The design agent assumed this file (the removal modal tells the user the rows are kept and never drawn again). |

### Recorded inputs

Staleness needs to say **what** changed, so inputs are recorded as named components rather than one hash. Components (all SHA-256 hex unless noted), defined once in `files.py`:

| Component | Value |
|-----------|-------|
| `seeds` | `candidates.seeds_digest(read_seeds())` (exists) |
| `embedding_model` | the model name, as in `config.toml` (a plain string) |
| `candidates` | hash of the sorted candidate ids |
| `prompt` | hash of `prompt.md` with leading/trailing whitespace stripped (the classifier strips it too) |
| `taxonomy` | hash of the mode and the labels with their descriptions, in order |
| `classifier_model` | the model name (a plain string) |
| `gold_dev`, `gold_test` | hash of the sorted `(id, labels)` of the **labelled** rows of that split |

`run_digest(prompt, taxonomy, model)` = `sha256(json.dumps([model, classifier.system_prompt(prompt, taxonomy)]))` is also kept. It is exactly what the classifier cache key hashes (minus the item text), so **equal `run_digest` means the cache would hit**. It is what `results.jsonl` rows record as `run`, and it replaces `final.prompt_hash`.

| Stage | Records, when | Stale when this differs |
|-------|---------------|-------------------------|
| 1 Seeds | — (the root) | never stale |
| 2 Search | `candidates.meta.json` is written: `seeds`, `embedding_model` | `seeds` or `embedding_model` |
| 3 Taxonomy and prompt | — | never stale from prompt edits (the prompt is tuned later); a label-set change already goes through taxonomy versions |
| 4 Gold dev | — | never stale; it can be **incomplete** (rows removed) and can hold **orphaned rows** |
| 5 Tuning | `dev_done` approved: `prompt`, `taxonomy`, `classifier_model`, `gold_dev` | any of them |
| 6 Gold test | `test_result.json` written and `test_done` approved: `prompt`, `taxonomy`, `classifier_model`, `gold_test` | any of them |
| 7 Threshold | `threshold.json`/`threshold_sample.json` written and `threshold_chosen` approved: `prompt`, `taxonomy`, `classifier_model`, `candidates` | any of them |
| 8 Full run | each `results.jsonl` row: `run` | the row's `run` ≠ current `run_digest` (that row is not done) |
| 9 Browse | — | shows a notice if any row's `run` is not current |

Removing or replacing test rows changes `gold_test`, so the test result goes stale; removing dev orphans changes `gold_dev`, so Tuning goes stale.

### Statuses and reasons

```python
Status = Literal["current", "stale", "incomplete", "not_started"]
```

- **current:** the stage's completion rule (the rules in `first_incomplete_stage`) is met and every recorded component matches.
- **stale:** complete, but a recorded component differs.
- **incomplete:** the completion rule is **not** met, but the stage was complete before: its own flag is set, or a later stage is complete. Example: dev rows removed after Tuning was accepted ("44 of 50 rows").
- **not_started:** not complete and never was. This is a project that has not got that far. **It gets no mark** in the UI and does not appear in the Redo plan. Without this status a new project would show every stage as incomplete.

Every non-`current` status carries a **reason of at most 24 characters**, used by the rail tooltip, the banners and the plan. For stale stages it is built from the components that differ, most upstream first: `seeds changed`, `embedding model changed`, `candidates changed`, `prompt changed`, `taxonomy changed`, `classifier model changed`, `gold rows changed`. If several differ, the first is the reason (the plan may show all). Stage 8 has no components, only `run`, so its reason is stage 7's when that is stale, otherwise `classifier input changed`. For incomplete stages it is a count: `44 of 50 rows`.

Clarifications made while implementing `stage_status` (task 04):

- **Stage 8** is `stale` only when a success row of a candidate at or above the threshold has a `run` that is not current. A run that is merely partial (rows current, some candidates missing) is `not_started`, so a resumed run shows no mark. Stage 8 is never `incomplete`. **Stage 9** is `current` when stage 8 is complete, otherwise `not_started`.
- A stage's recorded components are the union of what `state.inputs[flag]` and the derived file (`test_result.json`, `threshold.json`) recorded, so a re-run that rewrote the file is still `stale` until the user re-approves. Stage 2 compares `candidates.meta.json` (`seeds_digest`, `embedding_model`). Stages 1, 3 and 4 never are stale.
- `RunScreen.run_all` drops, before classifying, the error rows and the rows of the items it is about to classify, so a re-run replaces stale rows instead of duplicating them (D3: they stay until overwritten).
- Incomplete reasons: `not approved`, `no seeds`, `files missing`, `no candidates`, `N of 50 rows`, `not accepted`, `not chosen`.

## Backend

### `history.py` (new)

```python
save(artifact, text, source, summary="", group=None) -> bool   # False if unchanged
sync() -> list[dict]                                            # log external changes; returns the new entries
entries(artifact=None) -> list[dict]                            # newest first for display is the caller's job
text(object_hash) -> str | None                                 # the saved text, for previews and diffs
is_current(entry) -> bool                                       # the newest entry of its file
can_undo(artifact) -> bool;  can_redo(artifact) -> bool
undo(artifact) -> dict | None;  redo(artifact) -> dict | None
restore(artifact, seq) -> dict                                  # make the file as it was after entry `seq`
approval(stage, flag, inputs, summary) -> None
class NeedsVersion(Exception): ...                              # see "Taxonomy and gold"
```

- **`save`** is the only way the three files are written by the app. Order: write the object (if absent), write the file (temp file + `os.replace`), append the log line. If the process dies between the second and third step, the next `sync()` sees a file that does not match the log and records it as `external`, so nothing is lost. A save of identical content is a no-op and writes no entry.
- **`sync`** hashes the three files and compares each to the `after` of its last entry. A difference (the user edited in an editor, ran `git checkout`, `git pull` or `git stash`) is logged as `source="external"`. A project with no log gets one `baseline` entry per existing file. `sync` runs at project open, on entering every stage screen, **when the app regains focus** (Textual 8.2.8 has `events.AppFocus`; check how it behaves in the terminals we support), and at the start of `undo`, `redo` and `restore`. It reads three small files. It returns the entries it just added so the UI can announce each external change once; "already announced" is kept in memory, not on disk.
- **Stacks are derived from the log; there is no extra state.** Replay one artifact's entries: `edit` entries with source `user`, `assistant`, `external`, `restore` or `baseline` push onto the undo stack and clear the redo stack; an `undo` entry moves the top of the undo stack to the redo stack; `redo` moves it back. Entries sharing a `group` pop together (one assistant proposal that adds ten seeds is one undo).
- **Undo and redo append entries; they never rewrite the log.** An undo writes the target's `before` through the same write path with `source="undo"`. They do nothing to the pipeline: no classifier call, no automatic re-run. Stale status then follows from the digests.
- **Restore** (from the timeline) makes the file match its state after a chosen entry and appends a `restore` entry. It is a normal edit: undoable. Restore is allowed for any entry, including a `baseline` entry (the design agent disabled it for baseline rows; this spec allows it, see "Design handoff").
- **Taxonomy and gold.** A taxonomy change that alters the label set or mode while gold labels exist is not a plain text edit (003 D12). **This is a common case, not a rare one:** a user can edit labels before labelling any gold, label gold, and then undo that earlier edit. Two situations, which the confirmation must word differently:
  - *The entry is a `version` start* (the label change that began taxonomy version N). Undo calls `files.restore_version(n)`: the current state is archived as a new version `m` first, and **the gold labels of version n come back**. The undo entry records `snapshot=m`; redo of it is `restore_version(m)`. Nothing is lost.
  - *Any other undo, redo or restore that would change the label set or mode while `files.taxonomy_in_use()`* raises `NeedsVersion`. After the user confirms, the app calls `files.start_new_version(target_taxonomy)`: the current state is archived, and **gold labels are cleared on the same items** (D12). `NeedsVersion` carries `kind` (`"restore"` or `"new_version"`), the target taxonomy and the number the archive will get, so the confirmation can say which of the two it is and name the version.
- **Callers after an undo or redo:** reload their widgets from the files, and call `ChatPanel.record(summary, body)` so the assistant is told (no model call), exactly as `taxonomy.restore` does today. For `prompt`, the Tuning screen supersedes pending proposals (as `tune.accepted` does) but **does not re-run**: the user presses Re-run (design: the Edit prompt modal's primary button reads "Re-run  F2" after an undo). The re-run of a previously seen prompt is all cache hits.

### Where `save` replaces existing writes

| Today | After |
|-------|-------|
| `brief.write_seeds` | `history.save("seeds", …, source="user")`; `propose_seeds` uses `source="assistant"` and a shared `group` |
| `taxonomy.commit_taxonomy` / `files.write_taxonomy` (no version case) | `history.save("taxonomy", …)` |
| `files.start_new_version` | writes a `version` entry, and its `write_taxonomy` goes through `save` |
| `taxonomy.save_prompt`, `write_prompt` tool, `tune.accepted` | `history.save("prompt", …)` |

### Approvals

`confirm_approve` (`app.py`), `tune.action_done`, `final.accept` and `threshold` each set a `State` flag by hand. Replace with one `files.approve(flag, stage, summary)` that sets the flag, stores `state.inputs[flag]` (the stage's current components from the table above) and calls `history.approval`. Un-approving never happens automatically (D3).

### `files.stage_status()` and resume

```python
stage_status() -> dict[int, tuple[Status, str]]    # str: the reason (<= 24 characters), "" if current
first_incomplete_stage() -> int                    # now the lowest stage whose status is not "current"
```

- `first_incomplete_stage` keeps its 1–9 return value and its completion rules; it now returns the lowest stage that is stale, incomplete **or not started** (a new project resumes at 1). `run.pending` counts only rows whose `run` is current. This fixes the gap described above.
- `final.prompt_hash` (and its import in `run.py`) is replaced by the components. The Stage 8 "untested prompt" block keeps taking precedence over the stale state, as the design describes.

### Redo plan

```python
redo_plan(from_stage=1) -> list[dict]
# {stage, status, reason, live_calls: int | None, cached_calls: int | None, dollars: float | None, price_unknown: bool}
```

One row for **every stale or incomplete stage** (not `not_started`), in order. Stages that make no model calls (Gold, Taxonomy) have `live_calls` and `cached_calls` `None`; the UI shows `·`. For the rest, count how many calls would be live and how many would be cache hits **without calling anything**, by building the same cache keys the stage would use:

- Stage 2: one embedding per seed (`cost.cache_key(embedding_model, "embed_query", seed)`).
- Stage 5: the labelled dev rows. Stage 6: the labelled test rows. Stage 7: the ids in `threshold_sample.json`. Stage 8: the candidates at or above the threshold with no current-digest row.
- A classifier hit is an entry whose `output` is a dict (`classifier.classify` treats the old list shape as a miss). Add one helper, `classifier.is_cached(text, prompt, taxonomy, model)`, so the rule lives in one place.
- Dollars for the live calls use the existing estimate in `screens/run.py::estimate` (average tokens per call from `cost.breakdown()`; move it to `cost.py` if both modules need it). Unknown price → `dollars=None`, `price_unknown=True`, shown as `?` with the usual warning. Never `$0`.

### Gold after seeds change (D2)

```python
files.orphaned_gold(split=None) -> list[GoldRow]    # gold rows whose id is not in candidates.jsonl
files.gold_coverage() -> dict                       # {"dev": {"rows", "labelled", "orphaned", "orphaned_labelled", "orphaned_by_label": {...}}, "test": {...}}
gold.remove(ids, reason) -> int                     # moves rows to gold_removed.jsonl, returns how many
gold.draw(split, n)                                 # existing; now also excludes ids in gold_removed.jsonl
```

- "Orphaned" means the item is no longer in the candidate pool after Search was re-run. Its labels are still valid; only its representativeness changed. The default is to keep it (D2). Orphaned rows stay labelled and count toward progress until removed.
- Row ids are unique across both splits, so `remove` takes ids only.
- Removing rows lowers the labelled count, so the stage is `incomplete` ("44 of 50 rows") and `first_incomplete_stage` returns 4 (dev) or 6 (test) until the split is back to `SAMPLE_SIZE` labelled rows. `draw` tops it up (n = rows missing); the new rows start unlabelled. Removing rows also changes `gold_dev` / `gold_test`, so Tuning / the test result go stale.
- Removing or replacing **test** rows after the test result was viewed weakens the held-out guarantee. The confirmation says so (wording in `PLAN_004_INTEGRATION.md` §6), whenever the split is `test`.
- `draw`'s RNG seed uses the number of gold rows, so a draw after a removal is deterministic but different from the original; that is fine.

### Embedding model change (D10)

`candidates.meta.json` records `embedding_model`. Stage 2 is stale with reason `embedding model changed` when `config.embedding_model` differs from it, independently of the seeds. A meta file without the field is treated as unchanged.

Why it matters: query vectors are only comparable with the corpus vectors if they come from the same model. `search.py` already refuses to search when a local corpus's `meta.json` names a different model than `config.toml`, so a change that is accepted means the project was pointed at a different embedded corpus or store (Project settings, F3), and the existing candidates and gold ids may refer to a corpus that is no longer searched. The user must be told before anything downstream is trusted:

- Search shows a warning (not just the neutral "Seeds changed, rerun needed" status): the project's embedding model is now X; the current candidates were built with Y; run the search again, and expect gold rows to be reported as no longer in the pool.
- Project settings, after saving a changed embedding model on a project that has candidates, says the same in one line.
- The stage 2 mark and the Redo plan use the reason `embedding model changed`; the plan counts one embedding call per seed, all live (the new model has no cache entries) and priced from the embedding model's recorded usage, or `?`.
- The assistants' `# Pipeline status` names it.
- After the re-run, the normal orphan flow applies: ids that are not in the new candidates are orphaned.

Not covered: switching to a different corpus that uses the same embedding model name. The meta file does not record the corpus identity (O8).

### What the assistant is told and can do

All three assistants (Brief, Taxonomy, Tuning) already get per-run `instructions` that are recomputed every run, which is the guarantee. Add two sections to each:

```
# Pipeline status
1 Brief and seeds: current
2 Search: STALE: seeds changed (12 added, 3 removed)
5 Tuning: STALE: prompt changed
…
# Gold coverage
dev: 50 labelled, 6 orphaned (no longer in the candidate pool: ids …, first 80 characters of text, labels)
test: 50 labelled, 0 orphaned
```

The orphan list is capped (suggest 10 rows) with a total count. Undo, redo and restore are recorded in each assistant's history as edit lines with no model call, the same mechanism as every other user edit.

**Proactive message (D9).** On the Tuning screen, when the stale set or the gold coverage differs from what the assistant was last told, append an UPDATED context line carrying the two sections and let the assistant reply in a sentence or two. The record of what was last sent uses the same digest-in-a-meta-file approach as the Taxonomy context update (`taxonomy.read_meta` / `write_meta`; write the digest after the turn is appended so a half-sent turn is not recorded as sent).

New tools, on the **Tuning** assistant (it already works with the dev gold through `get_disagreements`; see O3 for the Gold screen):

- `get_gold_coverage(split=None)` — read-only; the counts above and the capped orphan list with id, text and labels.
- `remove_gold(ids, reason)` — asks the user to confirm inside the tool call, as `write_taxonomy` does (`await self.app.push_screen_wait(...)`), with the same removal modal as the Gold screen titled "The assistant wants to remove N dev rows" (**Reject  Esc**, **Remove N rows**). It returns the real outcome to the model ("Removed N rows." or "The user rejected the removal."). Nothing is written before the user presses Remove.
- `draw_gold(split, n)` — calls `gold.draw`; the new rows are unlabelled and the **user** labels them.

The assistant has no tool that sets a gold label (D7).

### Cache

Unchanged, apart from the `classifier.is_cached` helper above. Notes for the README: a description-only edit to a label changes the system prompt and therefore re-classifies everything, which is correct; `history/` is small text and should be committed; `cache/` may be git-ignored if it grows.

## Design handoff: what this spec changes

The design agent answered the open questions in `PLAN_004_INTEGRATION.md` §0 and designed the surfaces listed in the next section. This spec accepts those answers: **F6 Undo, F7 Redo, F8 History, F9 Redo plan** (F-keys because `TextArea` and `Input` do not bind them; `ctrl+z`/`ctrl+y` keep their typing meaning), the Redo plan as a modal that reopens after each re-approval, rail glyphs `↻` stale and `◐` incomplete with reasons on the stage banner and in the plan, the held-out warning wording, `gold_removed.jsonl`, and the gold tools on the Tuning assistant only.

Where this spec differs, the design handoff needs these changes (to be sent to the design agent):

1. **Prompt version numbers are removed from History.** The mock approval row reads "Approved: Tuning loop (dev accuracy 0.920, prompt version 3)"; drop "prompt version 3". Identify entries by time, file, source and summary (D8). The Tuning screen's existing automatic counter is untouched.
2. **Version row copy.** "Taxonomy version 2 saved (50 dev labels kept)" reads as if the labels stayed live. Under D12 a new version clears the live gold labels and the archive keeps them: "Taxonomy version 2 started (version 1 holds 50 dev labels)".
3. **The "Undo changes the labels" modal has two cases** (see "Taxonomy and gold"). When undoing a version start, the text says the earlier gold labels come back and the current state is archived as version M. For any other label-changing undo, it says gold labels will be cleared on the same items (D12) and that the current labels, prompt and results are archived as version N. The button label "Archive as version N and undo" fits both.
4. **`not_started` stages get no mark** and are not in the Redo plan. Only `stale` and `incomplete` stages are marked.
5. **Removing dev orphans can mark Tuning stale** (the `gold_dev` component), and removing test rows marks the test result stale. The mock `redo/plan-seeds` shows stages 2, 4 and 7 only; it should also show stage 5 when dev rows were removed after Tuning was approved.
6. **Tuning's Done button** is disabled until the dev set has run with the current prompt. Stage status stays stale until the user approves again, so the screen needs its own "metrics are current" flag, set when the dev run completes.
7. **`remove_gold` blocks inside the tool call** (see above); no "Waiting for the user to confirm" result is needed.
8. **Restore on a BASELINE row is allowed.** The mock disables it. Either is acceptable; this spec allows it because the baseline is a real earlier state.
9. **Tool names:** `get_gold_coverage` replaces the separate list tool.
10. **New: the embedding-model warning** on Search and in Project settings has not been designed.

## What the user can see and do (UI surfaces)

The backend above exposes data; these are the places it must show up. Keys follow the existing rules (every key has a button, every button shows its key, no colour alone, works at 80×24, 100×30, 120×36). Details, copy and state ids are in `PLAN_004_INTEGRATION.md` as amended above.

1. **Undo / Redo** for each of the three editors: the seed list (Brief), the Labels panel and the Prompt panel (Taxonomy), and the prompt (Tuning's Edit prompt modal). Disabled when `can_undo` / `can_redo` is false and while that editor has a draft open. After use, a one-line note ("Undid: …").
2. **History** (modal, F8): the combined timeline, newest first, with source badges, approval and version events as their own rows, a file filter, a diff or text preview and **Restore this**.
3. **External change notice:** shown once per detected change, with Undo, History and Dismiss.
4. **Stale markers:** rail glyphs with a legend, a narrow-header badge, a banner on stages 5–9, a notice on Browse.
5. **Redo plan** (modal, F9): stale and incomplete stages in order with live and cached counts and dollars or `?`; the primary button goes to the earliest stage; after each re-approval it reopens on the next one. Never approves.
6. **Approvals** appear in the History modal; the user re-does them on the stage itself.
7. **Gold after a seeds change:** a count on Search; on the Gold screen an orphan banner, a Rows modal, confirmed removal (with the number of labels discarded and, for test rows, the held-out warning) and "Draw N replacements".
8. **Assistant:** the status and coverage sections arrive as a context line (UPDATED, with a short reply); the tools render as tool lines; `remove_gold` opens the confirmation.
9. **Embedding model change (not yet designed):** a warning on Search, a one-line note after saving Project settings, a stage 2 mark with the reason `embedding model changed`.

## Behaviour that changes in 001–003

- `first_incomplete_stage` also returns the lowest stale, incomplete or not-started stage (001 completion rules otherwise unchanged).
- `run.pending` and the Stage 8 "done" rule require a current `run` on each row.
- `final.prompt_hash` is replaced by recorded components; a legacy `prompt_hash` file is still compared the old way.
- Setting a `State` flag goes through `files.approve`, which records the components and an `approval` log entry.
- `candidates.meta.json` records `embedding_model`.
- `gold.draw` skips ids in `gold_removed.jsonl`.
- 003 D12 (taxonomy versions) is unchanged. Its archives still copy `gold.jsonl`, results and the other derived files.
- Tuning gains an `r` binding that re-runs the dev set, and `action_done` does nothing while the screen's dev metrics are not current (UI task).
- The gap noted above (prompt change after a full run leaving stage 8/9 looking complete) is closed.

## Tasks

Task files are written after this revision is accepted. The planned order:

| # | Task | Depends on |
|---|------|-----------|
| 01 | `history.py`: objects, log, `save`, `sync` (including app focus), undo/redo/restore, `text`, `is_current`, tests | — |
| 02 | Route the three files' writers through `history.save`; edit recording; taxonomy-version link and `NeedsVersion` (both kinds) | 01 |
| 03 | `files.approve`, `State.inputs`, `approval` and `version` entries with summaries | 01 |
| 04 | Components, `run_digest`, `stage_status` (four statuses, short reasons), new `first_incomplete_stage`, `run.pending`, `final`/`run.py` switch, embedding model in `candidates.meta.json` | 03 |
| 05 | `classifier.is_cached`, `redo_plan` | 04 |
| 06 | Gold: `orphaned_gold`, `gold_coverage`, `gold.remove`, `draw` exclusion, `gold_removed.jsonl` | 04 |
| 07 | Assistant context sections, the UPDATED message, and `get_gold_coverage` / `remove_gold` / `draw_gold` | 04, 06 |
| 08 | UI: undo/redo buttons, F6–F8, the History modal, the external-change block | 02, design |
| 09 | UI: stale markers, banners, Redo plan, embedding-model warning on Search and Project settings, Tuning `r` | 04, 05, design |
| 10 | UI: gold orphan handling | 06, design |
| 11 | README, `AGENTS.md`/`CLAUDE.md` current-state update, end-to-end test, size sweep for new modals | all |

## Tests

All offline; no real model, AWS or keyring. Expected values are written by hand in the test, never computed by the code under test.

- **History:** a sequence of saves, undos and redos yields the hand-written file contents at each step; a new edit after an undo clears redo; `group` entries undo together; a no-op save writes no entry; a file changed behind the app's back is logged as `external` and returned by `sync`; a crash between file write and log append (simulated) is recovered by `sync`; a project with no log gets baseline entries; the log is append-only (earlier lines unchanged); `text(hash)` returns what was saved.
- **Taxonomy:** undoing a `version` entry restores gold labels and a redo restores the new version; editing labels before any gold, labelling gold, then undoing that edit raises `NeedsVersion(kind="new_version")` and, once confirmed, clears gold labels on the same items; the same situation through a `version` entry has `kind="restore"` and keeps labels.
- **Statuses:** a new project is all `not_started` and resumes at stage 1; changing the prompt marks stages 5–8 stale with reason `prompt changed` and leaves 1–4 current; changing seeds marks 2 stale (`seeds changed`) and, after a re-run, 7 (`candidates changed`); changing only the embedding model marks 2 stale with reason `embedding model changed`; a `candidates.meta.json` without the field is current; restoring the old prompt makes everything current again; removing dev rows after Tuning was approved makes 4 `incomplete` ("44 of 50 rows") and 5 stale (`gold rows changed`); a project with no recorded inputs is all current; every reason is at most 24 characters.
- **Redo plan:** with `FunctionModel` call counting, the plan's cached and live counts equal what a real run then does, and a second run makes zero calls; an unpriced model gives `?`, never `0`; non-model stages have `None` counts; `not_started` stages are absent.
- **Gold:** orphans are exactly the rows missing from the pool; `remove` writes `gold_removed.jsonl` and `draw` never returns those ids; removing below 50 labelled sends resume back to stage 4 or 6.
- **Assistant:** the status and gold-coverage sections appear in the instructions; the UPDATED message is added once per change and not again for the same state; `remove_gold` writes nothing until confirmed and returns the user's answer; no tool sets a label.
- **UI:** one Pilot smoke test per new screen/modal, and each new modal added to `tests/test_sizes.py`.

## Open questions

For Chris:

- **O3 — Where the assistant's gold tools live.** The Gold screen has no assistant. This spec and the design put the tools on the Tuning assistant. Alternatives: also add them to the Taxonomy assistant, or add a chat to the Gold screen.
- **O8 — Switching to a different corpus with the same embedding model name** is not detected (the meta file records no corpus identity). Add one (corpus path or store name) later if it matters.

For the design agent:

- The ten changes listed under "Design handoff: what this spec changes", in particular the embedding-model warning (change 10) and the two-case Undo modal (change 3).

## Needs a human

Nothing in this spec needs credentials or a real corpus. Two checks only a human at a real terminal can do: that F6–F9 reach the app in the terminals we care about (many terminals and operating systems reserve some function keys, and I have not verified this), and a manual pass after implementation: edit seeds, a label description and the prompt; undo and redo each; run `git checkout` on `prompt.md` and confirm the external-change notice; change the prompt after a full run and confirm stages 5–8 show stale and the redo plan counts match the real run.
