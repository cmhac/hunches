# Backend changes implied by the rail redesign

Written for the agent implementing the design in `cmhac/hunches`. The UI work is in `ui_kits/tui-rail/`. This file lists what the design needs from the code that is not purely visual. File references are to `main` at the time of writing (2026-10-05).

The design catalogue shows every state. Where a state below has an id (for example `taxonomy/context-updated`), open `ui_kits/tui-rail/index.html` and pick it from the list.

---

## 1. Taxonomy chat starts with context, and refreshes it when upstream changes

States: `taxonomy/start`, `taxonomy/ready`, `taxonomy/context-open`, `taxonomy/context-updated`, `taxonomy/context-updated-open`.

### Today

`screens/taxonomy.py` builds the agent with `build_instructions()`: fixed `INSTRUCTIONS`, the first user message from `brief.md`, and 10 random candidate texts. The agent waits for the user to speak. The seed-generation conversation (`chat/brief.json`) and per-seed search results are not given to it.

### Wanted behaviour

1. When `TaxonomyScreen` opens, build a **context message** and send it to the agent as the next user turn. The agent replies on its own, without the user typing, with a short summary of where things stand and that it is ready to start building the taxonomy. Then the interview starts.
2. The context message contains:
   - the brief conversation (from `files.load_chat("brief")`: user and assistant text only, tool calls collapsed to one line each);
   - the seeds (`candidates.read_seeds()`), each with **items won**: the count of rows in `candidates.jsonl` whose `best_seed` is that seed. The counts add up to the number of candidates;
   - the search summary: total candidates at or above `candidates.FLOOR`, and counts per band (`candidates.band_counts`);
   - instructions for this turn (below).
3. **Staleness.** Compute a digest of the inputs: the seed list plus `candidates.jsonl` content. Persist the digest of the last context sent, for example in `.hunches/chat/taxonomy.meta.json`, as `{"context_digest": "...", "sent_at": "..."}`. On every `TaxonomyScreen` mount (stage screens are rebuilt by `goto_stage`, so this also covers returning from Brief or Search, and the rebuild after Project settings saves), compare:
   - no history: send the initial context;
   - history exists and the digest differs: append an **update** context message and let the agent reply;
   - digest equal: do nothing.
4. The update message says what changed and does not repeat everything. Include: seeds added, removed or edited; candidate count before and after; the new per-seed items won. End with instructions: reply in one or two sentences about what changed and whether it affects the conversation so far, then continue where you left off.
5. Taxonomy and prompt files already written are not touched by an update. The agent may propose changes through the normal `write_taxonomy` and `write_prompt` tools.

### Suggested text for the initial turn's instructions

> Reply in two or three sentences: where things stand (how many seeds, how many candidates, which seed found the most), and that you are ready to start building the taxonomy. Then begin the interview. Draft the prompt from the seeds and the best matches as the answers come in.

Keep the existing `INSTRUCTIONS` (the interview, `write_taxonomy`, `write_prompt`, off_topic rules). Drop the `brief.md` and random-sample parts of `build_instructions()`, since the transcript and seed results replace them. Keep `brief.md` itself: other code may read it.

### Delivery details

- Send the context as the user prompt of `agent.run_stream(...)` with the existing `message_history`, so it is persisted by `files.save_chat("taxonomy", ...)` like any other turn.
- The UI needs to recognise context turns so it can render them as a collapsed line (see section 2) and not as a user message. Two options, pick whichever the installed pydantic-ai supports cleanly:
  - put a marker in message metadata if `ModelRequest` carries a metadata dict in the installed version;
  - otherwise prefix the content with a sentinel such as `<hunches-context kind="initial|update">` and have the renderer strip it.
- Cost is recorded as usual through `cost.record`. A long brief conversation can be large; cap the transcript (for example the last 40 turns) and truncate long tool arguments. Truncation should be visible in the text ("… 7 more").
- Do not resend context on every mount. The digest check is what prevents that.

### Edge cases to handle

- Seeds are empty or `candidates.jsonl` is missing: the screen is only reachable after stages 1 and 2, but guard anyway; skip the context turn and fall back to the old behaviour.
- The user changed the assistant model in Project settings: `goto_stage` rebuilds the screen with the new model; history is replayed to it as is.
- Mount while a previous reply is still streaming: `exclusive=True` on the worker already cancels it. Make sure a half-sent context does not leave `taxonomy.meta.json` claiming it was sent. Write the digest after the reply completes, or after the context turn is appended to history.

