# 04 — Call cache and cost tracking

Spec sections: Classifier (cache key), Cost and timing, Stages (header).

## Goal
One place that every LLM and embedding call goes through for caching, usage and cost accounting.

## Do
- `src/hunches/cost.py`:
  - Cache: `cache/<sha256>.json`, key `sha256(model + prompt + text)` (use a delimiter that cannot be ambiguous, e.g. length-prefix or JSON-encode the tuple). Used for classification and embeddings only, never the chat agent. Cache stores the output and the original usage so estimates can use it, but a cache hit adds **no** cost and **no** timing.
  - `cost.json`: running total and per-model breakdown (input tokens, output tokens, calls, dollars). Survives restarts. A model whose price is unknown records dollars as `null`, and the total is flagged `unknown: true`.
  - Dollar computation: use pydantic-ai's cost helpers on the run usage / `EmbeddingResult.cost()` (spec open item: confirm the exact names in the current docs) which sit on `genai-prices`. When it returns `None`, store `null`. Never substitute 0.
  - `record(model, usage_or_cost)` function and `total()` returning `(dollars, unknown_flag)`.
  - Timing: `record_timing(label, n_items, seconds)` appended to a small file or to `cost.json`, used later for items/sec estimates. Cache hits are excluded.
- Tests: cache hit does not change totals; unknown-price model yields `null` and `unknown: true`; totals persist across a reload; key changes when model, prompt or text changes.

## Done when
- Tests pass using `TestModel` (see whether `TestModel` reports usage; if its price is unknown that is a good natural test of the `None` path).
