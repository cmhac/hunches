# 06 — Candidate generation

Spec section: Candidate generation, Stages 2.

## Goal
Turn `seeds.csv` into `candidates.jsonl`.

## Do
- `src/hunches/candidates.py`:
  - `embed_seeds(seeds)`: `pydantic_ai.Embedder(...).embed_query(...)` per spec (verify the exact signature in current docs), going through the cache and cost recorder from task 04.
  - `build_candidates()`: for each seed, call `search()` from task 05 with floor 0.60; merge by item id keeping `max_similarity` and `best_seed`; write `candidates.jsonl` sorted by similarity descending.
  - `BANDS`: edges `0.60, 0.625, …, 0.75` and `band_of(similarity)`; `band_counts(candidates)` for the UI. Boundaries are lower-inclusive; `0.75+` is open-ended.
- Tests: merging across two seeds takes the max and records the right best seed; band assignment at each boundary; `Embedder` replaced by pydantic-ai's test embedding model if available (check docs), else a stub function. Never a real model.

## Done when
- Tests pass; running twice gives identical output (cache hits on the second run cost nothing).