---

## 2. Tool calls shown in chat, with details on demand

States: `brief/seeds`, `brief/tool-open`, `taxonomy/drafted`, `taxonomy/tool-open`. Applies to every `ChatPanel` (Brief and Taxonomy today).

### Today

`ChatPanel.write_messages` (in `app.py`) renders `ToolReturnPart` as one line, `↳ tool_name · content`. `ToolCallPart` arguments are never shown. The chat is a `RichLog`.

### Wanted behaviour

- Each tool call renders as one line: `↳ name  summary  ▸`. The summary is the tool's return string (for example "Added 10 seeds."), clipped with an ellipsis.
- The line is expandable. Expanded, it shows the call's **arguments** and the tool's **result** in a tinted block under the line, indented to the text column. Collapsed is the default. Context lines (section 1) use the same pattern with a `◇` marker, and an `UPDATED` tag for update messages.
- Pair `ToolCallPart` with its `ToolReturnPart` by `tool_call_id`. Arguments come from the call part (`args_as_json_str()` or the dict form), pretty-printed. Long values truncated with "… N more" in the collapsed-adjacent view; the full text stays available in the expanded block.
- Streaming: while a tool call is running, show the line with the name and a spinner or `…`, then update it when the result arrives.

### Implementation note

`RichLog` cannot hold widgets. Replace the log with a `VerticalScroll` that mounts one widget per turn (`Static` for text, `Collapsible` or a small custom widget for tool and context lines). Keep the live streaming `Static` at the bottom. Auto-scroll to the end after each mount unless the user has scrolled up. Restore history through the same mount path as live turns so resumed conversations look identical.

Tool-call lines have no blank row between consecutive calls; other turns are separated by one blank row. See the kit's `ChatPanel`.

---

## 3. Smaller behaviours that come from the design

These are short; each names the state to look at.

- **Search: seeds changed.** States `search/seeds-changed`, `search/done`, `search/confirm`. Store with `candidates.jsonl` the digest of the seeds it was built from (for example `candidates.meta.json` with `seeds_digest`, `written_at`, `floor`). If `seeds.csv` no longer matches: button label is "Run search", no confirmation, and "Seeds changed, rerun needed" is shown next to it. If it matches and results exist: label "Rerun search" and a confirmation modal first (text in the state). With no results: "Run search".
- **Search: results dim.** Results panels are inactive and dimmed whenever there are no results yet (not approved, never run, running, failed).
- **Search: progress.** State `search/running`. `candidates.build_candidates` needs a progress callback, called after each seed with `(done, total, seed)`. The UI shows "4/12" and the seed text in a bar. There is no useful progress inside one seed (local is a single matrix product; S3 pages are sequential and the total is unknown).
- **Search: top seeds threshold.** States `search/top-filtered`, `search/threshold-open`. The "items won" per seed is recomputed for a chosen minimum similarity. This can be derived from `candidates.jsonl` (`best_seed`, `max_similarity`); no new data. Note that a seed's items won at a higher threshold can change the ranking.
- **Search: S3 cap warning.** Text is "WARNING: S3 returned its cap of 10,000 hits for at least one seed; only the 10,000 highest-scoring hits are kept." Update `screens/search.py` to match (it still says "topK cap").
- **Search: no "Done" paragraph.** Remove the long "Done. … candidates written…" line; the table is the confirmation.
- **Brief: Approve button.** A visible "Approve seeds F2" button on the seeds panel, disabled while there are no seeds. While adding or editing a seed it is replaced by "Save (Enter)" and "Discard (Esc)". The "Add at least one seed first." message and its state are gone; keep the guard in `action_approve` as a no-op. The seed input is shown only while adding or editing. Confirm text: "Approve N seeds and start searching?". The seeds table has a `#` column.
- **Chat panels.** A send button (up arrow) next to the input, disabled when the input is empty or a reply is streaming. Empty Brief chat shows centred text: "Describe what concepts you want to search for and the assistant will help you generate seed phrases".
- **System settings, New project, Project settings.** Save and Create are disabled until enough input exists; the message is shown to the right of the button. System settings: disabled with no API key at all. New project: disabled until the corpus, or bucket, index and embedding model, are valid and no key is missing. Project settings: disabled while the corpus has an error.
- **Models block.** Each model row carries its own marker, "RECOMMENDED" or "DIFFERS FROM RECOMMENDED"; there is no separate "DIFFERS" line. A divider sits between the thinking selector and the classifier.
- **Projects empty state.** A centred "New project" button below the message. The button is new UI; `n` still works.
- **Header and rail.** At 100 columns and wider the stage stepper moves into a left rail; below 100 columns the one-row header returns. The rail shows cost, including the "cost ?" warning for unpriced models. See `ui_kits/tui-rail/README.md`.

