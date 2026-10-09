# hunches

An interactive terminal toolkit for content analysis over an already-embedded corpus:
seed phrases, semantic search, candidates, an LLM classifier validated against a hand-labelled
gold set, and classified output. An assistant model talks to you; a classifier model does the bulk work.

## Install

```
uv tool install hunches          # or: pipx install hunches
uv tool install "hunches[s3]"    # adds boto3 for the S3 Vectors backend
uv tool install "hunches[pg]"    # adds psycopg for the pgvector (PostgreSQL) backend
uv tool install "hunches[rds]"   # pg plus boto3, for RDS / Aurora IAM database authentication
uv tool install "hunches[local]" # adds Sentence Transformers for local query embeddings (Python < 3.14)
```

## First run

```
hunches
```

The first run opens **System settings**: pick a provider (Anthropic or OpenAI), supply an API key if none is
available, and accept the recommended assistant and classifier models (each chosen from a list, or any
`provider:model` via Other...). Prices are shown beside every model. After that every run lands on **Projects**,
unless the current directory already contains `.hunches/config.toml`: then that project is registered and opened
directly, resuming at its first incomplete stage.

## API keys

Resolution order: process environment (including a git-ignored `.env`) first, then the OS keyring. Only
`ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are managed; System settings shows each as `ENV`, `KEYRING` or `MISSING`
and can save or remove the keyring entry. At startup keyring keys are copied into the process environment, so child
processes of hunches can see them. Keys are never written to a file by hunches and never committed. On systems
without a keyring backend (headless Linux, containers, CI) the Save button is not offered: set the variables in the
environment or a `.env` instead. Other providers work if you type their `provider:model` string and set their
env var yourself.

## Projects

**Projects** lists every project hunches knows about with a health status (`OK`, `MISSING DIR`, `NO CONFIG`,
`MISSING CORPUS`). `enter` opens one (hunches changes into its directory), `n` creates a new one, `e` edits its
settings, `x` removes it from the list or deletes its `.hunches/` folder (never the corpus), `l` locates a moved
project or corpus, `r` refreshes, `esc` goes back to the open project. **New project** asks for the location,
backend (local corpus, S3 Vectors or PostgreSQL with pgvector), corpus and embedding model; the assistant and classifier models are copied
from the system defaults into the project, and later system changes never alter an existing project. **Project
settings** edits them afterwards.

## Layout and keys

From 100 columns the left side is a rail with the stage list, project, models and cost; below that it is a one-row
header. Panels have a title row; the focused panel has a bar on its left. Every action has a button that shows its
key, and the footer lists the keys of the current screen (it leaves out the ones the rail already shows).
Everything works at 80x24.

| Key | Action |
|-----|--------|
| `f2` | Approve / finish the current stage (shown in the footer) |
| `f3` | Project settings of the open project |
| `f4` | Projects |
| `f5` | System settings |
| `f6` / `f7` | Undo / redo the last change to the seeds, labels or prompt being edited |
| `f8` | History: every change to seeds, labels and prompt, and every approval |
| `f9` | Redo plan: what is out of date and what redoing it costs |
| `n` / `p` | Next / previous stage (not on Projects, where `n` is New) |
| `q` | Quit |
| `ctrl+s` | Save the label or prompt being edited (Taxonomy) |
| `e` | Edit (labels, a seed, or propose a prompt change on Tuning) |
| `o` | Edit the prompt by hand (Tuning) |
| `c` | Switch between Chat and Results on a narrow Tuning screen |
| `x` / `s` | Stop / start or resume a classifier run (Tuning, Test, Threshold, Full run) |

The F-keys work from every screen, even with a text field focused, but not on top of a dialog. F6 and F7 act on
the editor you are in (the seed list, the focused panel on Taxonomy, the prompt box on Tuning) and are off while
a draft is open there. Some terminals and operating systems reserve function keys; every F-key action also has a
button.

## System state vs project state

System state (API keys in the keyring, default models, saved S3 stores, the pgvector result limit, the project list) lives in `system.json`
under your user config directory (`$HUNCHES_HOME` overrides it) and is never part of a project. Project state is
only `.hunches/` in the project directory.

## Run

A tiny sample project is in `examples/sample`; run `hunches` from inside it to open it directly.

## Corpus formats

**Local** (small corpora): a directory with
- `vectors.npy`: float32, shape N x D
- `items.jsonl`: N lines `{"id": ..., "text": ...}`, row-aligned with `vectors.npy`
- `meta.json`: `{"embedding_model": "<pydantic-ai embedder string>"}`, e.g. `openai:text-embedding-3-small`

Search is brute-force cosine similarity.

**S3 Vectors** (large corpora): set `backend = "s3"`, `s3_bucket`, `s3_index` in `config.toml` (cosine index, item
id as the vector key, the text under the `text` metadata key) and use AWS credentials from the usual boto3
sources. A query returns at most 10,000 hits; if a seed reaches that, the search screen warns.

**PostgreSQL with pgvector** (a table that already holds the embeddings): set `backend = "pgvector"` and `pg_table`
(`table` or `schema.table`) in `config.toml`; the columns default to `pg_id_column = "id"`, `pg_text_column = "text"`
and `pg_vector_column = "embedding"` (a `vector` or `halfvec` column). If the text is in a different table from the
vectors, choose **Two tables** and set `pg_text_table` (joined on `pg_text_id_column`, default the id column).
hunches only reads: the connection is read-only, it never creates a table, index or the extension, and never
inserts. The connection URL holds a password, so it is never written to `config.toml` or `system.json`. Paste it
into the masked **url** field: Check store, Create and Save keep it in the OS keyring under
`HUNCHES_PG_URL_<id>`, where `<id>` (stored as `pg_url_id`) is a hash of host, port, database and user, never of the
password. Projects on the same database share one entry, and projects on different databases never overwrite each
other. Without a keyring, set that variable in the environment, or name your own with `pg_url_var`.
Project settings and New project have a **Check store** button that reports the pgvector version, column type and
dimension, an estimated row count, the indexes and one sample row.

- `pg_search = "exact"` (default) finds every item at or above the similarity floor, equal to the local backend, in
  one scan of the table for all seeds; it uses no index, so a large table takes time (the Search screen shows
  elapsed time and rows, and `x` stops it, cancelling the query on the server). `pg_search = "index"` lets an
  HNSW/IVFFlat index answer one query per seed, needs pgvector 0.8.0 or newer, and **can silently return far fewer
  hits than exist**; the Search screen then always shows an APPROXIMATE warning.
- A seed returns at most 10,000 hits (the same cap warning as S3). A search whose result could exceed
  **512 MB** is refused before it starts, or stopped while streaming; change the limit in **System settings
  (F5)** (`pg_max_result_mb` in `system.json`, 0 = no limit). `pg_statement_timeout_s` in `config.toml` overrides
  the role's `statement_timeout` for the search (0 = no limit).
- Managed services (RDS, Aurora, Supabase and similar) work with a login that can `SELECT` the table; add
  `?sslmode=require` (or `verify-full`) to the URL as the host documents. Through a transaction-mode pooler (for
  example Supabase port 6543) Check store suggests the direct or session URL for long searches. Not tested by the
  project's authors against any managed service yet: see `specs/005-pgvector/manual-checklist.md`.
- **RDS / Aurora IAM authentication**: install `hunches[rds]`, set `pg_auth = "rds_iam"` (optionally `pg_aws_region`
  and `pg_aws_profile`; credentials come from the usual boto3 sources) and make the URL variable a URL without a
  password, with the instance endpoint as host, e.g. `postgresql://db_user@my-instance.abc123.us-east-1.rds.amazonaws.com:5432/mydb`.
  A fresh token is generated for every connection; `sslmode=require` is added if the URL has none. The database
  user needs the `rds_iam` role and the AWS identity `rds-db:connect` on that user.

