# 16 — Stage 8: full run

Spec section: Stages, item 8; Cost and timing.

## Goal
Classify every candidate at or above the threshold, resumably, with estimates and live progress.

## Do
- `src/hunches/screens/run.py`.
- Before starting: show the number of items to classify, the time estimate (items/sec from the recorded timings in task 04/07/15 divided into remaining items) and the cost estimate (average cost per item from sample usage × remaining items). If the model price is unknown, show cost as `?` with the warning, not 0. If no timing samples exist, say so rather than inventing a number.
- Start key runs `classify_many` (task 07) in a worker, appending each result to `results.jsonl` immediately. Items already in `results.jsonl` are skipped (resume). Show live progress bar, running cost, items/sec and ETA; allow pause/stop with a key and clean shutdown (no half-written line).
- Per-item failures after retries are written with an error marker and skipped, listed on the screen, and retried on the next run.
- Prompt-change guard: if `prompt.md` hash differs from the tested prompt, warn before starting.
- Tests: resume skips done items; killing mid-run (cancel the worker) leaves a valid file and the next run completes the rest; estimates computed from fixture timings; error rows handled.

## Done when
- Pilot tests pass.