---

## 4. Brief and Taxonomy: structured views with explicit save and discard

States: `brief/seeds`, `brief/editing`, `brief/adding`, `taxonomy/drafted`, `taxonomy/edit-labels`, `taxonomy/edit-labels-invalid`, `taxonomy/edit-prompt`.

### Today

- `screens/taxonomy.py`: two `TextArea`s show `taxonomy.yaml` and `prompt.md` raw. `on_text_area_changed` writes **on every keystroke** (prompt always; taxonomy only if it validates, otherwise it shows "taxonomy.yaml not saved: …"). There is no draft, save or discard.
- `screens/brief.py`: seeds are a `DataTable`; `a`/`e` use a shared `Input`; Enter saves, and there is no visible way to discard other than clearing the input.

### Wanted behaviour

**Brief**
- Show the seeds as a numbered list titled "Seeds" with a count; no "seeds.csv" naming.
- `e`: the selected row becomes an input holding its text. Show "Editing seed N", the original ("was: …"), an UNSAVED badge once the text differs, and two buttons: **Save** (Enter) and **Discard** (Esc). Save is disabled while the text is empty or unchanged. Other rows are dimmed and not selectable; Approve is hidden.
- `a`: append an empty input row; button is **Add seed** (Enter); Discard removes the row. Nothing is written until Save.
- Replace the single shared `#seed-input` with this inline editor (a `DataTable` cannot embed an `Input`; use a `ListView` or a `VerticalScroll` of rows, mounting an `Input` into the edited row).
- `propose_seeds` appends only, so a seed being edited keeps its index. If the user is mid-edit when the agent appends, append silently; do not touch the draft.

**Taxonomy**
- **Labels panel (read view):** mode and count in the subtitle; one row per label: coloured ■ name (`theme.label_tag`), description muted; a fixed last row `off_topic` marked "built in". An **Edit labels** button (`e`) opens edit mode.
- **Labels edit mode:** a `Select` for mode (single / multi), one row per label with name and description `Input`s and a delete control, an **Add label** button. All edits stay in a draft held by the screen. Buttons: **Save** (Ctrl+S) and **Discard** (Esc); the UNSAVED badge replaces EDITING in the panel's subtitle once the draft differs. Save is disabled while the draft is unchanged or invalid; show the validation message (from `files.Taxonomy.model_validate`, first line) to the right of the buttons, and mark the offending row with a red left bar. UNSAVED badge appears once the draft differs from the file.
- **Prompt panel (read view):** render `prompt.md` as markdown (`textual.widgets.Markdown`) so headings and bullet lists look formatted; label names inside bullets can stay plain. **Edit prompt** (`e`) swaps to a `TextArea` (language markdown, line numbers) with **Save** / **Discard**.
- Only one panel can be in edit mode. While one is, the other panel and the Approve button are inactive (set `disabled`), and `F2` does nothing.
- Writes happen only on Save: `files.write_text("prompt.md", ...)` or `files.write_taxonomy(...)`. Remove the per-keystroke `on_text_area_changed` writes.

### Agent writes while the user is editing

`write_taxonomy` and `write_prompt` currently overwrite the file and the widget. With drafts, define the rule so the user never loses typing:
- If the matching panel is **not** in edit mode: write the file and refresh the panel, and tag the panel "UPDATED BY ASSISTANT" until the user next interacts with it or the next agent turn starts.
- If the panel **is** in edit mode with a draft: do not write. Return an error string from the tool, for example `Not written: the user is editing the taxonomy. Ask them to save or discard first.`, so the model sees it and can tell the user in chat.