In every case `embedding_model` in `config.toml` must be the model the corpus was embedded with; the tool
refuses to search otherwise. It only embeds your seed phrases.

## Stages

1. **Brief and seeds.** Describe what you want to find; the assistant asks questions and proposes seed phrases that you edit in a table and approve.
2. **Search.** Seeds are embedded and searched; every item with cosine similarity of at least 0.60 becomes a candidate (score = best seed). Counts per similarity band are shown.
3. **Taxonomy and prompt.** The assistant interviews you (one label or several per item) and writes `taxonomy.yaml` and `prompt.md`. `off_topic` is built in and always exclusive.
4. **Gold dev set.** You label 50 random candidates by key. Labelling does not call the classifier (so it costs nothing and the classifier cache is not warmed): the first Tuning run classifies the whole dev set. Every row must be labelled to finish. If the corpus yields fewer than 50 candidates for a split, labelling is blocked with an error; add seeds or change the project's settings.
5. **Tuning.** The dev set is classified (progress, then results). Metrics (accuracy, per-label P/R/F1, macro/micro-F1) and the disagreements, each with the classifier's reasoning. Chat with the assistant, who can look at the disagreements and propose a prompt you accept, edit or reject, or edit the prompt yourself (`o`), until the target metric reaches the target score.
6. **Gold test set.** 50 more labelled candidates, classified once to report held-out metrics. Changing the prompt or the classifier model marks the result stale.
7. **Threshold.** About 30 items per similarity band are classified so you can see the off-topic rate per band. The cutoff is a band edge: select a band row (Enter) and Save (F2); the band's lower bound becomes the cutoff.
8. **Full run.** Candidates at or above the cutoff are classified with the classifier model, written to `results.jsonl` as they finish, with time and cost estimates first. Stop and resume freely. A prompt that has not been tested (stage 6) with the current prompt and classifier model blocks the run.
9. **Browse.** Search and filter `results.jsonl` (first 1000 matches are shown).

