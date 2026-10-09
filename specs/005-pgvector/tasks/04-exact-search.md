# 04 — `search_pg_exact`: one query for all seeds

Spec: D4, D5, D6, D10, "One query for all seeds (`exact`)", "Verified on a real database" (every row is a requirement on the SQL).

**Do** in `search.py`: add `PG_TOP_K = 10_000` next to `S3_TOP_K` and `search_pg_exact(vectors, floor)` returning `(hits_per_seed, capped)`, where `hits_per_seed` is `list[list[(id, text, sim)]]`, one list per seed in seed order, best first (`sim` desc, then id), and `capped` is true when some seed has exactly `PG_TOP_K` rows. Opens the connection (task 02), reads version/type/schema (task 03; no index-mode check), runs inside one read-only `REPEATABLE READ` transaction (verify how psycopg sets isolation level and read-only; report it).

The SQL is the two-step query in the spec, composed with `psycopg.sql`:
- Step 1, ids only: `seeds AS MATERIALIZED` from `unnest(%s::text[]) WITH ORDINALITY`, cast to the column's schema-qualified type; `pairs` as `table t CROSS JOIN LATERAL (… FROM seeds s OFFSET 0) d` so the table is the outer side; `WHERE t.vec IS NOT NULL AND d.sim >= %s AND d.sim <> 'NaN'`; `row_number() OVER (PARTITION BY i ORDER BY sim DESC, id)`; keep `rn <= PG_TOP_K`. Distance via `OPERATOR(<schema>.<=>)`, never relying on `search_path`. Seed vectors are sent as one text array of `[x,y,…]` literals; no `pgvector` Python package.
- Step 2: `SELECT id, text FROM table WHERE id = ANY(%s)` with the ids in the driver's native type; `str()` only when building hits. A missing text row (deleted between steps cannot happen inside one snapshot) is an error, not a silent drop.
- Rows are read through a server-side named cursor in batches (verify the psycopg named-cursor and `itersize` API; the spec notes it is observed rather than documented, so state in the report what the installed version documents).
- Nothing else is changed on the connection: no `SET` of planner settings.
- Do not "simplify away" `OFFSET 0`, the `LATERAL` over `t`, `MATERIALIZED`, the `NaN` test or the two-step fetch (the spec says why).

**Tests (red first, stubbed connection)**: assert on the SQL text and parameters: exactly one step-1 `execute` for 1, 3 and 30 seeds with all seed literals in one parameter, plus one step-2; the `NaN`, `OFFSET 0`, `LATERAL`, `MATERIALIZED`, `OPERATOR(extensions.<=>)` (extension in schema `extensions`) and `halfvec` cast shapes; no `SET` of planner settings; identifiers quoted; floor inclusive (a row at exactly the floor stays); canned rows for 3 seeds assemble into the expected per-seed lists sorted by hand-computed values, tie broken by id; `capped` true only with a monkeypatched small `PG_TOP_K` reached; integer and uuid ids reach step 2 unconverted and appear as `str` in hits; the connection is read-only and closed on error.

**Not in this task**: size guards, Stop, progress (05), the `index` branch (06), wiring into `build_candidates` (07).