### Notes

- Whether a `Markdown` widget's styling can match the mock (primary h1, bold h2, bullets with a coloured label name) depends on the installed Textual version; set `Markdown` component classes in `hunches.tcss`. If a closer match is needed, build the view from `Static` rows as the mock does.
- Keep the `Footer` keys in sync: view mode shows `e Edit panel` and `F2 Approve`; edit mode shows `^s Save` and `esc Discard`. Use a screen-level `BINDINGS` entry for `ctrl+s` that is active only in edit mode (`check_action`).

---

## 5. REQUIREMENT: the agent always has the same context as the user

**Rule:** anything the user can see and change that the agent reasons about must reach the agent, as soon as it changes, without the user having to say so. The agent must never answer from a stale view of the seeds, labels, mode or prompt.

States: `brief/edits-sent`, `taxonomy/edits-sent`, `taxonomy/edits-sent-open`, `taxonomy/mode-changed`.

### What counts as a change
| Screen | User action | Record |
|---|---|---|
| Brief | Save an edited seed | "Seed N edited" with was / now |
| Brief | Add a seed | "Seed added" with the text and its number |
| Brief | Delete a seed | "Seed N deleted" with the text |
| Taxonomy | Save Labels (names, descriptions, add, delete) | "Labels: …" with a per-label was / now |
| Taxonomy | Switch mode single / several | "Mode: one label → several labels" |
| Taxonomy | Save Prompt | "Prompt: N lines changed" with a unified diff |
| Taxonomy, Brief | Changes made on another screen while this one was not mounted | existing digest mechanism (§1), sent as an UPDATED context line on mount |

**Not sent:** unsaved drafts. Nothing is recorded while a panel is in edit mode; Discard records nothing. The agent's own tool writes are already in the history as tool calls and are not repeated.

### How
1. **Edit messages (the record).** On every Save, append a context message to the screen's chat history and persist it with `files.save_chat(stage, history)`. **Do not call the model.** The message is delivered with the next turn the user sends. Shape: `# What changed` (a short diff), `# Current <artifact>` (the full new state of what was edited; for the prompt include the whole text, since the agent will be asked to revise it), and `# Instructions`: "No reply needed. Treat this as the current state in your next turn." In the UI it is one collapsed line, tagged **YOU EDITED**, expandable (same renderer as context lines, §2).
2. **Current-state instructions (the guarantee).** Also make the current files part of the agent's instructions on every run, so a missed or reordered edit message cannot leave the agent stale. With pydantic-ai this is a dynamic instructions function registered on the agent (`@agent.instructions`, evaluated per run); it reads `candidates.read_seeds()`, `files.read_taxonomy()` and `prompt.md` fresh each time. **Check the installed pydantic-ai version supports per-run instructions functions;** if it does not, rebuild the `Agent` (or pass `instructions=` to `run_stream`) with the current state on each turn.
3. **Agent writes are guarded** by the rule in §4: if the user has the panel in edit mode, the tool returns "Not written: the user is editing…" so the agent never overwrites a draft.

### Notes
- Which screens: Brief (`screens/brief.py`, hook in `save()`, `add_seeds` and the delete action) and Taxonomy (`screens/taxonomy.py`, hook in the Save handlers that replace the per-keystroke `on_text_area_changed` writes). Put the shared helper next to `files.save_chat`, for example `files.record_edit(stage, summary, body)`.
- **Digest interaction (§1).** After recording an edit, update `taxonomy.meta.json`'s `context_digest` (and the equivalent for Brief if you add one) so the next mount does not also send an UPDATED line for the same change.
- **Seed edits reach the Taxonomy agent too.** The Taxonomy chat's seeds are covered by the §1 digest check on mount, and by instructions (item 2) on every run.
- **Mode** is a first-class user choice, not only something the agent asks about: the mode `Select` is always visible in the Labels panel (empty or filled). Changing it enters Labels edit mode with the new mode in the draft, so it is saved with Save, and recorded as a mode edit. With the mode already chosen, the agent should not ask about it again; the instructions function should state the mode when set.
- Cost: edit messages add input tokens to later turns only. Keep each message to the diff plus the current state of the edited artifact; do not repeat unrelated files.