## Classifier reasoning and the cache

The classifier now returns a short reasoning before its labels, shown next to disagreements. The call cache key
changed with it, and cache entries are `{"labels", "reasoning"}` (an old list-shaped entry is a miss). **The first
run after upgrading is therefore billed again**, even for items classified before. Cost estimates show `?` rather
than `$0` when a model's price is unknown.

## Taxonomy versions

Editing label descriptions or the prompt never needs a new version. Changing the set of label names, or the mode
(one label or several), while gold rows are already labelled would invalidate them, so Taxonomy asks first and then
starts a new version: the current taxonomy, prompt, gold labels, state and derived results are copied whole to
`.hunches/versions/<n>/`, and the gold items stay the same with their labels cleared, to be labelled again under the
new labels (approve the taxonomy again to relabel). Nothing under `versions/` is ever deleted. The **Versions**
button on the Labels panel lists them; **Restore** makes one live again, after archiving the current state as a
new version first, so a restore can itself be undone. If the assistant's `write_taxonomy` would start a version, it
asks you to confirm.

## History, undo and redo

Hunches keeps its own record of changes to the three files that define the analysis: `seeds.csv`, `taxonomy.yaml`
and `prompt.md`. Every save (yours, the assistant's, or an edit made outside hunches, such as `git checkout`) is
stored under `.hunches/history/` as a verbatim copy plus a line in an append-only log; nothing is ever deleted.
Each file has its own undo stack, so undoing in the Prompt panel never reverts a seed edit. Gold labels are not in
the history.

- **Undo / redo (F6 / F7)** step the file you are editing back and forth. They change the file and nothing else:
  no classifier call and no automatic re-run. The assistant is told about it, with no model call.
- **History (F8)** lists every change and every approval, newest first, with who made it (you, the assistant,
  outside, undo, redo, restore). Select an entry for a diff or the saved text, and **Restore this** to make the
  file match that moment again. A restore is itself an edit you can undo.
- If you undo or restore something that changes the set of label names while gold labels exist, hunches asks first
  and archives the current state as a taxonomy version (see below); undoing the start of a version brings that
  version's gold labels back.
- If a file changes outside hunches, a notice appears once with Undo, History and Dismiss.

### Stale work and the Redo plan

Each stage remembers what it was computed from. When something upstream changes, the stage is marked `↻` (stale)
in the rail with a reason such as `prompt changed`, `seeds changed`, `embedding model changed` or `gold rows
changed`; `◐` marks a stage that lost work, such as a gold set that is now `44 of 50 rows`. Stages you have not
reached get no mark. Marked stages keep their old files until you redo them, and the banner on each screen says
why. Nothing is approved for you: after redoing a stage you approve it again.

**Redo plan (F9)** lists the stale and incomplete stages in order with how many classifier calls each needs to be
live and how many are already cached, and the cost (`?` when a model's price is unknown, never `$0`). Its button
goes to the earliest stage; after each re-approval it reopens on the next. The classifier cache is keyed by
content, so going back to an earlier prompt, or redoing a run whose inputs have not changed, costs nothing. A
description-only edit to a label changes the system prompt and therefore re-classifies everything, which is
correct. The prompt versions you see on Tuning are only a counter for that screen; the history does not number or
name prompt versions.

### Gold after the seeds change

When a new search leaves some of your gold items outside the candidate pool, they stay labelled and counted. Search
shows how many, and the Gold screen offers **Remove stale rows** (confirmed; the rows are kept in
`gold_removed.jsonl` and never drawn again) and **Draw N replacements** to label. The Tuning assistant can look at
this too (`get_gold_coverage`), ask to remove rows (you confirm) and draw new ones, but never sets a label.
Removing test rows after you have seen the test result weakens it as held-out evidence; the confirmation says so.

## What to commit

System state is outside the repository, so there is nothing of it to commit. Everything in `.hunches/` is plain files and the only state: config, seeds, candidates, taxonomy, prompt, gold labels,
threshold, results, chat history, cost, the edit history and the call cache. The tool never runs git; you commit.
`history/` is small text and should be committed; if `cache/` grows too large, gitignore it (the history still
works, going back just costs the calls again). Keep `.env` out of git.

## Cost tracking

The header (the rail from 100 columns) always shows total spend. Costs come from `genai-prices` and are summed per model in `cost.json`
and survive restarts. Cached calls cost nothing. If a model's price is unknown the cost is shown as `?`
with a warning, never as `$0`.

## Develop

```
uv sync --all-extras
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```

Tests never call a real LLM, AWS or database API. `tests/test_pg_integration.py` runs against a real PostgreSQL
with pgvector only when `HUNCHES_TEST_PG_URL` is set (CI has an optional job for it); otherwise it is skipped.
