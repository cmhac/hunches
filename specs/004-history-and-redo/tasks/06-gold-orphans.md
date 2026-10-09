# 06 — Gold orphans and removal

Spec: Gold after seeds change (D2), Tests → Gold. `files.orphaned_gold`, `files.gold_coverage`, `gold.remove(ids, reason)` writing append-only `gold_removed.jsonl`, `gold.draw` excluding removed ids, removal below 50 labelled sends resume back to stage 4/6, and the `gold_dev`/`gold_test` components update so Tuning/test result go stale.