---

## 6. Gold labelling does not run the classifier

States: `gold/single`, `gold/multi`, `gold/confirm`, `test/single` (the prediction states are deleted).

### Today
`screens/gold.py` classifies each item right after the user labels it: `action_confirm` calls `self.run_worker(self.predict(...))`, `predict` calls `classifier.classify(text, self.prompt, self.taxonomy, self.model)`, results are kept in `self.predictions`, and `show_prediction` draws the `Model: … ✓ agrees / DIFFERS` line. The screen also loads `prompt.md` and `config.classifier_model` for this.

### Wanted
Labelling is human only. Remove from `GoldScreen`:
- `predict()`, `show_prediction()`, `self.predictions`, `self.prompt`, `self.model`, the `#prediction` Static and its CSS, and the `classify`, `Prediction` and `Model` imports;
- the `run_worker(self.predict(...))` call in `action_confirm`.
`action_confirm` then only validates the labels, writes `gold.jsonl` and moves to the next item. The `not ready` guard still needs `taxonomy.yaml` (for the labels), not `prompt.md`.

### Consequences to check
- **Cost and the header.** No API calls happen on this stage, so cost does not change while labelling. Nothing to do in `cost.py`.
- **Classifier cache.** Labelling used to warm the cache (`cost.cache_get`) for dev items, so the first Tuning run was partly free. It now starts cold: the first dev run classifies all of the rows. Tuning already shows a centred progress indicator for this (`tune/first-run`).
- **Stage 6.** `final.test_stage()` reuses `GoldScreen("test")` for labelling the test split; it gets the same change, and the first evaluation still happens only in `FinalScreen`.
- **Tests:** drop or rewrite tests that assert a prediction appears after labelling.

---

## 7. Gold labelling: too few candidates is a critical error

States: `gold/pool-short`, `test/pool-short`, `gold/exhausted`, `test/exhausted`.

### Today
`screens/gold.py`: `add_rows(n)` calls `draw(split, n)`; when it returns fewer than `n` rows the screen sets a warning note ("Only N unlabelled candidates were left to draw.") and carries on. On mount, `GoldScreen` tops up to `files.SAMPLE_SIZE` rows the same way. If the pool is smaller than 50, the user can label what exists but `files.first_incomplete_stage` (stage 4: "fewer than SAMPLE_SIZE labelled gold rows with split dev", stage 6: the same for test) never passes, so the stage cannot be finished and the message gives no way out.

### Wanted
1. **Blocking case (mount).** After the top-up on mount, if the split still has fewer than `SAMPLE_SIZE` rows, set a `pool_short` state holding: `found` (rows in `candidates.jsonl`), `used` (gold rows already taken by the other split, for the test split), `left` (unlabelled candidates not in `gold.jsonl`), `need` (`SAMPLE_SIZE`). Render the blocked view (see the states): error banner, explanation, the counts, **Add seeds** (`app.goto_stage(1)`) and **Project settings F3**. Hide the item, labels and counts panels and the progress block; labelling is not offered. `d` and the label keys do nothing in this state.
2. **Non-blocking case (draw more).** When `action_draw_more` gets fewer than `DRAW_MORE` rows back and `left == 0`, show a persistent error banner instead of the note: "No more candidates to draw: only N were left, so the set has M items. If you need more, your corpus may be too small for this analysis." Clear it on the next label or move.
3. **Dev and test share the pool.** `draw()` excludes ids in either split. State the numbers in the test case: found, already in dev, left, needed.
4. **Copy.** Keep the exact wording in the states. The phrase "Your corpus may be too small for this analysis" is deliberate.

### Optional, not designed
Warn earlier on the Search screen: when `candidates.jsonl` has fewer than `2 * SAMPLE_SIZE` rows (100), show an error banner there ("Only N candidates found. Labelling needs at least 100: 50 dev and 50 test."). It would avoid reaching this error three stages later. Ask the design owner before adding it.

---

## 8. Time remaining while the classifier runs

States: `tune/first-run`, `tune/rerun`. Test and Threshold can use the same helper.

