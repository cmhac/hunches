# hunches

An interactive terminal toolkit for content analysis over an already-embedded corpus:
seed phrases, semantic search, candidates, an LLM classifier validated against a hand-labelled
gold set, and classified output. A smart model talks to you; a cheap model does the bulk work.

## Install

```
uv tool install hunches          # or: pipx install hunches
uv tool install "hunches[s3]"    # adds boto3 for the S3 Vectors backend
uv tool install "hunches[local]" # adds Sentence Transformers for local query embeddings (Python < 3.14)
```

API keys come from the environment or a git-ignored `.env` in the project directory
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, ...). Never commit them.

## Run

From the project directory (the one that contains, or should contain, `.hunches/`):

```
hunches
```

The first run asks for the corpus location, the embedding model and the two model strings
(`smart_model`, `cheap_model`, as `provider:model`) and writes `.hunches/config.toml`. Later runs resume
at the first incomplete stage. `n` / `p` move between stages, `q` quits. A tiny sample project is in
`examples/sample`.

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

1. **Brief and seeds.** Describe what you want to find; the smart model asks questions and proposes seed phrases that you edit in a table and approve.
2. **Search.** Seeds are embedded and searched; every item with cosine similarity of at least 0.60 becomes a candidate (score = best seed). Counts per similarity band are shown.
3. **Taxonomy and prompt.** The smart model interviews you (one label or several per item) and writes `taxonomy.yaml` and `prompt.md`. `off_topic` is built in and always exclusive.
4. **Gold dev set.** You label 50 random candidates; the cheap model classifies as you go and per-label counts update live.
5. **Tuning.** Metrics (accuracy, per-label P/R/F1, macro/micro-F1) and a list of disagreements. The smart model proposes prompt edits you accept or change until the target metric reaches the target score.
6. **Gold test set.** 50 more labelled candidates, classified once to report held-out metrics. Changing the prompt marks the result stale.
7. **Threshold.** About 30 items per similarity band are classified so you can see the off-topic rate per band and pick a cutoff.
8. **Full run.** Candidates at or above the cutoff are classified with the cheap model, written to `results.jsonl` as they finish, with time and cost estimates first. Stop and resume freely.
9. **Browse.** Search and filter `results.jsonl` (first 1000 matches are shown).

## What to commit

Everything in `.hunches/` is plain files and the only state: config, seeds, candidates, taxonomy, prompt, gold labels,
threshold, results, chat history, cost and the call cache. The tool never runs git; you commit. If `cache/` grows
too large, gitignore it. Keep `.env` out of git.

## Cost tracking

The header always shows total spend. Costs come from `genai-prices` and are summed per model in `cost.json`
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
