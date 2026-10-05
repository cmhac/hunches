# 002 — System setup, projects and onboarding

Status: draft for implementation. Builds on `../001-initial-version/spec.md`, which is implemented (stages 1–9, `app.py`, `files.py`, …). Source: the author's notes (kept verbatim at the bottom), refined in review with the author. Read 001 first; where this spec changes 001 behaviour it says so under "Changes to 001".

## Principles

Same as 001 (minimal implementation, no abstraction/registry/plugin systems, plain files, the tool never runs git, check every Pydantic AI / Textual / keyring API against current docs before use, never call a real LLM/AWS/keyring in tests). Additional rules:

- Two scopes of state, kept separate:
  - **System** (per user, per machine, never in git): API keys (OS keyring), default models, saved S3 stores, the project list.
  - **Project** (`.hunches/`, tracked in git, unchanged): everything an analysis needs. A teammate's clone of a project must work without any system state beyond their own API keys.
- **A started analysis never changes models behind the user's back.** Models are copied into the project when it is created; system-level changes affect new projects only (see "Model pinning").
- Never store secrets in plain files written by hunches. Never print, log or put a key in a test snapshot.

## Terminology (rename)

`smart` → **assistant** (talks to the user: brief, taxonomy, tuning proposals). `cheap` → **classifier** (bulk labelling). The rename applies everywhere: config keys, UI text (e.g. "Asking the smart model…" → "Asking the assistant…"), README, specs' prose going forward. 001 prose is left as history.

## What changes, in one paragraph

First run (no system settings) opens **System setup**: pick a provider, enter an API key if none is available, accept the recommended models. After that, every run lands on **Projects** unless the current directory already is a project (then it opens directly, as today). **New project** asks for location, backend, corpus (or S3 store) and embedding model; models come from the system defaults. Existing projects are listed, health-checked, opened (the tool `chdir`s into them), edited or removed. **System settings** and **Project settings** screens edit everything later. Anywhere a directory is typed there is path auto-complete and a **Browse** picker.

## System state

### Location and format

One file `system.json` in the user config directory: `platformdirs.user_config_dir("hunches")` (`~/.config/hunches/` on Linux, `~/Library/Application Support/hunches/` on macOS, `%APPDATA%` on Windows). Env var `HUNCHES_HOME` overrides the directory (used by tests, also handy for users). Add `platformdirs` as an explicit dependency. JSON validated by a Pydantic model, same style as `State`. No secrets in this file.

```json
{
  "version": 1,
  "provider": "anthropic",
  "assistant_model": "anthropic:claude-sonnet-5-5",
  "assistant_thinking": "medium",
  "classifier_model": "anthropic:claude-haiku-4-5",
  "recommendation_seen": 1,
  "s3_stores": [
    {"name": "wapo-docs", "bucket": "b", "index": "i", "region": null, "embedding_model": "openai:text-embedding-3-small"}
  ],
  "projects": [
    {"path": "/home/me/work/layoffs", "last_opened": "2026-10-03T14:00:00Z"}
  ]
}
```

- A missing file means first run. Unknown future `version` → refuse to overwrite and tell the user (don't corrupt a newer tool's file). Writes are atomic (write temp file, `os.replace`).
- `projects` stores only `path` (absolute) and `last_opened`. Name, backend, and store are read live from each project's `config.toml` so they cannot go stale.
- Module `src/hunches/system.py` (system file I/O, project/store list helpers, recommendations table); `src/hunches/keys.py` (keyring). Plain functions, like `files.py`.

### Recommended models (hard-coded)

In code, a plain dict plus an integer `RECOMMENDED_REVISION`, bumped by whoever changes the table:

| provider | assistant | thinking | classifier |
|---|---|---|---|
| anthropic | `anthropic:claude-sonnet-5-5` | `medium` | `anthropic:claude-haiku-4-5` |
| openai | `openai:gpt-6-sol` | provider default (see open items) | `openai:gpt-6-luna` |

Verified 2026-10-03: all four IDs are in pydantic-ai's `KnownModelName`; `claude-sonnet-5-5` is a documented pydantic-ai model name; `genai-prices` has prices for `claude-sonnet-5-5`, `claude-haiku-4-5`, `gpt-6-sol`, `gpt-6-luna` (so cost is never `?` for the defaults). The author's original note said "GPT 5.6 Sol/Luna"; OpenAI shipped GPT-6 Sol/Luna on 2026-09-22 (50% cheaper than 5.6), and the author chose `gpt-6-sol`/`gpt-6-luna` in review. The implementer must re-verify every ID against the provider docs and `genai-prices` when implementing (`calc_price` must return a price for all four, with `provider_id` as in `cost.py`) and stop and report if one does not resolve.