`screens/tune.py` `run_dev` already counts `done` items and the total. Record `start = time.monotonic()` before the loop and after each result compute `eta = elapsed / done * (total - done)`. Format with `run.seconds_text` (`screens/run.py`, for example `14s` or `1m05s`; it prints `0m14s` today, so trim a leading `0m`). Show nothing until `done >= 3`, so the first estimates are not wild. Cached items return almost instantly and skew the average; compute the rate from non-cached completions if `classify_many` can report that, otherwise accept the skew and note it. Show it once, in the detail line under the bar ("23 of 50 · about 14s left"), not beside the bar. `final.py` `run_test_set` and `threshold.py` `run_sample` have the same loop and can reuse the helper.

---

## 9. Tuning: assistant chat

States: `tune/below`, `tune/chatting`, `tune/tool-open`, `tune/asking`, `tune/proposal`, `tune/proposal-pending`, `tune/rerun`, `tune/pass`, `tune/rejected`, `tune/proposal-failed`, `tune/metric`, `tune/chat-tab`.

### Today
`screens/tune.py`: one `Agent(config.assistant_model, instructions=INSTRUCTIONS, output_type=str)`. `propose()` builds a text with the current prompt, the taxonomy and up to `MAX_SHOWN` (20) disagreements, calls `agent.run(text)`, records cost, and pushes `ProposalScreen(self.prompt, result.output)`. There is no conversation: the output string *is* the new prompt, the user cannot ask anything, and nothing persists.

