# 07 — Classifier and metrics

Spec section: Classifier, Cost and timing.

## Goal
Classify text with the cheap model and score predictions against gold. Two modules: pure metrics, and the model call.

## Do
- `src/hunches/metrics.py` (pure functions, no I/O). Input: lists of gold label sets and predicted label sets, plus the label list. Output: exact-match accuracy, per-label precision/recall/F1 (with `0` when a denominator is zero, documented), macro-F1, micro-F1, per-label counts, and the list of disagreeing item indices. `target_value(metrics, name)` for `accuracy | macro_f1 | micro_f1 | exact_match`; `accuracy` is the same number as `exact_match` and the UI label just differs by mode.
  - Tests against **hand-computed** examples written out in the test as comments: a single-label case, a multi-label case with partial overlap, a label with no gold examples, an all-correct case, and an `off_topic` mix. Do not generate expected values by running your own code.
- `src/hunches/classifier.py`:
  - Build the output type from the taxonomy: a list of `Literal[...]` containing user labels plus `off_topic`.
  - `classify(text, prompt, taxonomy, model)`: pydantic-ai `Agent` with that `output_type`, system prompt from `prompt.md`. Apply `validate_labels` from task 03; on a violation, let pydantic-ai retry via a validation error (check the current docs for the output-validator/retry mechanism) and give up after the library's limit with a recorded error, not a crash.
  - Route through the cache and cost recorder from task 04. Record timing for non-cached calls.
  - `classify_many(texts, ...)`: bounded concurrency (an `asyncio.Semaphore`, default 8), yields results as they finish so callers can write incrementally.
- Tests with `TestModel`/`FunctionModel`: valid output; `off_topic` combined with another label rejected and retried; `single` mode with two labels rejected; second identical call is a cache hit with no added cost.

## Done when
- All pass offline.
