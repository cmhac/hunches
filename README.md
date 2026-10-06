# hunches

An interactive terminal toolkit for content analysis over an already-embedded corpus:
seed phrases, semantic search, candidates, an LLM classifier validated against a hand-labelled
gold set, and classified output. An assistant model talks to you; a classifier model does the bulk work.

## Install

```
uv tool install hunches          # or: pipx install hunches
uv tool install "hunches[s3]"    # adds boto3 for the S3 Vectors backend
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
backend (local corpus or S3 Vectors), corpus and embedding model; the assistant and classifier models are copied
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
| `n` / `p` | Next / previous stage (not on Projects, where `n` is New) |
| `q` | Quit |
| `ctrl+s` | Save the label or prompt being edited (Taxonomy) |
| `e` | Edit (labels, a seed, or propose a prompt change on Tuning) |
| `o` | Edit the prompt by hand (Tuning) |
| `c` | Switch between Chat and Results on a narrow Tuning screen |
| `x` / `s` | Stop / start or resume a classifier run (Tuning, Test, Threshold, Full run) |

The F-keys work from every screen, even with a text field focused, but not on top of a dialog.

## System state vs project state

System state (API keys in the keyring, default models, saved S3 stores, the project list) lives in `system.json`
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

In both cases `embedding_model` in `config.toml` must be the model the corpus was embedded with; the tool
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

## What to commit

System state is outside the repository, so there is nothing of it to commit. Everything in `.hunches/` is plain files and the only state: config, seeds, candidates, taxonomy, prompt, gold labels,
threshold, results, chat history, cost and the call cache. The tool never runs git; you commit. If `cache/` grows
too large, gitignore it. Keep `.env` out of git.

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

Tests never call a real LLM or AWS API.
