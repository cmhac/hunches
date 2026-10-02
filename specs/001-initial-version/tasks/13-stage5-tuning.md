# 13 — Stage 5: tuning loop

Spec section: Stages, item 5; Classifier (metrics, `target_metric`).

## Goal
Show dev-set metrics and disagreements, and let the smart model propose prompt edits until the target is reached.

## Do
- `src/hunches/screens/tune.py`.
- Top: all metrics from task 07 (exact-match, per-label P/R/F1, macro-F1, micro-F1), the current `target_metric` and `target_score`, with a pass/fail indicator. The user can change both in the screen (writes `config.toml`).
- Left: list of disagreements (text, gold, predicted). Selecting one shows the full text.
- Key to ask the smart model for a prompt edit: give it the current `prompt.md`, the taxonomy, and the disagreements (cap how many it sees, say 20, noting if truncated). It returns a proposed new prompt. Show a diff against the current one (stdlib `difflib` is fine). User accepts, edits, or rejects. Accept overwrites `prompt.md`.
- After accepting, re-run the dev set. Cached items are free, so only classifications whose prompt changed are re-run (the cache key already includes the prompt). Show progress and the cost of that run.
- Remember an in-memory (and optionally on-disk) history of prompt versions and scores so the user can see the trend; keep it simple (a list in the screen, optionally `prompt_history.jsonl`).
- Done key, enabled when the target is met (or the user overrides with a confirmation).
- Tests with `FunctionModel`: disagreements are listed correctly; accepting a proposed prompt changes the classifier outputs and the metrics; the cache avoids re-calls for an unchanged prompt; changing `target_metric` changes the pass/fail result.

## Done when
- Pilot tests pass.
