# 005 — pgvector backend

Status: proposal, for review. Not implemented. Builds on `../001-initial-version/spec.md`, `../002-onboarding-setup/spec.md`, `../003-tui-redesign/spec.md` and `../004-history-and-redo/spec.md`, all implemented. Written 2026-10-09 against `main` at `c8ebdf1`.

**Read order for an implementer:** this spec → your task file (none yet; see "Proposed tasks") → the code named under "What changes in the code".

## What this is, in one paragraph

Today `hunches` searches an already-embedded corpus from either a local directory (`vectors.npy` + `items.jsonl` + `meta.json`, numpy) or an Amazon S3 Vectors index. This spec adds a third backend, **pgvector**: a table in a PostgreSQL database that has the `vector` extension and already holds the corpus embeddings. As with S3, hunches only **reads** it: it never creates tables, indexes or the extension, never inserts, and never embeds the corpus. Only `search.py` talks to the database; everything downstream (candidates, gold, classifier, metrics, history) is untouched.

## Principles

Same as 001–004 (minimal implementation; no abstraction, base class, registry or plugin system; where behaviours coexist use a plain `if` in one function; plain files in `.hunches/` are the only state; check every API against current docs; never call a real LLM, AWS or database in the default test run; unknown is `?`; never commit secrets). Additional rules:

- **Read-only against the database.** The connection is opened read-only and every statement is a `SELECT` or a `SET LOCAL`.
- **No secrets in tracked files.** The connection URL contains a password, so it never goes in `config.toml` (tracked) or `system.json`. It comes from an environment variable or the OS keyring (D3).
- **Recall must not silently degrade.** An approximate index can return far fewer rows than exist above the similarity floor without any error. The default mode is exact (D4); the approximate mode shows a permanent warning.

## Resolved decisions

These are my recommendations; the ones marked **ask** are open for Chris.

