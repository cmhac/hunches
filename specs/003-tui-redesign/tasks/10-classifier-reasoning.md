# 10 — The classifier returns reasoning

Spec: conflict 4, D10. Handoff: `design/BACKEND_CHANGES.md` §10; states `tune/below`, `tune/failed-item`, `final/result`. `[backend]` only; the UI that shows it lands in tasks 13 and 15. Files: `classifier.py`, `files.py` (none), `cost.py` (none).

## Goal
Every classification returns a short reasoning with its labels, kept through the cache, so users and the assistant can see why the classifier chose a label.

## Do
- **Structured output.** Replace `output_type=list[label_type]` with a model: `class Classification(BaseModel): reasoning: str; labels: list[label_type]`, built at runtime inside `classify` (the Literal depends on the taxonomy; keep the `# ty: ignore` already used for it). **`reasoning` must be declared before `labels`** so the model explains first and decides second. Check the installed pydantic-ai 2.53 docs for how a Pydantic model is passed as `output_type` and how `@agent.output_validator` receives it. The validator still calls `validate_labels(out.labels, taxonomy)` and raises `ModelRetry` on a violation.
- **System prompt.** Add one sentence to `system_prompt()`: "First give a short reasoning (one to three sentences) that names the evidence in the text, then the labels." Keep it out of `prompt.md`. It changes the string `cost.cache_key` hashes, so every existing cache entry stops matching; that is intended (spec conflict 4: the first run after upgrading is billed again; tell the user in the README, task 17).
- **`Prediction`** gains `reasoning: str | None = None` (None when `error` is set). `classify_many` yields it unchanged.
- **Cache shape.** `cost.cache_put(key, output, usage)` stores any JSON output. Store `output = {"labels": [...], "reasoning": "..."}`. On a hit, accept a dict output only; an entry whose `output` is a list (old shape) is a miss. (This is the handoff's "entry without reasoning is a miss", expressed without changing `cache_put`'s signature.) Reasoning must survive a cache hit so a second tuning run keeps it. `cost.py` stays unchanged.
- **Where reasoning is kept.** Tasks 13 and 15 carry it into the disagreement records. Per D10 it is **not** written to `results.jsonl`; `screens/run.py` row format is unchanged.
- Nothing else in `classifier.py` changes: failure handling (`UnexpectedModelBehavior` → `Prediction(None, error=…)`), timing, `classify_many`'s `finally` cancellation.

## Tests (`tests/test_classifier.py`)
- Update `FunctionModel`/`TestModel` scripts to return `Classification`-shaped outputs (`custom_output_args` with `reasoning` and `labels`).
- Reasoning is returned on a live call and **on a cache hit** (second call: `cached=True`, same reasoning, no model call).
- An old-shape cache entry (list output) is a miss and is replaced.
- Keep the retry tests for `off_topic` combined with another label and for single mode with ≠1 label, now through the model output.
- `Prediction.reasoning is None` when the call fails.
- Cache-key test: the hashed system string contains the reasoning sentence (hand-written expectation).
- Expect other tests that build classifier outputs (`test_tune_screen`, `test_final_screen`, `test_threshold_screen`, `test_run_screen`, `test_e2e`, `test_assistant_thinking`) to need their scripted outputs updated to the new shape.

## Done when
- All classifier call sites work unchanged apart from tests; `reasoning` is available on every `Prediction` that has labels.