### Wanted
1. **Chat.** Yield `ChatPanel("tuning", self.agent)` (from `app.py`, with §2's expandable tool lines) and persist with `files.save_chat("tuning", ...)`. The agent is conversational: change its instructions so it replies in prose and never outputs the prompt as plain text. Replace `output_type=str` handling accordingly.
2. **Tools.**
   - `get_disagreements(label: str | None = None, limit: int = 10) -> str`: read-only; returns disagreements (text, gold, predicted) filtered by gold or predicted label. The context message only carries the first `MAX_SHOWN`; this gives the rest.
   - `propose_prompt(prompt: str, rationale: str) -> str`: stores the proposal and opens `ProposalScreen(self.prompt, prompt)`. The tool should **wait for the user's decision** and return it to the model: "Accepted", "Accepted with edits: <unified diff vs. the proposal>" or "Rejected". In Textual, `await self.app.push_screen_wait(...)` works only inside a worker; `ChatPanel.reply` already runs in one. Confirm against the installed Textual. While the modal is open, show the card in the chat as pending; if the user dismisses without deciding (Esc), keep the card with a **Review** button that reopens the modal and have the tool return "Pending: the user has not decided yet".
   - Both tools return "Not available while the dev set is running" during a run. The chat panel itself is hidden (`display = False`) while `self.running`, so the user cannot send a message mid-run; any reply already streaming when a run starts (e.g. after Accept) finishes before the run's UI takes over.
3. **Context (same mechanism as §1 and §5).**
   - *First run:* when the first dev run completes and no tuning history exists, send the initial context: dev metrics (target metric, score, n), per-label P/R/F1/gold, the disagreements (up to 20), the current prompt, the taxonomy, and instructions ("reply in two or three sentences: where the classifier stands against the target and the main pattern in the errors; offer to propose an edit; call propose_prompt only when asked or agreed"). The assistant replies on its own.
   - *Every later run:* when a dev run completes, if the digest of (prompt hash, classifier model, gold dev rows, metrics) differs from `chat/tuning.meta.json`, append an UPDATED context line with the new metrics and disagreements and let the assistant reply briefly.
   - *User edits (YOU EDITED lines, no model call):* target metric or score changes (`action_next_metric`, `action_score`), and a proposal accepted **with edits** (the diff between what the assistant proposed and what the user accepted, plus the new prompt). Rejections are covered by the tool result.
   - Also add the §5 requirement here: put the current prompt, taxonomy and target in the agent's per-run instructions so it cannot be stale.
4. **Propose edit button / `e`.** Instead of the separate `agent.run` in `propose()`, send the canned user message "Propose a prompt edit based on the current disagreements." through the chat. Disable the button (and `e`) while a reply is streaming or a run is in progress.
5. **Accept path.** `accepted()` is unchanged: write `prompt.md`, `rerun()`. The tool result is returned when the modal closes; the rerun's completion then triggers the UPDATED context (item 3).
6. **Errors.** A failed assistant call is an error line in the chat (`ChatPanel` already does this); the `"Proposal failed: …"` note is removed.
7. **Cost.** Chat turns are recorded as elsewhere (`cost.record`). The old `propose()` recording moves into the chat path.

### Layout notes for the screen code
- 120 columns and wider: `Horizontal` with `ChatPanel` first (`width: 42`, as on Brief and Taxonomy) and the results column (`1fr`) after it. Under 120: a `TabbedContent` (or two containers toggled by a `-chat` class) with tabs "Chat" and "Results" (in that order); key `c` switches; show a ● on the Chat tab when the assistant has replied or a proposal is pending and Results is showing. Use `on_resize` to toggle, as `BrowseScreen` does.
- At 120+, the disagreements `DataTable` and the text panel are stacked (table above, selected item's text below); under 120 they stay side by side as today.
- The metric/target controls and the action row are buttons mirroring `m`, `+`, `-`, `e`, `F2` (see the README's button rule).


---

## 10. The classifier returns reasoning, and Tuning shows it to the user and the assistant

States: `tune/below`, `tune/chatting`, `tune/tool-open`, `tune/failed-item`, `tune/pass`, `final/result` (any state with a disagreement selected). Also the `get_disagreements` tool lines and the context message in `tune/*`.

### Today
`classifier.py`: `classify()` builds `Agent(model, output_type=list[label_type], system_prompt=system)` and returns `Prediction(labels, error, cached)`. The model returns only labels. There is no explanation, so the disagreements table can show gold vs predicted but nobody (user or assistant) can see why the classifier chose a label. The cache (`cost.cache_put(key, result.output, usage)`) stores only the label list.

### Wanted
1. **Structured output with reasoning.** Replace `output_type=list[label_type]` with a model, for example `class Classification(BaseModel): reasoning: str; labels: list[label_type]`. **Field order matters: `reasoning` must come before `labels`** so the model explains first and decides second (this also tends to improve accuracy). The `@agent.output_validator` keeps calling `validate_labels(out.labels, taxonomy)` and raises `ModelRetry` on a violation.
2. **System prompt.** Add one sentence in `system_prompt()`: "First give a short reasoning (one to three sentences) that names the evidence in the text, then the labels." Keep it out of `prompt.md` so users do not have to maintain it. It changes the string the cache key hashes, so existing cache entries stop matching. That is intended.
3. **`Prediction` gains `reasoning: str | None`** (None when `error` is set or the entry is an old cache hit). `classify_many` yields it unchanged.
4. **Cache.** Store `{"output": labels, "reasoning": reasoning}`. Treat an entry without `reasoning` as a miss (or rely on the key change in item 2). Reasoning must survive a cache hit, otherwise the second tuning run would lose it.
5. **Where it is kept.** `tune.py` keeps predictions in memory per run; carry `reasoning` into the disagreement records it builds. For the full run (stage 8) decide whether to write it to `results.jsonl`: it is useful in Browse but adds output tokens and file size. The design only needs it in Tuning and the Test result. Suggested default: store it for dev and test runs, and make it a `include_reasoning` flag for the full run (off by default).
6. **UI (`DisView` equivalent in `tune.py` and the Test/Final screen).** The detail panel for the selected disagreement is titled `text · classifier reasoning`: item text, then a bold teal `classifier reasoning` heading, then the reasoning text. When the call failed there is no reasoning; show only the existing "Model failed: ..." line.
7. **Assistant context.** Include the reasoning wherever disagreements are given to the assistant: in the context message (each disagreement gets a `reasoning:` line under it) and in the `get_disagreements` tool result (§9). Both are shown in the expandable context and tool lines, so the user can read exactly what the assistant was given. The assistant's instructions should say: "Each disagreement includes the classifier's own reasoning. Use it to explain why the classifier chose its label and to decide what the prompt is missing."
8. **`MAX_SHOWN`.** Reasoning adds roughly 30 to 60 tokens per item. Keep the 20-item cap in the context message and let the tool fetch more.
9. **Cost.** Output tokens rise for every classification. The rail's cost figure and the ETA helper (§8) pick this up automatically through `cost.record`; no UI change.
10. **Tests.** Update `tests/test_classifier.py`: `TestModel`/`FunctionModel` outputs become `Classification` objects; add a test that reasoning is returned on a cache hit; keep the retry tests for `off_topic` combination and single mode.

Depends on the installed pydantic-ai version: how a Pydantic model is passed as `output_type` and how the output validator receives it. Check the current docs.


---

## 11. Tuning: edit the prompt by hand and re-run

States: `tune/edit-prompt`, `tune/edit-prompt-changed`, `tune/rerun-manual`. Builds on §5 (agent has the same context as the user) and §9 (Tuning chat).

### Wanted
1. **Button and key.** `Edit prompt  o` in the controls row (`screens/tune.py`). Add `Binding("o", "edit_prompt", "Edit prompt")`. Disabled while a dev run is in progress or before the first result. Single-letter keys do not fire while the chat input has focus (as for `e`).
2. **Modal.** A new `PromptEditScreen(ModalScreen[str | None])` (can reuse the layout of `ProposalScreen`, without the diff panel): an editable `TextArea` loaded with the current `prompt.md`, a caption, and a note that unchanged items are not re-charged. Buttons: `Cancel  Esc` (dismiss with None) and `Save and re-run  F2`, disabled until the text differs from the file (compare on `TextArea.Changed`). Both are real buttons; the keys are their shortcuts.
3. **On save.** `files.write_text("prompt.md", text)`, set `self.prompt`, then start the same dev run that Accept starts after a proposal (reuse that method). Do not call the model for anything except the re-run itself.
4. **Tell the assistant (§5).** Before the run, append a context message to the tuning history and persist with `files.save_chat("tuning", ...)`, without calling the model: `# What changed` with was/now lines for each changed block (a line diff of old vs new is enough), then `# Current prompt` and the usual "No reply needed" instruction. Summary line: `Prompt: edited by the user`. Use the same helper as the "accepted with edits" message so both read alike.
5. **Pending proposal.** If a proposal card is pending in the chat when the user saves a manual edit, mark it superseded (`status: "superseded"`) so the old diff cannot be applied over the new prompt.
6. **After the run.** Same as after an accepted proposal: the UPDATED context line and the assistant's short reply (§1/§9), run cost recorded as usual. Cached items with an unchanged system string are not re-charged; any change to the prompt text changes the cache key (`classifier.system_prompt`) for every item, so a re-run after a prompt edit is a full re-classification. The modal note should say "Items whose prompt text is unchanged are not re-charged" only if you keep per-item keys otherwise; if every edit invalidates everything, change that sentence to "The dev set is classified again with the new prompt."
7. **Not in scope.** Taxonomy edits during Tuning are not offered; labels stay locked once gold labelling has started.


---

## 12. Stop and resume for every classifier run

States: `tune/first-run`, `tune/stopped`, `tune/rerun`, `final/running`, `threshold/sampling`, `run/*`.

### Today
Only the Full run (`screens/run.py`) can be stopped (`x`) and resumed (`s`). The dev run in Tuning (`screens/tune.py`), the test run and Threshold sampling start on mount or on a key and cannot be interrupted; they use `classifier.classify_many`.

### Wanted
1. **Stop.** A `Stop  x` button and `x` binding on each of those screens. It cancels the worker that iterates `classify_many` (the generator's `finally` already cancels outstanding tasks). Predictions already finished are kept: they are in the classifier cache (`cost.cache_put`), so nothing is paid for twice.
2. **Stopped state.** Keep the progress at "N of M" and show `Resume  s`. Resume calls the same method as Start; cached items return instantly, so it continues where it stopped. Do not compute metrics from a partial dev run; the results panels stay hidden (as while running) until the run completes.
3. **Chat.** The chat panel stays hidden while stopped (the run is unfinished), and `get_disagreements` / `propose_prompt` keep returning "Not available while the dev set is running" (reword to "...is not complete" if you like).
4. **Leaving the screen.** Navigating away while a run is in progress should stop it the same way, so no worker keeps spending in the background.
5. **Shared widget.** Build one `RunIndicator` widget (title, `ProgressBar`, counts line, optional stats line, optional button) and use it on all four screens and in the Full run panel.
