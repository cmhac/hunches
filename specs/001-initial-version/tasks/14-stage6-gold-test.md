# 14 — Stage 6: gold test set

Spec section: Stages, item 6.

## Goal
A held-out test set, evaluated once and flagged stale if the prompt changes.

## Do
- Reuse the gold screen from task 12 with `split="test"`: 50 random candidates disjoint from dev (and from anything already in gold).
- After labelling, run the classifier once and show all metrics plus the disagreement list.
- Store the prompt hash used for the evaluation next to the result (for example `test_result.json`: prompt hash, metrics, timestamp). If the current `prompt.md` hash differs, show the result as **stale** with a clear banner and offer to re-run.
- Path back to tuning (stage 5) is always available. Remind the user that tuning against test disagreements weakens the test result; do not block it.
- Accept key sets `test_done`.
- Tests: disjointness from dev; staleness flips when `prompt.md` changes; accept sets the flag; metrics on the test set match hand-computed values for a tiny fixture.

## Done when
- Pilot tests pass.
