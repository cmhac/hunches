# Handoff: hunches TUI redesign, as a change set against `main`

## 1. Read this first
**Baseline:** `cmhac/hunches@main` at tree `2278ad08fd5c` (read 2026-10-05). Everything in this document is a **difference from that code**. If a screen, key binding or behaviour is not mentioned, it does not change.

Three kinds of change, tagged in every list below:
- **[visual]** TCSS, Rich markup or widget composition only. No logic.
- **[behaviour]** UI logic changes in an existing screen (enabled/disabled states, edit modes, new buttons, copy).
- **[backend]** needs data, stored state or an agent change. These are specified in `BACKEND_CHANGES.md`; each item names the repo file.

**Where to look:**
- `reference/ui_kits/tui-rail/index.html` click-through, `states.html` gallery. Serve `reference/` with `python -m http.server`. Every state has a `when:` line naming the code condition that produces it, and its id is quoted below.
- `BACKEND_CHANGES.md` for everything tagged [backend].
- `reference/ui_kits/tui/` is the **superseded** first design. Do not implement from it.
- `textual/theme.py` and `textual/hunches.tcss` are the earlier drop-in files, already merged in main. The rail design needs **no new theme colours or variables**; it needs new TCSS rules (section 3).

**Do not port the JSX.** Recreate the look with Textual widgets and TCSS. One mock cell = one terminal column by one row. Everything must work at 80×24; larger sizes only grow `1fr` regions.

**Requirement that cuts across screens: the agent always has the same context as the user.** Every user edit to seeds, labels, mode or prompt is recorded in the agent's chat history on Save and the agent's instructions always carry the current state. See BACKEND_CHANGES.md §5. [backend]

**Suggested order:** (1) section 3 global shell and component rules, which restyle most screens at once; (2) section 5 per-screen items; (3) the [backend] items, starting with BACKEND_CHANGES.md §4 (drafts instead of autosave) and §1 (taxonomy context).

## 2. Already in main: do not redo
- `theme.py` (`HUNCHES` theme, `LABEL_COLORS`, `label_tag`, `label_text`, `editor`) and `hunches.tcss` exist and match `textual/`. Keep them.
- Screens that exist and are only restyled or lightly changed here: `SystemSettingsScreen`, `RecommendationModal`, `ProjectsScreen`, `RemoveModal`, `NewProjectScreen`, `ProjectSettingsScreen`, `ModelPicker`, `PathPicker` and all nine stage screens.
- The `Setup` screen from the first design no longer exists in main; first run opens `SystemSettingsScreen`. The design reflects that.
- Bindings: all current bindings stay (`q n p F2 F3 F4 F5` and per-screen keys). The only new keys are `ctrl+s` in Brief and Taxonomy edit modes and `enter`/`esc` as Save/Discard in the Brief seed editor (section 5, Brief and Taxonomy).

## 3. Global changes [visual]
Apply once, in `app.py` and `hunches.tcss`; most screens change without touching their code. **The TCSS below is a starting point.** Check each rule against the installed Textual (theme.py says 8.2.8), because the mocks were drawn from the design and not run in Textual.

### 3.1 Shell: rail at 100 columns and wider
- Today `StatusHeader` (`app.py`) is a one-row bar yielded first by every screen, with the stage stepper, `n/9 name` and cost.
- **Wide (≥100 columns):** replace it with a left rail 26 columns wide, full height, background `$surface`. It lists: `hunches` (primary, bold), the project name (muted, ellipsis); a blank row; the 9 stages, one per row (done: `✓` success with muted name; current: `●` primary, strong bold name, `$panel` background and a primary left bar; upcoming: `·` and faint name); a blank row; **Projects F4**, **Project settings F3**, **System settings F5** (muted names, faint key; the current one gets `▸`, strong bold, the same bar); at the bottom `n/p stage · q quit` (faint), then `cost` (muted) over `$0.3127` (strong bold). Unknown price: a warning reverse badge `cost ?` and the model names in warning colour below it.
- **Narrow (<100 columns):** keep today's one-row header exactly as is.
- Implementation hint: keep the class name `StatusHeader` so every screen's `yield StatusHeader()` still works. On `on_resize` toggle a `-rail` class and render multi-line markup; TCSS `StatusHeader.-rail { dock: left; width: 26; height: 100%; }` against today's `dock: top; height: 1`. The content must sit beside the rail with the footer under the content column only (the rail runs the full height). Dock order and whether the footer spans under the rail depend on the installed version; if it does, wrap the screen body and `Footer` in one container.
- The footer in wide mode drops `q n p F3 F4 F5`, since the rail shows them (mock: `Footer` filters them when `window.__wide`). Narrow mode keeps today's full footer.
- The content column starts on the first row, level with the top of the rail. No blank row above the panels.
- **Boxes fill the available space** (measured in the mocks at 80×24, 100×30 and 120×36): the rightmost panel in a row ends flush with the terminal's right edge (the 1-column gutter exists only *between* panels, never after the last one); panels end half a row above the footer, with no extra blank row; a tab strip (Tuning, under 120 columns) is a full-width `$surface` bar with a half-row gap (1 row in a terminal) before the first panel; side-by-side panels with no rail (under 100 columns) keep a 1-column gutter between them.
- Panels end half a row above the footer. A terminal has whole rows: use one blank row (`margin-bottom: 1`) or none, and decide when you see it.

