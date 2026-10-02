# 001 — Initial version

Status: draft for implementation. Source: Notion "Hunches tool" idea page, plus design review with the author.

## Principles

- Absolute minimal implementation. No abstraction, plugin system, base class or registry unless the user asks for one.
- Where two behaviours must coexist (local vs S3 vector search), use a plain `if` in one function. No interfaces.
- Plain files in `.hunches/` are the only state. The tool never runs git; the user commits.
- Before using any Pydantic AI or Textual API, check it against the current docs (APIs are moving, and the Pydantic AI docs now live under `pydantic.dev/docs/ai/`). Do not code from memory.

## What it is

An interactive TUI toolkit for content analysis over a corpus that is already embedded: seed phrases → semantic search → candidate set → LLM classifier (validated against a hand-labelled gold set) → classified output. Two kinds of AI are used: a smart model for talking to the user, a cheap model for bulk classification.

Out of scope for v1: corpus ingestion/embedding/index creation, other vector backends, web UI, multi-user use, any git operation by the tool.

## Stack

- Python 3.12+, `uv`. Lint/format with `ruff`, type check with `ty`, all as pre-commit hooks.
- `pydantic-ai` for all LLM calls and embeddings (`Agent`, `Embedder`). Anthropic and OpenAI both work out of the box (provider is just the prefix of the model string).
- `textual` for the whole UI. There is no non-TUI interface beyond the `hunches` entry point.
- `numpy` (local search), `boto3` (S3 Vectors; optional extra `s3`), `genai-prices` (cost), `pyyaml`.
- One package `hunches`, console script `hunches`. Run from inside the project directory (the one containing `.hunches/`).
- API keys from environment or `.env`.

## Vector search

Two backends, selected by `config.toml`. The tool is read-only against both.

**Local** (small corpora): a directory with
- `vectors.npy` — float32, shape N×D
- `items.jsonl` — N lines `{"id": ..., "text": ...}`, row-aligned with `vectors.npy`
- `meta.json` — `{"embedding_model": "<pydantic-ai embedder string>"}`

Search is brute-force cosine similarity in numpy (normalize, matrix multiply).

**S3 Vectors** (large corpora): Amazon S3 Vectors via `boto3` `s3vectors` `query_vectors`, cosine distance. Item `id` is the vector key; `text` is in vector metadata. Convert returned distance to similarity. `topK` limits must be checked in the AWS docs; if the per-query cap is lower than the number of hits above the floor, document the cap and fall back to the highest-scoring hits, and show a visible warning in the TUI.

**Embedding models.** The query embedding must come from the same model as the index. `meta.json` (local) or `config.toml` (S3) records the model; the tool refuses to search if `config.toml`'s `embedding_model` disagrees. Supported embedders are whatever `pydantic_ai.Embedder` supports; the documented list includes OpenAI `text-embedding-3-*` and local Sentence Transformers models from Hugging Face, which the tool can run locally for query embedding. The tool only embeds seed phrases (tens of short strings), so running a local model on CPU is fine; the first run downloads the model. Embeddings use `embed_query()`.

## Candidate generation

- Seed phrases embedded, each searched. Retrieval floor: cosine similarity 0.60. All items at or above the floor are candidates; there is no top-K.
- An item's candidate score is its maximum similarity across all seed phrases.
- Similarity bands (used for threshold selection): `0.60–0.625`, `0.625–0.65`, … `0.725–0.75`, `0.75+`.

## The `.hunches/` folder

All tracked in git. Layout is a starting point; the implementer may add, change or remove files as needed.

```
config.toml        backend, paths, embedding_model, smart_model, cheap_model, dev_accuracy_target
state.json         approval flags only (seeds_approved, taxonomy_approved, dev_done, test_done, threshold_chosen)
brief.md           the user's original description of what to find (kept for transparency)
chat/<stage>.json  agent message history (ModelMessagesTypeAdapter)
seeds.csv          seed phrases (reviewed by the user)
candidates.jsonl   id, text, max_similarity, best_seed
taxonomy.yaml      labels with descriptions; "off_topic" is built in, not listed
prompt.md          classifier prompt
gold.jsonl         {id, text, labels: [...], split: "dev"|"test"}
threshold.json     chosen similarity cutoff + the band sample results
results.jsonl      {id, text, labels: [...], max_similarity}
cost.json          running total and per-model breakdown
cache/<sha256>.json  cached API calls
```

`cache/` is tracked by default like everything else; the user can gitignore it if it grows.

## Stages

