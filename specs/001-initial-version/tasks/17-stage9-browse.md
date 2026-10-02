# 17 — Stage 9: browse

Spec section: Stages, item 9.

## Goal
Browse and search `results.jsonl`.

## Do
- `src/hunches/screens/browse.py`. A `DataTable` (id, labels, similarity, truncated text), a search `Input` (case-insensitive substring over text), and label filters (toggle one or more labels; show items having any selected label; include an `off_topic` toggle). Selecting a row shows the full text in a side pane.
- Handle a large results file reasonably: load once, filter in memory. Do not add pagination or indexes unless it is visibly slow with ~100k rows (test it with generated rows and note the result).
- Header counts: showing X of Y.
- Tests: filter by label, search, combined, empty result, row selection shows full text.

## Done when
- Pilot tests pass.