"Medium reasoning" for Anthropic: pydantic-ai 2.53 has a cross-provider `thinking` model setting (`ModelSettings.thinking`, values `True|False|'minimal'|'low'|'medium'|'high'|'xhigh'`; also `anthropic_thinking`, `anthropic_effort`). Use `model_settings={'thinking': 'medium'}` on the assistant `Agent`. Confirm in the docs that Sonnet 5.5 accepts it and what it maps to. Thinking applies to the assistant only; the classifier runs with no thinking setting.

### API keys

- Only Anthropic (`ANTHROPIC_API_KEY`) and OpenAI (`OPENAI_API_KEY`) are managed. Other providers still work if the user types a `provider:model` string and sets their own env var; hunches just doesn't manage those keys.
- **Resolution order:** process environment (including a `.env` loaded by `load_dotenv()`) > keyring > missing. At startup, `keys.load_into_env()` copies keyring values into `os.environ` for any managed var that is not already set, so every pydantic-ai provider/embedder picks them up without per-call plumbing. (Consequence to document: the key is then visible to child processes of hunches. It never touches disk beyond the keyring.)
- **Storage:** `keyring.set_password("hunches", "ANTHROPIC_API_KEY", key)` (service `hunches`, username = env var name). The entry UI is a masked `Input(password=True)`; the value is never echoed, logged, or kept after saving.
- **Status** per key: `env` (and which: shell vs `.env` isn't distinguished), `keyring`, or `missing`. Shown with a word, never colour alone.
- **No keyring backend** (headless Linux, containers, CI): keyring raises `keyring.errors.KeyringError` subclasses (`NoKeyringError`) or selects the `fail` backend; verify the exact behaviour in the keyring docs. Handle it by catching `KeyringError` on every call, showing "No system keyring available: set ANTHROPIC_API_KEY / OPENAI_API_KEY in the environment or a git-ignored .env", and not offering the Save button. Never fall back to writing keys to a file.
- A **Remove key** action calls `delete_password` (raises when absent; treat as already removed). It never touches environment variables; if the var is still set, status stays `env`.
- A key is **required** for: the assistant's provider, the classifier's provider, and the project's embedding model's provider (`openai:` → `OPENAI_API_KEY`; `sentence-transformers:` → none). First-run setup requires at least one of Anthropic/OpenAI. Keys are not validated with a network call; a bad key shows up as the first call's error, which the chat panel and stage screens already surface.

### Model pinning

- **New project:** `assistant_model`, `assistant_thinking`, `classifier_model` are copied from system settings into `.hunches/config.toml`. These are the only models that project uses, forever, unless the user edits them in **Project settings**.
- **System changes never reach existing projects.** Not at update, not on settings edit, not on "accept new recommendation".
- **Recommendation updates** (`RECOMMENDED_REVISION` > `recommendation_seen` at startup, after system setup exists): if the user's current system models already equal the new recommendation for their provider, bump `recommendation_seen` silently. Otherwise show a modal "Recommended models changed" with old → new for each of assistant/classifier, and two buttons: **Use new** (updates system defaults only) and **Keep mine**. Both set `recommendation_seen`, so there is no nagging on every start; **System settings** always shows when the stored models differ from the current recommendation and offers "Reset to recommended". Text on both: "Existing projects keep their models."
- **Project settings** shows a `RECOMMENDED` / `DIFFERS` marker comparing the project's pinned models to the current recommendation, informational only.
- **Changing a project's models in Project settings** (explicit user action) shows a confirmation that states consequences: (a) classifier changed: the classifier cache is keyed on model so nothing stale is reused, dev/test/threshold numbers are recomputed with new cost, test result becomes STALE, and `results.jsonl` (if present) was produced by the old model and is not rewritten; (b) assistant changed: only future chat turns. Do not delete any file.
- **Cache key** (requirement, confirmed against current code): `cost.cache_key(model, system_prompt, text)` already hashes the model string, the full system prompt (prompt.md plus labels and mode rule) and the text, so a changed classifier never reuses another model's cached labels. Keep that property: if classifier model settings (e.g. thinking) are ever added, they must be part of the key. Add a test pinning this.
- **Test-result staleness** (change to 001): `FinalScreen`'s stale check hashes `prompt.md` only (`final.prompt_hash`). It must hash `classifier_model` too, so a model change marks the held-out result STALE, with banner text "prompt.md or classifier model changed…".
- Each result row does not record its model (001 format unchanged); `cost.json` already breaks cost down per model name, which is the audit trail.

## Config changes (project)

`.hunches/config.toml` keeps its current fields except:

| 001 | 002 |
|---|---|
| `smart_model` | `assistant_model` |
| `cheap_model` | `classifier_model` |
| — | `assistant_thinking` (string or omitted; omitted = no thinking setting) |
| — | `s3_region` (optional; omitted = boto3's default resolution) |

- `files.read_config` (via `Config`) accepts the old keys `smart_model`/`cheap_model` (migration on read via a `model_validator(mode="before")`); `write_config` only writes new names. A project written by 001 and never saved again keeps working.
- An old project without `assistant_thinking` gets no thinking (preserves its behaviour); only new projects get the recommendation's thinking value.
- Defaults in `Config` for the models are removed from `files.Config` (system settings is now the default source). Tests construct configs explicitly. Done in task 06: `assistant_model` and `classifier_model` are required fields of `Config` (no defaults); test fixtures name their models. `assistant_thinking` is typed as pydantic-ai's `ThinkingEffort` (`minimal|low|medium|high|xhigh`), so a bad value is rejected on read; the helper is `files.thinking_settings(config)`.
- Paths: `corpus_dir` is stored **relative to the project directory when the corpus is inside it, otherwise absolute**, so tracked configs stay portable. All path use stays relative to cwd (the project dir) because opening a project `chdir`s into it.
- `config.toml` remains self-contained: bucket/index/region/embedding model are copied in, never referenced by store name.
- Everywhere models are read (`brief.py`, `taxonomy.py`, `tune.py`, `gold.py`, `final.py`, `run.py`, `threshold.py`) the field names change. The assistant `Agent` sites (`brief.py`, `taxonomy.py`, `tune.py`) pass `model_settings={'thinking': ...}` when `assistant_thinking` is set; put that in one small helper in `files.py` or `system.py`, not a framework.

## Model picker

Users pick models from a list instead of typing exact strings; used by System settings, and Project settings (and the S3 embedding model field).

- **Source of the list: pydantic-ai, not `genai-prices`.** `pydantic_ai.models.KnownModelName` (a type alias; its string members via `typing.get_args(KnownModelName.__value__)`) holds the exact API strings, e.g. `anthropic:claude-sonnet-5-5`, `openai:gpt-6-sol`. **The picker lists the models of every provider that has an API key** (env or keyring; `keys.providers()`): only OpenAI key → OpenAI models; only Anthropic → Anthropic; both → both; neither → no models, only **Other…** and a note pointing to System settings. It takes no provider argument; the System settings provider Select only chooses which recommendation gets filled in. Embedding pickers follow the same rule (local models such as Sentence Transformers need no key, so with no key they are reached through **Other…**). The list is built when the picker opens. Embedding models likewise from `pydantic_ai.embeddings.KnownEmbeddingModelName`. Check in the pydantic-ai docs/source that these are public, and how they behave across versions (the list ships with the installed pydantic-ai, so it only knows models released before that version; hence "Other…").
- **`genai-prices` only annotates rows.** `genai_prices.data_snapshot.get_snapshot().providers[...].models` gives `name`, `description`, `context_window`, `deprecated`, prices. Do **not** use its `id`s as the list: they are price-matching rules, not API strings. (Verified 2026-10-03: the entry `claude-sonnet-5` matches by prefix `claude-sonnet-5*`, so it also covers `claude-sonnet-5-5`; the snapshot has no separate `claude-sonnet-5-5` id; it also contains image/TTS/embedding models and older ids.) Annotation lookup is `calc_price(...)`-style matching by the real model string (as `cost.py` does), not by comparing ids.
- **Prices are always visible (cost transparency).** Format: `$2.00 in / $10.00 out per 1M tokens` (embedding models: `$0.02 in per 1M tokens`). Rules:
  - Source: the matched `genai-prices` model's `get_prices(now)` (`ModelPrice`: `input_mtok`, `output_mtok`; prices are time-dependent, so pass the current timestamp). Verified 2026-10-03: `claude-sonnet-5` entry $2/$10, `claude-haiku-4-5` $1/$5, `gpt-6-sol` $2/$10 (`+tiers`), `gpt-6-luna` $0.10/$0.50 (`+tiers`), `text-embedding-3-small` $0.02 in. Re-check against the installed snapshot at implementation time.
  - Tiered prices (the library marks `+tiers`): the tier is a long-prompt surcharge. Verified 2026-10-03 for `gpt-6-sol` (input $2 → $4, output $10 → $15) and `gpt-6-luna` (input $0.10 → $0.20, output $0.50 → $0.75) above 272,000 input tokens in one request (`TieredPrices(base, tiers=[Tier(start, price)])`; `price_comments` cites OpenAI's model page). Show the base price plus a plain-words note with the threshold read from the tier data, e.g. `$2.00 in / $10.00 out per 1M tokens (higher above 272K prompt tokens)`. Never a bare `+tiers`. If a model has several tiers or tiers on only one side, say `(higher above <first start> prompt tokens)` using the lowest `start`. Hunches' calls (one short item plus the prompt) stay far below such thresholds, so the base price is what users pay in practice; don't add tier maths to cost tracking (that already comes from `genai-prices` via pydantic-ai).
  - Unknown price: `no price: cost will show ?` in the warning style (001 rule: never `$0`).
  - Prices appear **in the picker rows, next to the selected value afterwards** (System settings, Project settings, the read-only models summary on New project, both columns of the recommendation modal's old → new, and the Projects/Settings screens wherever a model string is shown). A model shown anywhere in a settings/setup screen has its price beside it.
  - Footnote on those screens: "Prices from genai-prices as of <snapshot date>; the header shows actual spend." The snapshot date comes from the library's snapshot timestamp.
  - No projected-total estimate here (it would need token assumptions); stage 8's estimate from sample usage stays the source for run cost.
  - One helper `price_label(model_string) -> str` (plain function) used everywhere so the wording lives in one place; unit-test it against hand-written expectations for a known, a tiered, and an unknown model.
- Row also shows: model string, `deprecated` badge when flagged, and a `recommended` marker.
- **Other…** accepts any `provider:model` string. Anything not in the list gets a visible `not in known list` note (warning, not an error: newer models or other providers may be valid).
- Chat-only filtering: hide obviously unsuitable entries only if `KnownModelName` includes any (check; do not hand-maintain a deny list). Checked 2026-10-03 (task 04): `KnownModelName` does include non-chat entries (e.g. `openai:gpt-audio-mini`, `openai:computer-use-preview`, `gateway/...`) but carries no metadata to tell them apart, so none are hidden; **Other…** and the visible list cover the rest. Type-to-filter was not implemented (the provider-filtered list is short).
- The list is a Textual `Select` or a small modal with a `ListView`/`OptionList`, with type-to-filter if cheap; the implementer picks the simplest that works at 80×24.
- Tests use a hand-built list/monkeypatched source; assert recommended entries are present in the real `KnownModelName` (this doubles as the "re-verify the four recommended IDs" check).

## Path input and browser

Used by: project location, local corpus dir, relocating a missing project, and anywhere else a local path is typed.

**`PathInput`** (a Textual `Input` with a custom `Suggester`; `Input(suggester=...)`, subclass `textual.suggester.Suggester`, `async get_suggestion(value)`; check current signatures):
- Completes the last path segment from directory entries of its parent: directories only, sorted, first match wins. Expands `~`; relative paths resolve against cwd; a completed directory gets a trailing `/`. Hidden entries (leading `.`) suggested only when the typed segment starts with `.`.
- `use_cache=False` (the filesystem changes); `case_sensitive=True`. `PermissionError`/`FileNotFoundError` → no suggestion. Listing capped (e.g. 2,000 entries) so a huge directory can't freeze the UI.
- Accepting: Textual accepts a suggestion with the right arrow at end of input (documented). Also bind `tab` to accept when a suggestion exists, if Textual allows; if it does not, document right-arrow in the placeholder/hint line ("→ completes").
- No bespoke fuzzy search, no history.

**`PathPicker`** (`ModalScreen[Path | None]`):
- A `DirectoryTree` subclass whose `filter_paths` keeps only directories (documented Textual pattern; hidden dirs excluded), rooted at a start directory (the input's current value if it is a directory, else cwd).
- Top row: a `PathInput` showing the current root (Enter re-roots the tree), an **Up** button (re-root at parent), **Select** (returns the highlighted directory; if none is highlighted, the root) and **Cancel** (returns `None`, Esc too).
- `DirectorySelected` (Enter on a directory) expands it; selecting is explicit via **Select**, so browsing by keyboard never picks by accident.
- Each input that uses it has a **Browse** button (`b` key hint in the label) that opens the picker and writes the result back into the input.
- Must work at 80×24 (Rule from AGENTS.md).

## Screens

All screens follow `AGENTS.md` "TUI look": `StatusHeader` first, `panel(...)`, words with colour, 80×24. System/projects screens are not stages: `app.stage == 0`, header shows `Setup`/`Projects`/`Settings` as the stage name. Keys are proposals; the implementer checks each against the screen's existing `BINDINGS` and Textual's defaults (note `ctrl+p` is Textual's command palette).

### Startup flow

```
main(): load_dotenv() → keys.load_into_env()
on_mount:
  system file missing                       → SystemSettingsScreen (first run) → then continue below
  recommendation changed                    → RecommendationModal → continue
  cwd has .hunches/config.toml              → register in system projects if absent; open it (stage = first incomplete)
  else                                      → ProjectsScreen
```

Opening a project from anywhere is `HunchesApp.open_project(path)`: confirm if a worker is running (e.g. a stage-8 run: "A run is in progress; stop it and switch?"), cancel workers, `os.chdir(path)`, update `last_opened`, reset the screen stack to the project's first incomplete stage (`stage_shown = False` then `goto_stage`). This is the **only** place that changes cwd; all of `files.root()`, `cost.json`, gold sampling seeds (`Path.cwd().name`) stay cwd-relative. A project that cannot be opened (dir/config missing) produces an error message, never a traceback.

Always-available keys from any screen (not while a modal is open or an Input has focus, same as `n`/`p`): **Projects** and **Settings**. Proposed: `f9` Projects, `f10` System settings (verify F-keys against terminals/tmux; fall back to `ctrl+`-chords other than `ctrl+p`). Footer lists them. Existing `q`, `n`, `p` unchanged.

Implementation notes (task 09): chosen keys are `f4` Projects and `f5` System settings (next to `f2` approve and `f3` project settings; `f10` is taken by the menu bar in common terminals such as GNOME Terminal and `f9` by some multiplexers). They are app-level bindings, so they also work with an Input focused (unlike `n`/`p`); they are ignored on a modal, on the screen they open, and (Projects) before first-run setup has written `system.json`. They have not been tried in every terminal/multiplexer; a human should check. `n`/`p` (goto stage) are hidden and disabled via `check_action` when `stage == 0` or Projects is on top, which removes the footer clash with Projects' own `n` New. Startup: first run shows System settings, then continues; an unchanged-models recommendation bump is silent (`recommended_changed` is called exactly once); a `.hunches/` in cwd is registered with `system.add_project` and opened with `open_project`, so a cwd project that fails the health check (e.g. `MISSING CORPUS`) now shows an error and the Projects screen instead of opening as in 001.

### System setup / System settings (`SystemSettingsScreen`)

One screen serves first run and later edits (first run = file missing: title "Welcome — set up hunches", no Cancel, Save writes the file and continues). Fields:
- **Provider** (Select: Anthropic, OpenAI): picks which recommended pair is offered. Preselect the provider that has a key available; if both do, Anthropic.
- **API keys** panel: a row each for Anthropic and OpenAI: status word (`ENV`/`KEYRING`/`MISSING`), masked input, **Save** (to keyring) and **Remove**. Disabled with the no-keyring message when no backend. Save is blocked until at least one managed key is available.
- **Models** panel: assistant model, assistant thinking, classifier model; prefilled from the recommendation for the chosen provider; each model is chosen from a **list** (see "Model picker") with an **Other…** entry for typing any `provider:model`; a `DIFFERS from recommended` badge when changed; **Reset to recommended**. Changing the provider re-fills fields only if the user hasn't edited them (or asks first). Warn (not block) when `genai-prices` has no price for an entered model, since cost would show `?` — use the same unknown-price rule as 001.
- **Saved S3 stores** panel: list with delete and edit-name. Stores are created from **New project** (below); this panel only manages them. Deleting a store never affects projects (their config is self-contained).
- Notice: "Changes here apply to new projects. Existing projects keep their models."
- Implementation notes (task 05): assistant thinking offers `provider default` (stored as `null`) plus the `ThinkingEffort` values (`minimal`…`xhigh`), the same set `files.Config.assistant_thinking` accepts. Store delete/rename take effect immediately (they are not part of Save); `system.rename_store` refuses a name already in use. Save keeps `projects`, `s3_stores` and `recommendation_seen` of an existing file (only the recommendation modal changes `recommendation_seen`; first-run Save sets it to the current revision). The modal is `RecommendationModal` in `screens/system.py`.

### Projects (`ProjectsScreen`)

DataTable, one row per registered project, most recently opened first. Columns: Name (dir name), Backend (`local`/`s3`), Where (corpus path, or `bucket/index`), Status, Opened.

**Status** (computed on screen mount and on `r`, no network):
| status | condition |
|---|---|
| `OK` | project dir exists, `.hunches/config.toml` parses |
| `MISSING DIR` | project dir does not exist |
| `NO CONFIG` | dir exists but `.hunches/config.toml` is missing or invalid |
| `MISSING CORPUS` | backend local and corpus dir lacks `vectors.npy`/`items.jsonl`/`meta.json` (names which) |
| `S3` suffix | S3 projects can't be verified offline; show `OK` plus "(s3 not checked)" |

A banner at the top counts problems ("2 projects need attention") and rows are marked with a word, not just colour.

Keys: `enter` open; `n` new project; `e` edit (opens the project then Project settings, so settings code stays cwd-relative); `x` remove/delete; `l` locate (for `MISSING DIR`/`MISSING CORPUS`: PathPicker, then updates the registry path or the project's `corpus_dir`); `r` refresh; `esc` back to the current project if one is open. Unhealthy projects cannot be opened but can be located, removed or deleted.

**Remove / delete** (modal with two distinct actions, default focus on the safe one):
1. **Remove from list** — deletes the registry entry only. Files untouched.
2. **Delete project files** — deletes the project's `.hunches/` folder after the user types the project name. Never deletes the corpus directory, never touches S3 (hunches is read-only against both), never touches anything outside `<project>/.hunches/`. The message tells the user hunches doesn't run git, so committed history is unaffected. Refuse if the dir is the current project with a running worker.

Empty state (no projects): "No projects yet. Press n to create one."

Implementation notes (task 07): `system.project_status(path)` computes the status (so `app.open_project` can refuse an unhealthy project without importing the screen); S3 projects show `OK (s3 not checked)`; the Status column holds the word and the detail (which corpus files are missing) goes into the error text when opening fails. `files.read_config`/`write_config` take an optional `project` path so `l` can rewrite another project's `corpus_dir` without changing cwd. "Delete project files" leaves the registry entry in place (the row then shows `NO CONFIG`; use Remove to drop it). `esc` pops back to the open project, so the Projects screen must be pushed over a stage screen (task 09). The header shows a non-stage screen's name from its `stage_name` attribute. `n` (new project) and `e` (edit) are added by tasks 06 and 08, which own the screens they open.

### New project (`NewProjectScreen`, replaces 001's `SetupScreen`)

A form (not a wizard) on one screen:
1. **Location** (`PathInput` + Browse). Default: current directory. Options "Use current directory" (default) and "Another folder"; a path that doesn't exist is created (`mkdir -p`) after the user saves, if its parent exists; refuse when `.hunches/config.toml` already exists there ("already a project — open it instead", with a button that opens it). Warn if the folder is not empty? No, projects commonly live in existing folders.
2. **Backend** (Select: Local / S3 Vectors).
3. **Local:** corpus directory (`PathInput` + Browse). On change, validate: all three files exist (list the missing ones), `meta.json` parses and has `embedding_model`, `len(items) == N` is checked at search time as today (don't load the array here). The embedding model is **read from `meta.json` and shown read-only** ("from meta.json"); the user doesn't type it. Corpus path stored relative to the project dir when inside it.
4. **S3:** a Select of saved stores plus "New store…"; picking a saved store prefills bucket, index, region and embedding model (editable). "New store" asks bucket, index, optional region, embedding model (picked from `KnownEmbeddingModelName` via the model picker, with Other… for any string `pydantic_ai.Embedder` supports, e.g. `openai:text-embedding-3-small`). Checkbox **Save this store for other projects** (default on, name defaults to `bucket/index`). Optional **Check store** button: `boto3.client("s3vectors").get_index(...)` and show `dimension` and `distanceMetric`, warn when the metric isn't cosine (this also gives a real-data way to resolve 001's open `similarity = 1 - distance` item). Network call only on that button; stubbed in tests. Check the real parameter names in the boto3 `s3vectors` reference (existing `search.py` uses `vectorBucketName`/`indexName`; the index/bucket argument names for `get_index` must be verified, don't copy them from a summary).
5. **Models** shown read-only from system settings (assistant, thinking, classifier, with a note "pinned for this project; change later in Project settings"). If a required key is missing for any of assistant/classifier/embedding providers: a visible blocking message and a button that opens System settings, then returns here keeping the form's values.
6. **Create:** write `.hunches/config.toml` (self-contained, all fields), add the S3 store if requested, register the project in the system file, `open_project(location)` → stage 1.

Required-field errors use the same inline error pattern as 001's `SetupScreen` ("Required: …").

Implementation notes (task 06): location is one `PathInput` prefilled with the current directory plus Browse (no separate "use current directory"/"another folder" radio: the prefill is the default and typing a path is "another folder"). The Browse button reads `Browse` without a `b` key hint, because a focused Input swallows `b`. `NewProjectScreen` itself registers the project (`system.add_project`) and calls `app.open_project`, so every caller (Projects `n`, first-run startup in task 09) just pushes the screen; the "already a project" button calls the same open. S3 saved-store picking prefills the fields and turns "Save this store" off (it is already saved); a new store is saved under the name `bucket/index` (same name replaces). The embedding model of an S3 project is chosen with the model picker (Pick button; the picker's provider is that of the current value, `openai` at first, and Other… reaches any string). Check store runs `get_index` in a thread worker and shows `dimension` and `distanceMetric` (a non-cosine metric gets a WARNING). The warning, Create and error line sit outside the scroll area so they stay visible at 80×24. A required key is missing when `keys.status` is `missing` for the provider of the assistant, the classifier or the embedding model; Create is refused with `BLOCKED: …` and the System settings button pushes `SystemSettingsScreen` over the form (values stay) and re-checks on return. `search.py` now passes `s3_region` to `boto3.client("s3vectors", region_name=…)`; before this task nothing read that field.

### Project settings (`ProjectSettingsScreen`)

Opened from the current project (key `s`/menu proposal: the implementer picks a free key; footer shows it) or from Projects `e`. Edits `.hunches/config.toml` fields: backend data (local corpus dir with Browse, or bucket/index/region, with saved-store picker), embedding model (read-only for local, from `meta.json`; editable for S3), assistant model + thinking, classifier model, plus `DIFFERS`/`RECOMMENDED` markers (see "Model pinning"). Save runs the consequence confirmation for model changes, and for embedding model/backend/corpus changes: "Candidates were generated from the old corpus/model (`candidates.jsonl`); re-run Search (stage 2). Gold labels refer to ids." Nothing is deleted automatically. `target_metric`/`target_score` stay in the Tuning screen.

Implementation notes (task 08): key `f3` (app-level, shown in the footer; works in every stage screen even with an Input focused; ignored on modals, on Projects without an open project and while the screen is already open). Projects `e` opens the project (cwd moves into it) then pushes this screen. Editable: backend, local corpus (`PathInput` + `Browse` button, no key hint), S3 bucket/index/region (saved-store picker prefills and sets the embedding model; `Check store` as in New project), S3 embedding model (picker), assistant model, thinking (`provider default` or `ThinkingEffort`), classifier model; every model shows its `price_label` and a `RECOMMENDED` marker (equals the current recommendation for that role, any provider) or `DIFFERS`. The embedding model of a local corpus is read from `meta.json` and shown read-only; a corpus problem blocks Save (`Corpus: …`); S3 needs bucket, index and an embedding model. Switching backend writes only the active backend's fields (the other's are set to `None`; no file is touched). Save with no change closes without writing; otherwise `ConfirmScreen` lists the consequences that apply (corpus/embedding/backend/bucket/index, assistant or thinking, classifier) and **Approve** writes `config.toml` (other fields such as `target_metric` are kept) and rebuilds the stage screen underneath so it reads the new config; **Cancel** keeps the form and the file. Not done: no API-key check for a newly chosen provider (the first call surfaces it, as in 001).

## Dependencies

Add `keyring` (current 25.7.0, Python ≥ 3.9) and `platformdirs` to `dependencies`. `uv add` and commit the lockfile. No `textual-fspicker` or other picker library: Textual's `DirectoryTree` + `Suggester` are enough.

## Changes to 001 (explicit list)

1. Rename `smart_model`/`cheap_model` → `assistant_model`/`classifier_model` (with read-side migration); add `assistant_thinking`, `s3_region`.
2. `SetupScreen` is removed; `HunchesApp.on_mount` follows the new startup flow. 001's "run from inside the project directory" still works (auto-opens, auto-registers); running elsewhere now shows Projects.
3. Embedding model for local projects comes from `meta.json` instead of being typed.
4. `main()` calls `keys.load_into_env()` after `load_dotenv()`.
5. `final.prompt_hash` includes the classifier model.
6. README: install, first run, keys, projects, "what to commit" (system state is outside the repo). `AGENTS.md` layout updated with `system.py`, `keys.py`, `screens/paths.py`, `screens/system.py`, `screens/projects.py`, `screens/new_project.py`, `screens/project_settings.py`.
7. `examples/sample/.hunches/config.toml` uses the new key names.

## Testing

- **Never touch the real system:** a fixture sets `HUNCHES_HOME` to `tmp_path` and installs an in-memory keyring backend via `keyring.set_keyring(...)` (a `KeyringBackend` subclass storing in a dict), restoring afterwards. A second fixture installs the `fail` backend to cover the no-keyring path. Tests must fail loudly if the real keyring or real `~/.config` is reached (e.g. autouse fixture that sets `HUNCHES_HOME` and the in-memory backend for every test).
- Existing tests that build `files.Config(..., cheap_model="test")` are updated to the new names. Add one migration test: a config written with the old keys loads into the new fields.
- `system.py`: round-trip, unknown newer `version` refused, atomic write, project add/remove/dedupe, store add/delete, recommendation-changed logic (silent bump vs prompt, "Keep mine" doesn't change models, "Use new" does, neither touches any project's `config.toml`).
- `keys.py`: resolution order env > keyring > missing; `load_into_env` doesn't override an existing env var; no-keyring handled; delete of absent key is not an error; a key never appears in any rendered text (assert on a sentinel value).
- Models: assistant `Agent` gets `thinking` model settings when set (`TestModel`/`FunctionModel` capturing settings); classifier cache key differs per model (hand-written expected values); stale flag flips when `classifier_model` changes.
- `PathInput` suggester unit tests on a `tmp_path` tree: `~`, relative, trailing `/`, hidden rule, unreadable dir, no match, file entries excluded. `PathPicker` Pilot test: browse, Up, Select, Cancel.
- Pilot smoke test per new screen (system settings first-run and edit, projects list with an OK/MISSING DIR/MISSING CORPUS fixture, new project local and S3 with a stubbed `get_index`, project settings). Open-project test asserts `os.getcwd()` changed and the right stage showed. Delete test asserts only `<project>/.hunches/` is removed and the corpus dir and registry behave as specified.
- Startup-flow test matrix: no system file; system file + cwd is a project; system file + cwd is not a project; recommendation changed.
- Metrics/expected values written by hand in the test, per AGENTS.md.

## Out of scope

- Storing AWS credentials/profiles (boto3's normal credential chain only); creating/embedding corpora; non-Anthropic/OpenAI key management; encrypting `system.json` (it holds no secrets); syncing system state between machines; project templates; a CLI beyond `hunches` (no subcommands/flags in this version); validating API keys over the network; multi-user concerns.

## Open items for the implementer to flag, not guess

- **OpenAI assistant reasoning level.** The author specified "Claude Sonnet 5.5 medium reasoning" for Anthropic but only model names for OpenAI. Default: no explicit thinking setting for OpenAI (provider default), recorded as `null` in the table above. Check the pydantic-ai/OpenAI docs for the real parameter (`openai_reasoning_effort`, unified `thinking`) and flag it to the author if `medium` is the sensible parity choice.
- **Exact keyring behaviour on headless systems** (which exception, which backend) must be taken from the keyring docs, not from this spec.
- **F-key bindings** may be swallowed by terminals/multiplexers; confirm and pick alternatives.
- **GPT-6 IDs and prices** must be re-verified at implementation time (the model landscape moves quickly). The author confirmed `gpt-6-sol`/`gpt-6-luna` on 2026-10-03; `genai-prices` also lists `gpt-6.1-sol`, which the author did not choose.
- **S3 `get_index` argument names** (see New project). Resolved in task 06 against botocore 1.43.108 (the installed boto3's `s3vectors` service model): `get_index(vectorBucketName=…, indexName=…)` (or `indexArn`), response `index` with `dimension` (integer) and `distanceMetric` (`euclidean` | `cosine`). Re-check against the AWS API reference if boto3 is upgraded.
- **Needs a human:** real API keys, a real keyring, AWS credentials and an S3 Vectors index for the manual end-to-end check. Agents cannot fake these.

---

## Original notes (verbatim, from the author)

<!-- User input - this is a starting point for the spec, not the spec itself. a full technical spec must be generated based on this initial description -->

We need a first-time system-wide setup option, and the ability to modify those settings after. The initial setup screen we have is a bit confusing, and shouldn't be needed every time. when setting up a new project, we should need to set up the backend and corpus and embedding model, but the llms should be pre-configured based on the system-wide settings. We should require the user to configure an api key if one is not available in these system-wide settings, either for anthropic or openai. we should use the keyring python library to store these securely. then we should hard-code the smart and cheap models. also rename "smart" to "assistant" and "cheap" to "classifier." we should be opinionated - hard-coding the recommended models for each. for anthropic, use claude sonnet 5.5 medium reasoning for assistant and claude haiku 4.5 for classifier. For openai, use gpt 5.6 sol for assistant and gpt 5.6 luna for classifier. we should have the ability to modify these settings later through a dedicated system-wide settings interface. also, on subsequent updates to the hunches tool, if the recommended models change, we should prompt the user to change them if they want to accept the new recommendations but not force update them.

For the corpus dir selector, we should have some sort of auto completion based on the current directory - suggesting existing directories as the user types, and allowing easy navigation through the file system.

Also, for s3 vectors configurations, we should store the s3 bucket and index variables system-level, so users can reuse the same vector store for multiple projects. we should also track all of the projects created in this system-wide setup, allowing users to easily manage and switch between projects, for both local and s3-based vector stores. should check the local ones are actually present and alert users to any missing directories. option to manage existing projects should be provided, allowing users to delete or update project configurations as needed. when a user selects an existing project to open, if it is a local directory should cd the tool into that directory and update the current project context accordingly.

Best way to do this is probably to have a "new or existing project" interface, where users can either create a new project by setting up the backend, corpus, and embedding model, or select an existing project to open and manage. Like if there's an existing s3 project in some folder, we'll want to cd into it if the user wants to work on it, and similarly for local projects, we should navigate to the appropriate directory and update the current project context accordingly, but also for s3 if we want to reuse the existing store for a new project we should let users create a new one while still being able to link it to the existing s3 store. when a user uses the tool to create a new project, we should prompt them to create it in the current directory or in another folder on the comptuer, with the option to browse and select the desired location. like with the local path descfribed above, we should have a similar browsing/auto-pathcompletion for any time the user is navigating the local file system. we should cache which embedding model the user selects for each project, so that it can be reused and easily modified later if needed.

So in summation, we need a first-time system-wide setup interface, and a project setup interface, with the ability to modify both later. Additionally, we need efficient management for existing projects, both local and s3-based, with easy navigation, updating, and deletion options. We also need a user-friendly file system navigation experience, with auto-completion and browsing capabilities for selecting directories.
