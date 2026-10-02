# 10 — Stage 2: search

Spec section: Stages, item 2.

## Goal
Run candidate generation and show counts per band.

## Do
- `src/hunches/screens/search.py`. A button/key runs `build_candidates()` (task 06) in a Textual worker so the UI stays responsive; show a spinner/progress text.
- Show a table: band, number of candidates, cumulative number at or above that band. Show total candidates and the best-seed distribution (top ~10 seeds by number of items won).
- If the S3 backend returned `capped=True` (task 05), show a visible warning with the cap value.
- If the embedding-model mismatch error is raised, show it plainly with how to fix it; do not crash.
- Candidates are persisted by task 06. Re-running overwrites; the screen warns that downstream gold labels reference ids and remain valid, but sample sets may need refreshing if the candidate set changed a lot.
- Tests: a tiny local index fixture → band table matches expected counts; the capped warning appears with a stubbed S3 response; mismatch error is displayed.

## Done when
- Pilot tests pass.