Every stage is a Textual `Screen`. The app header is always visible and shows project name, current stage and **total cost so far**. If any call's cost is `None` (model unknown to `genai-prices`), show a prominent warning in the header and display that cost as "?" — never $0.

Resumability: on start, load `.hunches/` and go to the first incomplete stage. Completion is derived from files plus the flags in `state.json`. Everything a stage produces is written to disk as it is produced.

1. **Brief and seeds.** User describes what they want to find. The smart-model agent asks follow-up questions in a chat panel and proposes seed phrases (statements that would be true of a matching item). User edits `seeds.csv` in a DataTable inside the TUI and approves.
2. **Search.** Embed seeds, search, write `candidates.jsonl`. Show candidate counts per band.
3. **Taxonomy and prompt.** The agent starts from `brief.md`, interviews the user, and writes `taxonomy.yaml` and `prompt.md`. Chat history is saved in `chat/`.
4. **Gold dev set.** Random sample of 50 candidates (without replacement). User labels each in the TUI. This is multi-label: any number of taxonomy labels, or `off_topic` alone. TUI shows a per-label count table updating as the user labels, so the user can see which labels are under-represented (draw more samples if needed). The classifier runs on the sample as it goes.
5. **Tuning loop.** TUI shows accuracy on the dev set and a browsable list of all disagreements (predicted ≠ gold). A key press asks the smart model to propose a prompt edit; user approves or edits the diff, the dev set re-runs (cached, so cheap), and `prompt.md` is overwritten. Repeat until accuracy ≥ `dev_accuracy_target` (default 90%, user can change).
6. **Gold test set.** Another 50 random candidates, disjoint from dev. User labels them. Run once and report accuracy on the test set. User can browse disagreements and go back to tuning (any prompt change invalidates the test result, which is shown as stale). User accepts when satisfied.
7. **Threshold.** Classify ~30 random items from each similarity band. Show the off-topic rate per band. The user picks a cutoff, saved to `threshold.json`. "Off-topic" for this purpose means a predicted label set that is exactly `{off_topic}`.
8. **Full run.** Candidates ≥ threshold are classified with the cheap model, appended to `results.jsonl` as they complete, resumable. Before starting, show a time estimate (items/sec measured from the earlier sample runs; every sample run records timing) and a cost estimate from sample usage. Show live progress, cost and ETA.
9. **Browse.** Navigate and search `results.jsonl` in a DataTable with a search box and label filters.

## Classifier

- Cheap model through a pydantic-ai `Agent` with structured output: a list of labels drawn from the taxonomy plus `off_topic` (a `Literal` built from `taxonomy.yaml`). Rule enforced in validation: if `off_topic` is present it is the only label; at least one label is required.
- Metrics: **exact-match accuracy** (predicted set equals gold set) is the headline number and what `dev_accuracy_target` applies to. Also show per-label precision and recall. A disagreement is any item where the sets differ.
- Call cache key: `sha256(model + prompt + text)`. Applies to classification and embeddings only, not to the chat agent.

## Cost and timing

- Sum `result.usage()` of every agent run and embedding call into `cost.json`; dollars come from `genai-prices` (via the pydantic-ai cost helpers). Cost survives resume.
- Cached calls cost nothing and do not count toward throughput measurements.

## Testing

- `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"`).
- LLM code: use pydantic-ai `TestModel` (or `FunctionModel` where a specific output is needed). Never call a real API in tests.
- Textual (per the Textual testing guide):
  - Drive the app with `async with app.run_test() as pilot:`; use `pilot.press(...)` for keys and `pilot.click("#id")` for widgets.
  - Add `await pilot.pause()` before assertions whenever a message must be processed first.
  - Default terminal is 80×24; pass `run_test(size=(...))` when a screen needs more room.
  - Each screen gets one Pilot smoke test that exercises its main path against a tmp `.hunches/` folder. Optionally add `pytest-textual-snapshot` (`snap_compare`) for layout regressions; update baselines deliberately with `--snapshot-update`.
- Local vector search tested with a tiny hand-built `vectors.npy`. S3 is tested with a stubbed `query_vectors` response only.

## CI/CD

- GitHub Actions: one workflow runs ruff, ty and pytest on push and PR.
- One workflow publishes to PyPI when a tag is pushed, using trusted publishing (OIDC), so no token is stored in secrets.

## Open items for the implementer to flag, not guess

- S3 Vectors `topK` maximum (see above).
- Exact pydantic-ai names for embedding cost and usage; exact extras name for local Sentence Transformers.
- Whether exact-match accuracy is too strict for multi-label (if it is, per-label F1 is the fallback; ask the user).
