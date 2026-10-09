# 07 — `build_candidates` branch and Search screen

Spec: D6, D10, "One query for all seeds" (Result), UI (Search screen), "Streaming and progress", Tests (Screens).

**Do**
- `candidates.build_candidates`: one `if config.backend == "pgvector" and config.pg_search != "index":` that embeds the seeds as today, gets all per-seed hit lists from `search.search_pg_exact(vectors, FLOOR)` in one call, and then falls into the **unchanged** merge/sort/write/meta code. Local, S3 and `index` mode call `search()` per seed exactly as before. Docstring `S3 topK cap` → `backend cap`. The same Stop handle (task 05) is reachable from the screen.
- `screens/search.py`: `cap_warning` becomes backend-aware (`WARNING: <backend> returned its cap of N hits …`; S3 text unchanged for S3, `pgvector` for pgvector, using `search.S3_TOP_K` / `search.PG_TOP_K`); show the `APPROXIMATE` warning for `index` mode every time the screen is shown; the progress callback with total `0` shows elapsed time and rows received (`LabelBar` has no total: handle it, test at 80×24); the Stop path calls the handle from task 05 (key `x`, button per the `key_button` rule). A connection or scrubbed error appears in the existing `#error` line.
- Add the new warning/progress states to `tests/test_sizes.py` (80×24, 100×30, 120×36).

**Tests (red first)**: `build_candidates` with `search_pg_exact` monkeypatched produces the same `candidates.jsonl` and meta as the per-seed path for the same hand-built data (including a tie going to the earlier seed and the max-similarity rule); the stub is called once whatever the number of seeds; `index` mode and S3 still call `search()` per seed; Pilot: cap warning text per backend, `APPROXIMATE` warning shown only for `index`, progress with unknown total renders, Stop ends the run and clears the searching state, error line has no password.

**Not in this task**: Check store, settings screens.
