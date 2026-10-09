# 06 — `search()` `index` mode

Spec: D4, D6, D9, "Why exact is the default", Errors (`index` on < 0.8.0).

**Do** in `search.search()`: a third plain `elif config.backend == "pgvector"` branch for `pg_search == "index"` only (one query per seed, signature and return value unchanged: `(hits, capped)`). `pg_search == "exact"` through `search()` is not supported (the exact path is `search_pg_exact` from `build_candidates`, task 07); raise a clear internal error rather than silently running the index path. Steps: connect (task 02), probe the version, `require_index_mode_version` **before any `SET`**, then in one read-only transaction `SET LOCAL hnsw.iterative_scan = relaxed_order` and `SET LOCAL hnsw.max_scan_tuples = <PG_MAX_SCAN>`, and `SELECT id, text, 1 - (vec OPERATOR(schema.<=>) %s::<type>) AS sim FROM table WHERE 1 - (…) >= %s ORDER BY vec OPERATOR(schema.<=>) %s::<type> LIMIT PG_TOP_K`, with the same `NaN` guard as exact. Re-sort client-side by similarity (relaxed order). Set only the parameters named here (the spec says not to hard-code `ef_search`'s bound). `capped` as for S3. Name `PG_MAX_SCAN` as a module constant and justify its value from the pgvector README in the spec (the default is 20,000; the spec's measurements show raising it did not help, so say what you chose and why).

Also expose a small `is_approximate(config)` (true for pgvector + `index`) that the Search screen uses for the permanent warning text `WARNING: APPROXIMATE pgvector search; the index may hide hits above the floor. Switch to exact in Project settings for a complete pool.` (task 07 shows it).

**Tests (red first, stubbed)**: 0.6.0 raises the exact message and the fake saw no `SET`; 0.8.1 issues both `SET LOCAL` statements before the query, one query per seed for 3 calls; results re-sorted from deliberately out-of-order canned rows; floor and `NaN` guard in the SQL; `capped` with a small monkeypatched `PG_TOP_K`; `halfvec` and schema handling as in 04; local and S3 behaviour unchanged (existing tests untouched and green).

**Not in this task**: wiring `exact` into `build_candidates`, UI.