### 3.2 Panels (`panel()` helper, `.panel` rules)
- Today: `widget.border_title / border_subtitle` on a `round` border (`$border-blurred`, `$border` when `:focus-within`).
- Now: **no border.** Background `$surface`, padding `0 1`, a one-row title line with the title (bold, strong; primary when focused) on the left and the subtitle (muted) right-aligned. Focus is a left accent: `border-left: outer $primary` on `:focus-within` (the same technique Textual's own toast uses). Panels sit directly against each other, separated by background only.
- If `border_title` renders on a `blank`/`hidden` border in the installed version you can keep the helper unchanged; otherwise make `panel()` mount a one-row title `Static`. Subtitles that contain a widget or badge (Search threshold, EDITING/UNSAVED, UPDATED BY ASSISTANT) need the second approach.
- Suggested rules:
```
.panel { border: none; background: $surface; padding: 0 1; }
.panel:focus-within { border-left: outer $primary; }
DataTable { background: transparent; }
DataTable > .datatable--header { background: transparent; color: $text-muted; text-style: none; }
DataTable > .datatable--cursor { background: $panel; color: #EEF1F5; text-style: bold; }
DataTable:focus > .datatable--cursor { background: $boost; }
Input { border: none; background: $panel; height: 1; padding: 0 1; }
Input:focus { background: $boost; border-left: outer $primary; }
Select > SelectCurrent { border: none; background: $panel; height: 1; }
FooterKey .footer-key--key { background: $boost; color: #EEF1F5; text-style: bold; }
.banner { border-left: outer $warning; padding: 0 2; }   /* .-stale uses $error */
```

### 3.3 Components
- **Table headers:** no fill, muted, no bold. Cursor row: tinted bar (above) with a primary left accent when focused. Zebra off.
- **Inputs and selects:** one row, tinted strip (`$panel`), `$boost` plus a primary left bar when focused, no border. This replaces the `tall` border used by chat, Browse search and Threshold cutoff.
- **Buttons:** one row, filled, bold, label with its key as part of the text (for example `Approve seeds  F2`). Variants: default (`$boost`), primary, success, error. **Disabled:** `$panel` background, faint text (not just dimmed).
- **Every keyboard action that saves data, finishes a task, starts or stops work, or deletes has a visible button, with its key in the label (`Finish dev set  F2`).** The footer keys stay; the button is the same action (`on_button_pressed` calls the matching `action_*`). Buttons that cannot run yet are disabled (section above), not hidden. Where the buttons sit is listed per screen in section 5.
- **Footer:** key caps are `$boost` blocks with bold strong text and a space before the muted description.
- **Modals:** no border; `$surface` background, left bar `$primary`, title in primary bold on the first row, buttons right-aligned. Default order stays Cancel then Approve (success, focused).
- **Notices:** one-line, unchanged; banners get a left bar in their colour.
- **Chat panel:** the user, assistant and tool gutters (`› │ ↳`) are unchanged. Added: send button `↑` right of the input (disabled while empty or streaming), one blank row between the last message and the input, an empty-state centred message, and expandable tool-call and context lines (see BACKEND_CHANGES.md §2).

## Design tokens
Dark only.

| Role | Token / Textual var | Hex |
|---|---|---|
| background | `$background` | `#0E1218` |
| surface (table headers, inputs, modal bg) | `$surface` | `#141A23` |
| panel (header bar) | `$panel` | `#1B2230` |
| boost (hover, blurred cursor, key caps) | `$boost` | `#252E3E` |
| blurred border | `$border-blurred` | `#344056` |
| text | `$foreground` | `#CDD4DE` |
| text strong (values, item text) | — | `#EEF1F5` |
| text muted (labels, hints, column headers) | `$text-muted` | `#8C96A6` |
| text faint (placeholders, upcoming stages) | `$text-disabled` | `#5C6676` |
| **primary: focus and action** | `$primary`, `$border` | `#6EA8FE` |
| primary lighten / darken / muted (selection) | | `#B8D4FF` / `#4C86E0` / `#1D2F4D` |
| secondary: YAML keys, diff `@@`, DIFFERS badge | `$secondary` | `#D2BE94` |
| accent: the agent's voice | `$accent` | `#5CC8B4` |
| success / PASS | `$success` | `#7CCB83` (tint `#1C3322`) |
| warning | `$warning` | `#EAB54D` (tint `#3A2E15`) |
| error / FAIL / STALE | `$error` | `#F2557A` (tint `#3E1826`) |
| labels 1–8 (taxonomy order) | `LABEL_COLORS` | `#5CC8B4 #E592B8 #A8D46F #D9A77E #E8D27C #F0B37E #8FD3E8 #9DB4C7` |
| off_topic | `OFF_TOPIC_COLOR` | `#6B7585` |

**Spacing:** whole cells only. Panel padding is `0 1`. Modal padding is `1 2`, or `0 1` for the proposal modal. There's a 2-cell gap between header and footer items and one blank row between chat turns. No margins.

**Borders:** none on panels, inputs or modals in the rail design (see section 3). Focus is a 1-cell left accent bar in `$primary`. The only outlines left are the select dropdown and toast.

**Text styles:** bold, dim, reverse and underline only. No shadows, no gradients.

## Global rules
- **One focus colour.** Only the focused region gets a `$primary` left bar and a `$primary` title. The DataTable cursor is a `$boost` bar with a primary left accent and bold strong text when focused, and `$panel` when blurred. Hover is a `$boost` background.
- **Never colour alone.** Every coloured state also has a word or glyph: PASS, FAIL, STALE, WARNING, DIFFERS, ✓ agrees, ■ label name, +/- in diffs.
- **Badges** are reverse-video uppercase words with one cell of padding: `.badge.-pass` (success bg), `.badge.-fail` (error bg), `.badge.-stale` (warning bg; also UNSAVED and EDITING), `.badge.-info` (secondary bg; DIFFERS FROM RECOMMENDED, UPDATED BY ASSISTANT).
- **Labels** always render as `[label_color]■[/] name`, with the name verbatim from taxonomy.yaml. `off_topic`'s name is muted.
- **Number formats:**
  - Cost: `$0.4213` (4 dp). Unknown cost shows `cost ?`, never $0.
  - Target metric: 3 dp. Target score: 2 dp. P/R/F1: 2 dp.
  - Similarity: 3 dp in Browse. Band edges: 3 dp in Threshold, `:g` in Search.
  - Counts: thousands separators (`f"{n:,}"`), right-aligned.
- **Notices** are one-line Statics under the relevant region. Classes: `.note` (muted), `.ok`, `.warn`, `.error`. Banners use `.banner.-stale` or `.banner.-warning`: a full-width tinted background with bold text.
- **Glyphs** are Unicode box-drawing and geometric shapes only. No emoji, no Nerd Font glyphs.

## 4. What is NOT changing (to avoid wasted work)
Screen order, stage logic, `files.first_incomplete_stage`, `state.json` fields, every key binding listed in main, the classifier, metrics, cost tracking, Rich-markup colours for labels (`label_tag`), and the copy of every message not listed in section 5.

## 5. Per-screen change set
Format: **what changes in the code in main** → state ids to look at. State ids are in `reference/ui_kits/tui-rail/*.jsx`.

### System settings (`screens/system.py`) and RecommendationModal
- [visual] Each group (API keys, Models, Saved S3 stores) is a tinted block with a bold title. Notes move to the bottom. → `system/edit`, `system/first`
- [behaviour] **Save is disabled until at least one API key is saved (status KEYRING or ENV).** The message ("Add at least one API key to save", or the error) sits to the right of the button. Remove the `"ERROR: save at least one API key first"` path as the primary way to learn this, but keep the guard in `save()`. → `system/nokey`
- [behaviour] The line `DIFFERS from recommended` is removed. Each model row (assistant, classifier) ends with `RECOMMENDED` (success text) or a `DIFFERS FROM RECOMMENDED` info badge. A blank row separates assistant from thinking, and a divider line plus blank rows sit above the classifier row. `Reset to recommended` is spaced below. A model without a price shows `no price: cost will show ?` (warning) on its own row, and the separate `pricewarn` line is removed. → `system/differs`, `system/noprice`
- [visual] The note `Prices from genai-prices …; the header shows actual spend` now says "the sidebar shows actual spend" (in rail mode; keep "header" below 100 columns if you want exactness).
- [visual] **RecommendationModal** lays out as groups: **assistant** (now / new lines, new in success bold, prices muted), **thinking** (now / new), a divider, **classifier** ("unchanged" when equal), then the note and buttons Keep mine / Use new (success, focused). → `system/recommend`

### Projects (`screens/projects.py`) and RemoveModal
- [visual] Table restyled (section 3). The attention banner is a tinted block with a left bar. → `projects/list`
- [behaviour] **Buttons for every key action** in a row under the table: **New project n**, **Edit e**, **Remove x**, **Locate l** (enabled only for MISSING DIR / MISSING CORPUS rows), **Refresh r**. → `projects/list`
- [behaviour] **Empty state:** centred message plus a primary **New project** button below it (calls `action_new`). → `projects/empty`
- [visual] RemoveModal and the path picker are restyled modals. → `projects/remove`, `projects/delete`, `projects/locate`

### New project (`screens/new_project.py`)
- [behaviour] **Create is disabled until valid:** local needs a valid corpus; S3 needs bucket, index and an embedding model; and no required API key may be missing. The hint ("Required: corpus" or the corpus problem) is shown to the right of the button. The separate "Create with required fields empty" error state is removed, but keep the guards in `create()`. → `new/local`, `new/corpus-ok`, `new/corpus-bad`, `new/s3`, `new/blocked`
- [visual] Models summary block restyled; a divider separates the thinking line from the classifier. → `new/local`

### Project settings (`screens/project_settings.py`)
- [behaviour] **Save is disabled while the corpus has an error;** the message sits to the right. → `pset/problem`
- [visual] Same model-row markers as System settings (`RECOMMENDED` or the `DIFFERS FROM RECOMMENDED` badge). → `pset/differs`
- The confirmation modal text is unchanged. → `pset/confirm`

### Model picker, path picker
- [visual] Restyled as raised modals. Rows unchanged: model, ` ★ recommended`, ` DEPRECATED`, then the price line. → `picker/list`, `picker/embedding`, `picker/other`, `picker/nokey`

### 1 Brief and seeds (`screens/brief.py`)
- [backend] **Every seed save, add or delete is sent to the agent** as a collapsed "YOU EDITED" line in the chat (no model call); the agent's instructions also carry the current seeds. → `brief/edits-sent`. Spec: BACKEND_CHANGES.md §5
- [behaviour][backend] **Seeds panel is a numbered list titled "Seeds" with a count**, not "seeds.csv · N". Edit and add are **explicit**: `e` turns the row into an input and shows "Editing seed N", a "was: …" line, an UNSAVED badge once the text differs, **Save (Enter)** and **Discard (Esc)**; other rows dim and Approve is hidden. `a` appends an input row with **Add (Enter)** and **Discard (Esc)**. Replace the shared `#seed-input`. → `brief/seeds`, `brief/editing`, `brief/adding`. Spec: BACKEND_CHANGES.md §4.
- [behaviour] **Buttons for every key action** in one centred, wrapping row: **Add seed a**, **Edit e**, **Delete d** (both disabled with no seeds) and **Approve seeds F2**. → `brief/seeds`
- [behaviour] **Approve seeds F2 button** at the bottom of the panel, disabled when there are no seeds, next to an **Add seed a** button. The status line `"Add at least one seed first."` is removed; keep the guard in `action_approve`. Confirm text is now "Approve N seeds and start searching?" (was "…and continue to search?"). → `brief/empty`, `brief/confirm`
- [visual] Empty states: the chat shows centred text "Describe what concepts you want to search for and the assistant will help you generate seed phrases"; the seeds panel shows the existing "No seeds yet…" text centred. → `brief/empty`
- [visual] Chat: send button, tool calls as expandable lines. → `brief/seeds`, `brief/tool-open` (spec: §2)

### 2 Search (`screens/search.py`, `candidates.py`)
- [behaviour] The top row is a primary button reading **Run search  r** (**Rerun search  r** when results exist and the seeds are unchanged). Disabled and labelled **Searching…** while running, and disabled when seeds are not approved. → `search/never-run`, `search/running`, `search/not-approved`
- [behaviour][backend] **Progress bar** to the right of the button while searching: filled by seeds done, label `4/12  <seed phrase>`, label colour inverts over the filled part. The separate "Searching..." text label is removed. Needs a progress callback in `candidates.build_candidates`. → `search/running`. Spec: §3
- [behaviour][backend] **Staleness.** If seeds changed since `candidates.jsonl` was written: label is "Run search", no confirmation, and "Seeds changed, rerun needed" (warning) next to the button. If unchanged and results exist: "Rerun search" opens a confirmation ("You've already run the searches, and haven't changed the seed candidates. Depending on the size of the corpus, this can take a long time. Are you sure you want to rerun searches?"). → `search/seeds-changed`, `search/confirm`. Spec: §3
- [visual] Results panels are dimmed and inactive whenever there are no results (not approved, never run, running, failed). → `search/not-approved`, `search/running`
- [visual] "Candidates by similarity" panel (was "candidates.jsonl · by similarity band"): one row per band with a bar scaled to its count and a right-aligned count; the "At or above" column and the Total row are removed; the total shows in the subtitle. "Top seeds" panel (was "best seed (items won)"): ranked rows with rank, count, bar, phrase; the top row has a teal bar. → `search/done`
- [behaviour] **Top seeds has a similarity threshold select** in its subtitle ("similarity at or above 0.6 ▼", options are the band edges as `:g`). Counts are recomputed from `candidates.jsonl` (`best_seed`, `max_similarity`) for rows at or above it. No new data. → `search/top-filtered`, `search/threshold-open`
- [behaviour] The long "Done. N candidates written…" paragraph is removed. The S3 warning reads "WARNING: S3 returned its cap of 10,000 hits for at least one seed; only the 10,000 highest-scoring hits are kept." (the code still says "topK cap"). → `search/capped`

### 3 Taxonomy and prompt (`screens/taxonomy.py`)
- [backend] **Chat starts with context** (brief transcript, seeds with items won, search summary, instructions); the assistant replies on its own with a short summary and says it is ready to build the taxonomy. The context is refreshed, as an UPDATED line plus a short reply, when seeds or candidates change. Replaces `build_instructions()`'s `brief.md` and random samples. → `taxonomy/start`, `taxonomy/ready`, `taxonomy/context-open`, `taxonomy/context-updated`. Spec: §1
- [behaviour] **Single / several is a user choice in the UI.** A compact `Select` captioned "mode" (options "One label per item" / "Several labels per item") is always at the top of the Labels panel, including before any labels exist. Changing it (`m` opens it) enters labels edit mode with the new mode in the draft; Save commits it. The agent is told the mode and should not ask again. → `taxonomy/start`, `taxonomy/mode-open`, `taxonomy/mode-changed`. Spec: §5
- [backend] **Every saved edit to labels, mode or prompt is sent to the agent** as a collapsed "YOU EDITED" line (no model call, expandable to the diff and current state). Drafts are never sent. → `taxonomy/edits-sent`, `taxonomy/edits-sent-open`. Spec: §5
- [behaviour][backend] **No raw files.** "Labels" panel: mode and count, one row per label (coloured ■ name, description), a built-in off_topic row, **Edit labels e**. "Prompt" panel: the markdown rendered, **Edit prompt e**. Edit modes: mode select, name and description inputs, add and delete for labels; a line-numbered editor for the prompt; EDITING then UNSAVED badge in the panel subtitle; **Save (^s)** and **Discard (Esc)**; the other panel and Approve are inactive. Invalid labels disable Save and show the validation message. Remove per-keystroke writes in `on_text_area_changed`. After a tool write, the panel carries "UPDATED BY ASSISTANT". → `taxonomy/drafted`, `taxonomy/edit-labels`, `taxonomy/edit-labels-invalid`, `taxonomy/edit-prompt`. Spec: §4
- [behaviour] **Approve taxonomy and prompt F2 button** under the panels, disabled until both exist or while editing. The "Cannot approve…" status line is removed; keep the guards in `action_approve`. Confirm text: "Approve taxonomy (single, 3 labels) and prompt, and start labelling?" → `taxonomy/confirm`
- [behaviour][backend] Tool calls show as one expandable line each. → `taxonomy/tool-open`. Spec: §2

### 4 and 6 Gold labelling (`screens/gold.py`)
- [visual] Label options: key cap, mark, name, description; the chosen row gets `$boost` and a primary left bar. The note and counts panel keep their content. → `gold/single`, `gold/multi`
- [behaviour][backend] **Running out of candidates is a critical error, not a note.** (1) On mount, if the pool cannot fill the required rows (`files.SAMPLE_SIZE`, 50, for the dev or the test split), labelling is **blocked**: a full-width error banner ("Only 38 candidates were found; the dev set needs 50." or, for test, "Only 24 unlabelled candidates are left for the test set; it needs 50."), and a centred block titled "Your corpus may be too small for this analysis" with the numbers (candidates found, already in the dev set, left to draw, needed) and two actions: **Add seeds** (goes to stage 1) and **Project settings F3**. The stage can never complete otherwise, because `first_incomplete_stage` requires 50 labelled rows per split. (2) When `d` (draw 10 more) finds the pool empty, the old warning note becomes a persistent error banner above the progress block: "No more candidates to draw: only 6 were left, so the set has 56 items. If you need more, your corpus may be too small for this analysis." Not blocking, since the required rows exist. → `gold/pool-short`, `test/pool-short`, `gold/exhausted`, `test/exhausted`. Spec: BACKEND_CHANGES.md §7
- [behaviour] **Buttons for every key action** (right column, under the counts): **Finish dev set  F2** (`test set` on stage 6) on top and **Draw 10 more  d** below it, stacked and centred in the column. Finish is disabled until every row is labelled (below). → `gold/single`, `gold/confirm`, `test/single`
- [behaviour] **Finish is unavailable until every row is labelled.** The `"N items still unlabelled."` note and its state (`gold/unfinished`, `test/unfinished`) are removed. While rows remain, F2 does nothing and its footer key is dimmed; the progress block already shows "33 to go". When all rows are labelled the block reads "All labelled. Press F2 to finish." and F2 opens the existing confirm. Applies to the dev and test sets. In `GoldScreen.action_finish`, return silently when `left` is non-zero (no note), and make the footer binding conditional (`check_action` returning `None` to dim it, or `False` to hide it, depending on the installed Textual). → `gold/single`, `gold/almost`, `gold/confirm`
- [behaviour][backend] **No classification during labelling.** The "Model: …" prediction line (not classified / classifying / failed / agrees / DIFFERS) is removed from `GoldScreen` for both the dev and test sets. Labelling and the tuning loop are separate: the model only runs on Tuning (stage 5), Test evaluation (stage 6), Threshold (7) and Full run (8). The states `gold/classifying`, `gold/agrees`, `gold/differs`, `gold/pred-failed`, `gold/not-classified` and their `test/` twins are deleted. Spec: BACKEND_CHANGES.md §6
- [behaviour] **Prominent progress block** replaces the one-line `dev set  item 18/50, 17 labelled` (`#progress`). A tinted block with a primary left bar at the top of the left column: row 1 `dev set` (primary bold) · `item N` (muted) · right-aligned `33 to go` (strong bold), or `Complete` (success); row 2 a full-width bar with `17 / 50` centred inside it, fill in `$primary` (success when complete), faint dividers at 25 / 50 / 75%; row 3 `Next milestone: halfway · 8 more` (muted) with the percentage right-aligned. When the count lands exactly on 25%, 50% or 75% of the rows (`ceil(total × fraction)`), row 3 shows a one-time "Halfway there. 25 to go." in success; when every row is labelled it reads "All labelled. Press F2 to finish." Works the same for the test split. Compute from what the screen already holds (`done` = rows with labels, `total` = rows in the split, which grows after `d`); no new data or state, and `one-time` just means: show it when the count equals a milestone and clear it on the next label. The bar needs a two-layer label (inverted colour over the fill); in Textual use a `ProgressBar` or `Static` rendered with Rich styling. → `gold/single`, `gold/halfway`, `gold/almost`, `gold/confirm`, `test/single`

### 5 Tuning (`screens/tune.py`): assistant chat
- [behaviour][backend] **Tuning gets the full chat panel** (`ChatPanel("tuning", agent)`, history persisted with `files.save_chat`). The assistant can see the same things the user sees and talk about them; it acts through two tools, a read-only `get_disagreements` and `propose_prompt`, which opens the existing proposal modal. The one-shot `propose()` call is replaced by a chat turn. The "Propose edit  e" button sends a canned user message ("Propose a prompt edit based on the current disagreements.") and the assistant answers in the chat. Full spec: BACKEND_CHANGES.md §9. → `tune/below`, `tune/chatting`, `tune/tool-open`, `tune/asking`, `tune/proposal`, `tune/proposal-pending`, `tune/rerun`, `tune/pass`, `tune/rejected`, `tune/proposal-failed`
- [visual] **Layout.** At 120 columns and wider: chat 42 columns wide on the left, in the same position as on Brief and Taxonomy, and the results on the right (dev-set metrics, then the disagreements table with the selected item's text under it, then the action row). Under 120 columns (including 100×30 and 80×24): a "Chat | Results" tab strip (chat first, as on the left in wide mode); `c` switches; the footer lists `c Chat` first so it survives truncation (and shortens the other labels to Propose / Metric / Done, dropping `+` and `-`, which have buttons); the Chat tab shows a ● when the assistant has replied or a proposal is waiting and you are on Results. The disagreements table and its text panel sit side by side under 120 columns and stack at 120+. → `tune/chat-tab`
- [backend] **Chat content.** Opens with a collapsed context line (dev metrics, per-label table, up to 20 disagreements, current prompt, taxonomy) and a short assistant summary. Every later dev run appends an UPDATED context line and a short reply. User changes are sent as YOU EDITED lines: target metric or score, and accepted-with-edits proposals. A proposal shows as a card in the chat (diff size, Review and Reject while pending; Accepted or Rejected afterwards). → `tune/first-run` (chat waits, dimmed), `tune/metric`, `tune/pass`
- [behaviour] While a dev run is in progress the chat panel is **hidden** (and the tab strip too, under 120 columns): the progress view fills the content area. The chat returns when the run ends. Hide it with `display: none` on `ChatPanel` while `self.running`, so its history and scroll position survive. The "Asking the assistant…" note is removed; the reply streams in the chat. A failed assistant call shows as an error line in the chat, not in the note line. Single-letter keys do not fire while the chat input has focus (normal Textual); Tab moves focus; the buttons always work. → `tune/chat-focus`
- [visual] ProposalScreen keeps its content: a raised modal with a tinted diff and a line-numbered proposal editor.

### 5 Tuning buttons, 6 Test evaluation (`final.py`), 7 Threshold, 8 Full run, 9 Browse
- [behaviour] **Buttons for every key action** (the rule in section 3.3):
  - **Tuning:** a row under the disagreements: a "Target" select (`m`) with `−` / `+` and the value (`-` / `+`), then **Propose prompt edit  e** (disabled without disagreements) and **Done  F2** (success when the target is met, default otherwise; disabled before the first result). The subtitle no longer lists `m metric · +/- score`. → `tune/below`, `tune/pass`
  - **Test:** **Re-run  r**, **Back to tuning  t**, and **Accept  F2** (success; disabled while stale or without a result). → `final/result`, `final/stale`
  - **Threshold:** **Save cutoff  F2** (primary) next to the cutoff input; disabled until the input is a number. The input placeholder drops "(F2 saves)". → `threshold/sampled`, `threshold/picked`
  - **Full run:** **Start / Resume  s** (disabled while running or complete) and **Stop  x** (disabled unless running). → `run/idle`, `run/running`, `run/stopped`
  - **Browse:** no saving or finishing actions; no buttons.
- [visual] Otherwise restyle only, through section 3.
- [behaviour] **Centred progress while the classifier runs.** On Tune (dev run, including the re-run after an accepted proposal), Test (test run and re-run) and Threshold (band sampling), the metric and table panels are not shown while the run is in progress. Instead the content area shows, centred: a title ("Running the dev set", "Running the held-out test set", "Sampling each similarity band"), a progress bar, and "N of M · detail". When the run ends the panels appear; on failure show the existing panels or empty state with the failure note. Use the counts the screens already track (`done` in `run_dev` and `run_test_set`, `self.progress` in `run_sample`); no new data. The footer stays. → `tune/first-run`, `tune/rerun`, `final/first-run`, `final/rerun`, `threshold/sampling`. Implement as a `ProgressBar` (or the screen's existing one) in a centred container toggled by the existing `self.running`.
- One copy string in the mocks was aligned to main: Test's stale banner reads "STALE: prompt.md or classifier model changed since this result was computed. Press r to re-run."

## 6. Open questions the implementer should settle
- Whether `border_title` renders without a visible border (section 3.2).
- Whether `Footer` can sit under the content column only with the rail docked left (section 3.1).
- `Markdown` widget styling for the prompt view (BACKEND_CHANGES.md §4).
- pydantic-ai specifics: how to mark context turns and read tool arguments (BACKEND_CHANGES.md §1–2).

## 7. Files
- `BACKEND_CHANGES.md`: [backend] specs.
- `reference/ui_kits/tui-rail/`: current catalogue. `reference/components-rail/`: current mock widgets, with `.prompt.md` rules in `reference/components/` for the older ones. `reference/assets/hds-loader-rail.js`: loader.
- `reference/ui_kits/tui/`, `reference/components/`: superseded first design.
- `textual/`: theme and stylesheet already in main.
- `reference/DESIGN_SYSTEM.md`: voice, glyphs and keybinding conventions (still valid).

## Change log (rail version, newest first)

- Full run simplified to match the other run screens: one centered block (title, bar, "N of M · about X left", one status line, one button). The estimate and run panels, the live stats line, the failed-item list and the Start/Stop button row are gone. Before starting, the status line is the estimate (items, time, cost); when stopped with failures it is "N items failed and are retried on the next run"; a failed run shows the error text. Button: `Start  s` / `Stop  x` / `Resume  s`, none when complete · `run/idle`, `run/no-samples`, `run/price-unknown`, `run/running`, `run/stopped`, `run/complete`, `run/failed` · [visual]; the per-item error list is no longer shown (keep logging it to `results.jsonl`/the error log)

- Runs: every classifier run now shows the same centered progress indicator (title, 36-column bar, "N of M · about X left"), with real buttons: `Stop  x` while running and `Resume  s` when stopped. The Full run page uses it inside its panel, keeping `Start  s` / `Stop  x` below; the dev run (Tuning), held-out test run and Threshold sampling use it full-screen and gained `Stop  x` / `Resume  s` · `run/*`, `tune/first-run`, `tune/stopped` (new), `tune/rerun`, `final/running`, `threshold/sampling` · [behaviour] + [backend]: see BACKEND_CHANGES.md §12

- Full run: an untested prompt is a hard block, not a warning. When `prompt.md` differs from the tested prompt (or was never tested) the screen shows an error banner, no `Start` button, no `Stop`, no `s`/`x` keys in the footer, and a single `Go to Tuning loop` button · `run/untested` · [behaviour]: remove the "press s again to start anyway" path in `screens/run.py`; `action_start` must return without starting when the prompt differs, even if called by a key; compare against the prompt recorded with the last dev/test run

- Threshold: no text input. The cutoff is chosen by selecting a band row (Enter or click); the chosen row is marked `●`, a line under the table reads `Cutoff 0.650`, and `Save cutoff  F2` is disabled until a band is chosen. The "invalid cutoff" state is deleted since a free number can no longer be entered · `threshold/sampled`, `threshold/picked` · [behaviour]: remove the cutoff `Input` and its float parsing/validation in `screens/threshold.py`; keep the chosen band's lower bound as the value written to config

- Tuning results controls rearranged and measured at 80×24, 100×30 and 120×36 (nothing clipped, bottom edge half a row above the footer): row 1 is the target metric select, `−`, value, `+`, alone; row 2 is `Propose edit  e`, `Edit prompt  o` and `Done  F2` in one line. Both rows are centered horizontally in the results column and vertically in a 3-row band under the panels (a `Vertical` with `height: 3; align: center middle`), half a row apart from row 1. All are compact buttons (1 column of padding). At 120+ the stacked disagreements/text panels now share the height (5:4) so the text and classifier reasoning are visible; before, the text panel collapsed to its title. At 80×24 the text panel is short, so long text and reasoning scroll (`VerticalScroll`) · `tune/*` · visual

- Tuning: new `Edit prompt  o` button (beside `Propose edit e`; stacked under it below 120 columns) opens a full-size modal with `prompt.md` in an editable text area. `Save and re-run  F2` is disabled until the text differs; `Cancel  Esc` discards. Saving writes `prompt.md`, sends the change to the assistant as a context line ("Prompt: edited by the user", with was/now lines) and re-runs the dev set; the chat is hidden during the run · `tune/edit-prompt`, `tune/edit-prompt-changed`, `tune/rerun-manual` · [visual] + [behaviour] + [backend]: see BACKEND_CHANGES.md §11

- Classifier reasoning: the classifier now returns a short reasoning with its labels. Tuning (and Test/Final) disagreement detail panel is titled "text · classifier reasoning" and shows the item text, then a teal "classifier reasoning" block; failed items show no reasoning. The assistant's context message and `get_disagreements` results carry the reasoning too, visible in the expandable lines · `tune/below`, `tune/chatting`, `tune/tool-open`, `tune/failed-item`, `final/result` · [visual] + [backend]: needs a structured classifier output, cache change and prompt change, see BACKEND_CHANGES.md §10

- Tuning: `Propose edit e` and `Done F2` sit side by side (1 column apart) at 120 columns and wider, where the row has room; under 120 they stack as in the previous entry · `tune/below` at 100×30 vs 120×36 · visual (switch the container's `layout` between `horizontal` and `vertical` on width)

- Tuning: `Done F2` sits directly under `Propose edit e` at the right of the controls row, same width, with a half-row gap between them so they read as two buttons (in a terminal use a 1-row `margin-top` on `Done`, or a blank row), instead of beside it · all `tune/*` results states · visual (vertical container, `width: auto`, `align-items: stretch`)

- Tuning: removed the "Dev run finished, cost $..." note under the controls; run cost is already in the rail · `tune/below`, `tune/pass` · visual (delete that `Static` or never set its text)

- Spacing pass on Tuning and globally: no dead column to the right of the rightmost panels (all rail screens), chat panel runs down to half a row above the footer, tab strip is a full-width bar flush above the panels, action row sits one row under the panels with no extra gap, target caption dropped so the row fits on one line at 100 columns · `tune/below`, `tune/chat-tab`, `tune/pass` at 100×30 and 120×36 · visual (see section 3.1)

- Tuning has the full assistant chat on the left (120+ columns) or behind a tab (under 120) the results; context on the first run and after every run, YOU EDITED lines for target and prompt edits, `propose_prompt` and `get_disagreements` tools, proposal cards in the chat · `tune/below`, `tune/chatting`, `tune/proposal`, `tune/pass`, `tune/chat-tab` · **backend**: BACKEND_CHANGES.md §9

- Tuning (and the other classifier-run progress views): time remaining shown in the detail line under the bar ("23 of 50 · about 14s left") · `tune/first-run`, `tune/rerun` · **backend**: BACKEND_CHANGES.md §8 (derive from elapsed time in `run_dev`)

- Rule: every keyboard action that saves, finishes, starts/stops or deletes also has a button. Added buttons on Gold (Draw 10 more, Finish), Tuning (Propose edit, Done, target select and stepper), Test (Re-run, Back to tuning, Accept), Threshold (Save cutoff), Full run (Start/Resume, Stop), Brief (Edit, Delete), Projects (New, Edit, Remove, Locate, Refresh) · `gold/single`, `tune/below`, `final/result`, `threshold/picked`, `run/idle`, `brief/seeds`, `projects/list` · behaviour: `on_button_pressed` mirrors each existing `action_*`; no new data

- Gold labelling: users cannot finish until every row is labelled; the "N items still unlabelled." note and its states are removed, F2 is dimmed until complete · removed states `gold/unfinished`, `test/unfinished` · behaviour in `GoldScreen.action_finish`

- Gold labelling: a candidate pool that is too small is a blocking error with counts and next steps, and an empty pool on "draw 10 more" is an error banner · `gold/pool-short`, `test/pool-short`, `gold/exhausted` · **backend**: BACKEND_CHANGES.md §7

- Gold labelling no longer runs the classifier or shows its prediction; labelling and tuning are separate · removed states `gold/classifying`, `gold/agrees`, `gold/differs`, `gold/pred-failed`, `gold/not-classified` (and `test/` twins) · **backend**: BACKEND_CHANGES.md §6 (remove `predict`, `show_prediction`, prompt and model loading from screens/gold.py)

- Gold labelling: no blank rows between the stacked boxes in the middle column (progress block, item, labels). They are told apart by tint instead: progress and labels on `$surface`, the item panel on `$background`, with the focus bar on the item. The counts panel is flush to the same bottom edge. · `gold/single`, `gold/halfway`, `test/single` · visual: in `GoldScreen.DEFAULT_CSS` set margins between `#progress`, `#item`, `#labels-panel` to 0 and give `#item` `background: $background`

- Empty message lines take no row: on Gold (prediction and note), Tune, Test and Threshold the note line is not rendered when empty, so no blank strip sits between the panels and the footer · `gold/single`, `tune/below`, `final/result`, `threshold/picked` · visual; matches Textual (`height: auto` Statics with empty text take no rows), so keep those Statics at `height: auto` and set `display: none` when empty

- Gold labelling: prominent progress block (count inside a full-width bar, items to go, 25/50/75% milestones with a one-time message, complete state) · `gold/single`, `gold/halfway`, `gold/almost`, `gold/confirm` · behaviour: derive from existing row counts; no new data

- Classifier runs show a centred progress indicator instead of the empty panels (Tune, Test, Threshold) · `tune/first-run`, `tune/rerun`, `final/first-run`, `final/rerun`, `threshold/sampling` · behaviour: toggle on the existing running flags; no new data

- "Not ready" messages ("Finish stage 3 (taxonomy and prompt) first.", "Finish stages 3 and 7 first.") are centred horizontally and vertically in the content area, warning colour, with the footer below · `gold/not-ready`, `tune/not-ready`, `threshold/not-ready`, `run/not-ready` · visual (the `#not-ready` Static in Gold, Tune, Threshold and Run screens)

- Agent context mirrors the user: every saved edit to seeds, labels, mode or prompt is appended to the agent's history as a "YOU EDITED" line, and the agent's instructions carry the current state · `brief/edits-sent`, `taxonomy/edits-sent`, `taxonomy/edits-sent-open` · **backend**: BACKEND_CHANGES.md §5 (requirement)
- Taxonomy: single / several dropdown, always visible in the Labels panel, also before labels exist; toggling it enters edit mode · `taxonomy/start`, `taxonomy/mode-changed` · behaviour in screens/taxonomy.py; recorded per §5
Each line: change · state ids to look at · backend or behaviour impact. Visual-only items say "visual".

- Brief seeds: no raw file view. Panel is "Seeds" with a count; numbered rows; editing turns the row into an input with a "was:" line and Save / Discard, other rows dimmed, Approve hidden; "Add seed" appends an input row · `brief/seeds`, `brief/editing`, `brief/adding` · **backend**: BACKEND_CHANGES.md §4 (explicit save and discard)
- Taxonomy: no raw YAML or markdown. "Labels" panel (mode, ■ label, description, built-in off_topic row) with Edit labels; "Prompt" panel renders the markdown with Edit prompt. Edit modes show inputs or a line-numbered editor, an EDITING badge, UNSAVED badge, Save and Discard; the other panel and Approve go inactive. Panels show "UPDATED BY ASSISTANT" after a tool write · `taxonomy/drafted`, `taxonomy/edit-labels`, `taxonomy/edit-labels-invalid`, `taxonomy/edit-prompt` · **backend**: §4 (drafts instead of autosave, agent writes while editing)
- Content column starts on the first row, level with the top of the rail (no blank row above the panels) · all screens at 100+ columns · visual
- Taxonomy: prominent "Approve taxonomy and prompt F2" button under the two editors (disabled until both a taxonomy and a prompt exist), confirm text "…and start labelling?"; the "Cannot approve" notices and their two states are removed · `taxonomy/drafted`, `taxonomy/confirm` · behaviour: `action_approve` in screens/taxonomy.py keeps its guards as silent no-ops; button `disabled` mirrors them
- Taxonomy chat starts with a context message (brief transcript, seeds with items won, search summary, instructions); agent replies with a summary and says it is ready · `taxonomy/start`, `taxonomy/ready`, `taxonomy/context-open` · **backend**: BACKEND_CHANGES.md §1
- Context refreshes when seeds or candidates change; an UPDATED line is appended and the agent replies briefly · `taxonomy/context-updated`, `taxonomy/context-updated-open` · **backend**: §1 (digest, staleness)
- Tool calls are one expandable line with arguments and result, in every chat · `brief/tool-open`, `taxonomy/tool-open` · **backend**: §2 (ChatPanel from RichLog to widgets)
- Search: top seeds panel has a similarity threshold selector; "items won" label removed · `search/top-filtered`, `search/threshold-open` · derived from candidates.jsonl, no new data
- Search: rerun confirmation when seeds unchanged; "Run search" with "Seeds changed, rerun needed" when changed · `search/confirm`, `search/seeds-changed` · **backend**: §3 (seeds digest stored with candidates.jsonl)
- Search: per-seed progress bar next to the button · `search/running` · **backend**: §3 (progress callback in build_candidates)
- Search: results dimmed until a search has run · `search/not-approved`, `search/never-run`, `search/running` · visual
- Search: bands as bars, "At or above" column and Total row removed, top seeds as ranked rows · `search/done` · visual
- Search: S3 cap warning reads "only the 10,000 highest-scoring hits are kept" · `search/capped` · **backend**: update text in screens/search.py
- Search: "Done…" paragraph removed · `search/done` · remove the message in screens/search.py
- Brief: Approve seeds button (disabled with no seeds), Save/Discard while editing, seed input only while editing, `#` column, centred placeholders, confirm text "…and start searching?" · `brief/empty`, `brief/seeds`, `brief/editing`, `brief/confirm` · small behaviour changes in screens/brief.py (BACKEND_CHANGES.md §3)
- Chat panels: send button, blank row above the input · all chat states · visual (send triggers the same submit as Enter)
- System settings, New project, Project settings: Save/Create disabled until valid, message to the right of the button · `system/nokey`, `new/local`, `pset/problem` · behaviour in screens/system.py, new_project.py, project_settings.py
- Models block: per-row "RECOMMENDED" / "DIFFERS FROM RECOMMENDED" markers, divider before classifier · `system/differs`, `pset/differs` · visual
- Recommended-models-changed modal reworked as now/new groups · `system/recommend` · visual
- Projects empty: centred message and New project button · `projects/empty` · visual (adds an on-screen button; `n` still works)
- Rail layout at 100+ columns; header at narrower widths · every state · visual