| # | Question | Decision | Evidence |
|---|----------|----------|----------|
| D1 | Driver | **psycopg 3**, optional extra `pg = ["psycopg[binary]"]`, imported lazily inside `search()` with the same "needs … `pip install hunches[pg]`" error as boto3. The query vector is sent as a text literal cast in SQL (`%s::vector`), so the separate `pgvector` Python package is not needed. | The pgvector README shows vectors as text literals (`'[1,2,3]'`); the `pgvector` package is only needed to register adapter types ([README](https://github.com/pgvector/pgvector#readme), [pgvector-python](https://pypi.org/project/pgvector/)). Binary-wheel behaviour of `psycopg[binary]` is from memory: verify against the psycopg install docs in task 01. |
| D2 | Table layout | **Configurable table and column names with defaults**: `pg_table` (required, may be schema-qualified `schema.table`), `pg_id_column="id"`, `pg_text_column="text"`, `pg_vector_column="embedding"`. The corpus is "already embedded" by someone else, so a fixed schema would be wrong. All identifiers are composed with `psycopg.sql.Identifier`, never string-formatted. | Mirrors S3, where `key` is the id and `metadata.text` the text. |
| D3 | Where the connection URL lives | **Environment variable first, then the OS keyring**, through the existing `keys.status/save` (which already work for any variable name). Config stores only the variable name: `pg_url_var`, default `HUNCHES_PG_URL`. `keys.VARS` stays LLM-only, so `load_into_env` is unchanged; `search` resolves the URL itself with `os.environ.get(var) or keys._stored(var)`. | `keys.py` takes a `var` argument everywhere. |
| D4 | Exact vs approximate search | `pg_search = "exact"` (default) or `"index"`. **Exact** forces a sequential scan and answers **all seeds in one query** (D10), so the result equals the local numpy backend: every item at or above the floor, no cap. **Index** lets an HNSW/IVFFlat index answer, one query per seed, with iterative scan; it shows an `APPROXIMATE` warning on the Search screen every time. | See "Why exact is the default". |
| D5 | Similarity | `similarity = 1 - (column <=> query)`. pgvector documents cosine similarity as 1 minus cosine distance and `<=>` as cosine distance ([README](https://github.com/pgvector/pgvector#readme)); unlike S3 Vectors (001 open item), this is documented, not assumed. The operator is norm-invariant, so the corpus need not be normalised. **A zero vector gives distance `NaN`, and in Postgres `NaN` compares greater than every number, so `1 - NaN >= floor` is TRUE** (checked on PostgreSQL 16 + pgvector 0.6.0: a zero row passed the floor). The SQL therefore also requires `sim <> 'NaN'` (in Postgres `NaN = NaN` is true, so `isnan()`, which does not exist for `double precision`, is not needed). The local backend gives such rows similarity 0. | pgvector README; `candidates.FLOOR`; tested 2026-10-09, see "Verified on a real database". |
| D6 | Result cap | **Top `PG_TOP_K = 10_000` per seed in both modes** (Chris, 2026-10-09), same as S3 so the existing cap warning applies. `capped` is true when some seed has exactly `PG_TOP_K` hits. In `exact` mode the cap is applied per seed inside the single query (a window function; see below). In `index` mode it is the `LIMIT` the index needs anyway, and the permanent `APPROXIMATE` warning also applies. | S3 precedent (`search.S3_TOP_K`). |
| D7 | Embedding model | Recorded in `config.toml` as `embedding_model` (as for S3), chosen with the model picker. There is no `meta.json` in a table, so hunches cannot detect a mismatch by itself; **Check store** (below) reports the column dimension so a human can compare it with the model's. | 002 New project, S3 path. |
| D8 | Saved stores in `system.json` | **Not in this spec.** S3 stores exist so one bucket/index can back several projects (002). For Postgres the reusable parts are a secret (already shared by `pg_url_var`) and five short fields with defaults. Adding `pg_stores` also means a `system.json` schema change; defer until someone asks. | Minimal implementation. **ask.** |
| D9 | Version/compat | Needs pgvector with `<=>` (any release) and, for `"index"` mode, **0.8.0+** for iterative scans. | README: "Starting with 0.8.0, you can enable iterative index scans". |
| D10 | One query for all seeds | **Yes, for `exact`.** One scan of the table answers every seed, and the per-seed top-`PG_TOP_K` cap is kept, so the result is exactly what the per-seed loop would produce (`build_candidates` then merges per seed as today: highest similarity wins, ties to the earlier seed). `index` mode stays one query per seed: a per-row lateral lookup cannot use an ANN index. | Tested against numpy and against the per-seed SQL, 2026-10-09. |

## Why exact is the default

`hunches` asks "every item at or above this similarity", not "the 10 nearest". pgvector's approximate indexes answer a `ORDER BY … LIMIT k` query by walking a graph with a candidate list of `hnsw.ef_search` (default 40), and "with approximate indexes, filtering is applied after the index scan" ([README](https://github.com/pgvector/pgvector#readme)). So an index-backed query asking for 10,000 rows returns about 40 unless iterative scan is on, and with iterative scan it still stops at `hnsw.max_scan_tuples` (default 20,000, approximate), after which it "will still return fewer than LIMIT rows". None of these is an error, and a short result is indistinguishable from "that is all there was". The local backend and S3 Vectors do not have this failure mode, and the whole pipeline (candidate pool, gold sampling, coverage) assumes the pool is complete.

Hence:

- **`exact` (default):** see "One query for all seeds" below. No index is used or needed, there is no `LIMIT`, and the distance floor is applied in SQL (safe, because index scans are off).
- **`index`:** one query per seed (`SELECT id, text, 1 - (vec <=> q) AS sim FROM t WHERE … ORDER BY vec <=> q LIMIT PG_TOP_K`, the shape an index needs), but `SET LOCAL hnsw.iterative_scan = relaxed_order` (results may be slightly out of order; we re-sort client-side) and `SET LOCAL hnsw.max_scan_tuples = <PG_MAX_SCAN>`, with `WHERE 1 - (vec <=> q) >= floor` pushed into SQL so the scan continues until `LIMIT` or `max_scan_tuples`. Always shows: `WARNING: APPROXIMATE pgvector search; the index may hide hits above the floor. Switch to exact in Project settings for a complete pool.` (The 1000 upper bound of `ef_search` I remember is **not** in the README; do not hard-code it. Set only the parameters named here.)

**Tested (see "Verified on a real database"):** `enable_indexscan = off` on a table that has an HNSW index gives a sequential scan plus sort, i.e. exact search. Still to verify with a real pgvector 0.8+: the `index`-mode `SET LOCAL` names and what `index` mode misses under default settings.

## One query for all seeds (`exact`)

Yes: one query returns the candidates for every seed, with the top-`PG_TOP_K` cap applied **per seed**. The seed vectors are embedded first (as today, cached) and sent once as a text array. Every (row, seed) similarity is computed once; pairs below the floor (or `NaN`) are dropped; the survivors are ranked within each seed and the top `PG_TOP_K` of each seed are returned:

```sql
WITH seeds AS MATERIALIZED (
  SELECT u.i - 1 AS i, u.q::vector AS q            -- parse each seed vector once, not once per row
  FROM unnest(%s::text[]) WITH ORDINALITY AS u(q, i)
),
pairs AS (
  SELECT t.{id} AS id, t.{text} AS text, d.i, d.sim
  FROM {table} t
  CROSS JOIN LATERAL (                              -- refers to t, so the table is the outer side:
    SELECT s.i, 1 - (t.{vec} <=> s.q) AS sim        --   it is scanned once, whatever S is
    FROM seeds s
    OFFSET 0                                        -- stops the planner pulling the expression up and computing it twice
  ) d
  WHERE t.{vec} IS NOT NULL
    AND d.sim >= %s                                 -- the floor
    AND d.sim <> 'NaN'                              -- zero vectors (D5)
),
ranked AS (
  SELECT *, row_number() OVER (PARTITION BY i ORDER BY sim DESC, id) AS rn FROM pairs
)
SELECT id, text, i, sim FROM ranked WHERE rn <= {PG_TOP_K}
```

with `SET LOCAL enable_indexscan = off` and `enable_bitmapscan = off` first, in a read-only transaction. Each `OFFSET 0`, the `LATERAL` over `t`, the `MATERIALIZED` CTE and the `NaN` test is there for a reason shown below; do not "simplify" them away without re-running the checks.

**Result.** At most `S × PG_TOP_K` rows, `(id, text, seed index, similarity)`. `search.search_pg_exact(vectors, floor)` turns them into one hit list per seed (`list[list[(id, text, sim)]]`, best first) plus `capped` (any seed with exactly `PG_TOP_K` rows). `build_candidates` takes a plain `if config.backend == "pgvector" and config.pg_search == "exact":` to get those lists in one call instead of calling `search()` per seed; **the merge, sort, write and meta code below it is unchanged**, so the output is identical to the per-seed path. Local, S3 and `index` mode are untouched.

**Cost, honestly.** The table is read once, but the database still computes S × N distances and ranks the pairs that pass the floor (a sort of those pairs; spills to disk if they exceed `work_mem`). The saving over S separate scans is **I/O**, which matters when the table does not fit in cache. When it does fit, the work is CPU-bound and one query is no faster than S queries (measured below). The reasons to prefer one query anyway: one pass over a table too big to cache, one round trip, one `statement_timeout`, one Stop, and one progress display.

**Streaming and progress.** Read with a server-side (named) cursor so rows arrive in batches. One query has no per-seed progress, so the Search screen shows running time and rows received; `progress` is called as `(received, 0, "")` on this path and the screen handles the zero-total case (`LabelBar` has no total; test at 80×24).

### Verified on a real database (2026-10-09)

PostgreSQL 16.15 (Ubuntu package) with pgvector **0.6.0** (the apt version) and psycopg **3.3.6**, run in the build container. Scripts were scratch, not committed; task 05 turns them into the integration test.

| Claim | Result |
|---|---|
| The query above equals the numpy per-seed reference | 20,000 rows × 32 dims, 5 seeds, cap 300, floor 0.30: 1,451 candidates, same `max_similarity` (1e-5) and `best_seed`, 0 mismatches; the cap was detected on all 5 seeds. |
| It equals the per-seed SQL (`ORDER BY … LIMIT`) | 300,000 rows × 64 dims, S = 2, 10, 30: identical `(seed, id)` hit sets. |
| One scan of the table whatever S is | `EXPLAIN ANALYZE`: `Seq Scan on big t (actual rows=300000 loops=1)` for S = 2, 10, 30. **My first draft (`FROM docs t CROSS JOIN seeds s CROSS JOIN LATERAL …`) did not guarantee this**: with 2 seeds the plan scanned the table twice (`loops=2`). Making the lateral subquery iterate the seeds (so it depends on `t`) fixes it. |
| `OFFSET 0` prevents double evaluation | Without it the plan shows `1 - (t.embedding <=> s.q)` in both the output and a join filter. With it, one evaluation per pair. |
| `enable_indexscan = off` gives exact search despite an HNSW index | With the index the plan is `Limit` over the index; with the setting off it is `Limit → Sort` over a seq scan. The [PostgreSQL docs](https://www.postgresql.org/docs/current/runtime-config-query.html) say `enable_indexscan` covers index-scan and index-only-scan plan types, and note it is impossible to suppress sequential scans entirely (the reverse of what we need). |
| Read-only transaction | psycopg `conn.read_only = True`; `CREATE TABLE` fails with `ReadOnlySqlTransaction`. |
| Server-side cursor | `conn.cursor(name=…)` with `itersize` streamed 20,000 rows inside the read-only transaction. The psycopg [cursor docs](https://www.psycopg.org/psycopg3/docs/advanced/cursors.html) do not mention itersize or transactions; the behaviour above was observed, not documented. |
| Stop | `Connection.cancel()` called from another thread interrupted a running query with `QueryCanceled: canceling statement due to user request`. The psycopg [docs](https://www.psycopg.org/psycopg3/docs/api/connections.html) say `cancel()` is deprecated in libpq 17 and to use `cancel_safe()` (added in psycopg 3.2) where possible, which falls back to the same behaviour on older libpq, and do not address cross-thread use; the cross-thread call worked in the test. **Use `cancel_safe()`** if present. |
| `statement_timeout` | `SET LOCAL statement_timeout='1s'` raised `QueryCanceled: canceling statement due to statement timeout`. |
| Zero vectors | `'[0,0,0]' <=> '[1,2,3]'` is `NaN` and `1 - NaN >= 0.3` is true, so the unguarded query returned the zero row; `AND d.sim <> 'NaN'` removed it. **This corrected D5** (my earlier claim was wrong). |
| Speed | On a 300,000 × 64 table that fits in memory: S = 2: 0.2 s vs 0.1 s per-seed loop; S = 10: 0.5 s vs 0.4 s; S = 30: 1.2 s vs 1.3 s. **No speed-up when cached**, as expected. The I/O saving on a table larger than memory was **not** measured. |
| LATERAL semantics | The PostgreSQL [docs](https://www.postgresql.org/docs/current/queries-table-expressions.html) describe a lateral item as evaluated once per row of the table it references, matching the `loops` counts. CTE inlining and `MATERIALIZED`: [docs](https://www.postgresql.org/docs/current/queries-with.html). |

**Not verified:** pgvector 0.8+ (iterative scan, `index` mode), tables larger than memory (the I/O saving and the ranking sort spilling to disk), `halfvec` columns, managed services (RDS, Cloud SQL, Supabase) and their default timeouts, and pgvector versions other than 0.6.0.

## Tables with no index (very large, rarely queried)

Supported, and it is the case `exact` mode is built for: it needs no index and never looks for one, so a table with no index at all works the same as an indexed one. Nothing in Check store treats a missing index as a problem in `exact` mode (it only warns in `index` mode, where an index is the whole point). What changes is cost, so the spec adds these:

- **Say it is slow, honestly.** In `exact` mode the whole seed set is one full scan of the table, however many seeds there are (previous section, with the cost caveat there); only `index` mode, which needs an index anyway, runs a query per seed. Check store shows the planner's row estimate and, in `exact` mode with no usable index, a plain note: `No index: the search scans the whole table (~N rows).` Informational, not a warning; the user chose this.
- **Progress and Stop work.** The Search screen shows elapsed time and candidates received so far (see previous section) and lets the user cancel. Cancelling a worker thread blocked in a driver call does not interrupt the query, so on Stop the code calls `connection.cancel()` (psycopg's way to ask the server to cancel the running statement; **verify in the psycopg docs**) and closes the connection. Otherwise an abandoned multi-minute scan keeps running on the server.
- **Server timeouts are the user's, not ours.** We do not override `statement_timeout`; an admin may have set one on purpose. If a scan hits it, the error shown is Postgres's own (`canceling statement due to statement timeout`) plus `Fix: raise statement_timeout for this role, or set pg_statement_timeout_s in config.toml`. Optional field `pg_statement_timeout_s` (default unset = the server's setting); when set, `SET LOCAL statement_timeout` is issued. Setting it to `0` means no limit.
- **Memory.** Nothing is sorted on the server: the lateral lookup is per row and the result is streamed. Python holds one dict entry per candidate item, as `build_candidates` does today. The integration test should include a table large enough to confirm both, and note `work_mem` if the plan spills.

What this spec does **not** promise: speed. A table of tens of millions of 1,536-dimension vectors will take a long time (minutes at least) for the one scan on typical hardware; I have not measured it. That is inherent to exact search without an index; the product answer is the progress display, working Stop, and the honest note in Check store.

## Config

`.hunches/config.toml` gains (all optional, only read when `backend = "pgvector"`):

| Field | Default | Notes |
|---|---|---|
| `backend` | `"local"` | now `Literal["local", "s3", "pgvector"]` |
| `pg_table` | — | required for pgvector; `schema.table` or `table` |
| `pg_id_column` | `"id"` | |
| `pg_text_column` | `"text"` | |
| `pg_vector_column` | `"embedding"` | `vector` or `halfvec` column |
| `pg_url_var` | `"HUNCHES_PG_URL"` | name of the env var / keyring entry holding the URL |
| `pg_search` | `"exact"` | `"exact"` or `"index"` |
| `pg_statement_timeout_s` | unset | seconds; unset = the server's `statement_timeout`; `0` = no limit |
| `embedding_model` | — | required, as for S3 |

Switching backend in Project settings writes only the active backend's fields and sets the others to `None` (002 rule, unchanged). Old configs have none of these and load unchanged.

## UI

- **New project** (`screens/new_project.py`): Backend Select gets a third option `PostgreSQL (pgvector)`. A `#pg` section (shown like `#s3`): table, id/text/vector column, URL variable (with a status word `env` / `keyring` / `missing` from `keys.status` and a **Save URL…** that stores it in the keyring via `keys.save`, input masked), search mode Select (Exact / Index), embedding model (picker). Required: location, table, embedding model. **Check store** runs in a thread worker like S3's `get_index` and is the only network call on the screen: it opens the connection read-only and shows
  - the vector column's type and dimension (`format_type(atttypid, atttypmod)` from `pg_attribute`), with a WARNING when the column is not `vector`/`halfvec`,
  - the planner row estimate (`pg_class.reltuples`; **not** `count(*)`, which is a full scan),
  - the indexes on the column and their operator class, with a WARNING in `index` mode when none uses `vector_cosine_ops` (the index would not be used by `<=>`; the README says the operator class must match the operator). In `exact` mode no index is required: with none, it shows the informational `No index: the search scans the whole table (~N rows).`,
  - a one-row sample (id and the first 60 characters of text), proving the column mapping works.
  The exact catalog queries are to be verified against the PostgreSQL docs in the task; do not copy them from this spec.
- **Project settings** (`screens/project_settings.py`): same section, same Check store, same consequence confirmation as S3 (changing table/columns/model says "Candidates were generated from the old corpus/model; re-run Search").
- **Projects** (`screens/projects.py`): Backend column `pgvector`; Where column `table` (never the URL or host).
- **Status** (`system.project_status`, `app.open_project`): pgvector projects show `OK (pgvector not checked)`; the allow-list in `open_project` gains it, as for S3. No network on open.
- **Search screen** (`screens/search.py`): `cap_warning(top_k)` says `S3 returned its cap…` today; it becomes backend-aware (`WARNING: <backend> returned its cap of N hits …`), and `search.S3_TOP_K` is joined by `search.PG_TOP_K`. The `APPROXIMATE` warning above shows for `pg_search = "index"`. A connection failure surfaces in the existing `#error` line with the exception text, **with the URL's password removed** (see Errors).
- Every new widget works at 80×24; add the new section to the `tests/test_sizes.py` sweep. Keys and buttons follow the `key_button` rule.

## Errors

| Situation | Message (the Search screen shows it in `#error`) |
|---|---|
| `psycopg` not installed | `The pgvector backend needs psycopg: pip install hunches[pg]` |
| URL var unset and not in keyring | `config.toml: pg_url_var HUNCHES_PG_URL is not set (environment or keyring)` |
| `pg_table` missing | `config.toml: pg_table is required for pgvector` |
| Connection/auth/SQL error | The driver's message, passed through a scrubber that replaces the URL and, defensively, the password portion with `***`. Never print the URL. |
| Table or column missing | The Postgres error text (it names the object). |
| Column dimension ≠ query dimension | Postgres raises on the distance operator; pass its message through and append `Fix: embedding_model in .hunches/config.toml must be the model the table was embedded with.` |

## What changes in the code

- `pyproject.toml`: extra `pg = ["psycopg[binary]"]`; add `psycopg` to the dev group so `ty` and tests can import it (as boto3 is handled today: check how and mirror it).
- `files.py`: `Config.backend` literal, the new fields (above), and a validator that the pgvector fields are present when `backend == "pgvector"`. Verify what, if anything, already validates the S3 fields before adding this; do not add a validator S3 lacks.
- `search.py`: a third branch in `search()` (a plain `if`/`elif`, not a class) for `index` mode, `PG_TOP_K`, and one new function `search_pg_exact(vectors, floor)` returning one hit list per seed (the single-query path, D10). Local and S3 are untouched.
- `candidates.py`: `build_candidates` takes one `if` to get its per-seed hit lists from `search_pg_exact` instead of calling `search()` per seed, for `pgvector` + `exact`; the merge, sort, write and meta code is shared and unchanged. Docstring `S3 topK cap` → `backend cap`.
- `system.py`: `project_status` (one line), no schema change (D8).
- `screens/new_project.py`, `screens/project_settings.py`, `screens/projects.py`, `screens/search.py`, `app.py:857`: as under "UI".
- Docs: `README.md` (install `hunches[pg]`, a "pgvector" paragraph next to "S3 Vectors" at line ~95, the env var), `AGENTS.md` (Stack, Layout, "Needs a human"), and 001's "other vector backends" out-of-scope line is superseded by this spec (note it in the "Behaviour that changes" section below).
- `.github/workflows/ci.yml`: optional job for the integration test (below).

## Tests

All default-run tests are offline.

- **Stubbed connection (fast tier).** A fake `psycopg.connect` whose cursor records the SQL and parameters and returns canned rows, in the style of `FakeS3` in `tests/test_search.py`. Assert: results are `(id, text, similarity)` sorted best first with only `sim >= floor` kept (floor inclusive, hand-computed values); `capped` is true only when some seed returns exactly `PG_TOP_K` hits (use a small `PG_TOP_K` via monkeypatch); the `NaN` guard and the `OFFSET 0` / `LATERAL` / `MATERIALIZED` shape are asserted on the SQL text; `exact` sends **one** query for any number of seeds (assert the fake saw exactly one `execute` with all seed vectors in one parameter) and issues `SET LOCAL enable_indexscan = off`, `index` issues `hnsw.iterative_scan` and one query per seed; the rows `search_pg_exact` returns feed `build_candidates` to the same `candidates.jsonl` as the per-seed path would for the same data (hand-built, ties to the earlier seed); the connection is read-only; identifiers are quoted (a column named `"text"; DROP TABLE x` stays an identifier); the vector parameter is a text literal; missing `psycopg`, missing URL var, missing table each give the exact message in "Errors"; a connection error containing the URL does not leak the password.
- **Config:** old configs load; a pgvector config round-trips; switching backend nulls the other backend's fields.
- **Screens (Pilot):** New project with pgvector chosen (required fields, Check store with a stubbed connection showing dimension and the opclass warning, Create writes the expected `config.toml` and no URL anywhere in it); Project settings switch S3 → pgvector with the confirmation; Projects row shows `pgvector` and the table; Search shows the cap warning and the `APPROXIMATE` warning. Add to the size sweep.
- **No-index table (stubbed + integration):** a config with `pg_search = "exact"` and a table with no index searches normally; Check store shows the no-index note and no WARNING; in `index` mode with no index it shows the WARNING. Stop calls `cancel()` on the stub connection and closes it; `pg_statement_timeout_s` issues `SET LOCAL statement_timeout` with the value, and `0` is passed through (not treated as unset). The integration test also runs `exact` against a table created with no index, and compares its candidates (ids, `max_similarity`, `best_seed`) with the local backend on the same vectors with several seeds, including a tie; it also reads `EXPLAIN` to check the single-pass plan.
- **Secret leak test:** after Create, grep `config.toml`, `system.json` and every `.hunches/` file for the password used in the test.
- **Integration (optional, skipped unless `HUNCHES_TEST_PG_URL` is set):** against a real database with pgvector (CI service container using the `pgvector/pgvector` image): create a table with a few hundred random unit vectors and an HNSW `vector_cosine_ops` index, then assert `exact` equals the numpy result on the same vectors, and show what `index` mode returns under the default settings so the "hides hits" claim in this spec is measured, not assumed. This is the only way to resolve the verification list above; it needs no cloud account.

## Behaviour that changes in 001–004

- 001 "Out of scope: other vector backends" is no longer true; pgvector is the third. The "Vector search" section gains the pgvector paragraph (this spec's "Why exact is the default" is the reference).
- 002 New project / Project settings gain a third backend; "S3 stores" behaviour is unchanged and there are no saved Postgres stores (D8).
- 003/004: nothing. `candidates.jsonl` and `candidates.meta.json` are backend-independent.

## Out of scope

Creating or loading a table, creating an index, embedding a corpus, writes of any kind, SSH tunnels, connection pooling (one short connection per query, like S3's one client per call), other databases, hybrid (keyword + vector) search, metadata filters, saved Postgres stores (D8).

## Proposed tasks

Same one-commit-per-task, red/green TDD process as 004.

| # | Task | Depends on |
|---|------|-----------|
| 01 | Config fields, `pg` extra, `search()` `index` branch, `search_pg_exact` + `build_candidates` branch (stubbed), errors and scrubber | — |
| 02 | Check-store function (catalog queries verified against PostgreSQL docs) | 01 |
| 03 | New project: third backend, URL status/save, Check store | 01, 02 |
| 04 | Project settings, Projects, status allow-list, Search warnings | 01 |
| 05 | Integration test + optional CI job; size sweep | all |
| 06 | README, AGENTS.md, 001/002 notes | all |

## Open items

- **ask:** whether `exact` should be the default (D4). My recommendation is yes.
- **ask:** saved Postgres stores in `system.json` (D8). My recommendation is defer.
- `index` mode needs pgvector 0.8+ for iterative scans; the build container only had 0.6.0, so that mode's `SET LOCAL` names and its recall are unverified. Task 05 runs them against the `pgvector/pgvector` image.
- `halfvec` columns need a `::halfvec` cast on the query, and the README caps indexed `halfvec` at 4,000 dimensions vs 2,000 for `vector`. Task 01 picks the cast from the column type reported by Check store, or supports `vector` only and says so; decide when implementing.
- **Needs a human:** a PostgreSQL instance with pgvector and an embedded table for the manual end-to-end check, and the "Not verified" list above (tables larger than memory, managed services, pgvector 0.8+). Agents cannot fake these.
