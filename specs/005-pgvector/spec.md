# 005 — pgvector backend

Status: approved by Chris 2026-10-09 (exact default, 512 MB limit, refuse `index` below 0.8.0, IAM in scope); implementation in progress on `claude/intelligent-turing-asvhrl`, to be merged only after Chris has tested it against his RDS database. Builds on `../001-initial-version/spec.md`, `../002-onboarding-setup/spec.md`, `../003-tui-redesign/spec.md` and `../004-history-and-redo/spec.md`, all implemented. Written 2026-10-09 against `main` at `c8ebdf1`.

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
| D1 | Driver | **psycopg 3**, optional extras `pg = ["psycopg[binary]"]` and `rds = ["psycopg[binary]", "boto3"]` (the second only for IAM authentication, D11), imported lazily inside `search()` with the same "needs … `pip install hunches[pg]`" error as boto3. The query vector is sent as a text literal cast in SQL (`%s::vector`), so the separate `pgvector` Python package is not needed. | The pgvector README shows vectors as text literals (`'[1,2,3]'`); the `pgvector` package is only needed to register adapter types ([README](https://github.com/pgvector/pgvector#readme), [pgvector-python](https://pypi.org/project/pgvector/)). Binary-wheel behaviour of `psycopg[binary]` is from memory: verify against the psycopg install docs in task 01. |
| D2 | Table layout | **Configurable table and column names with defaults**: `pg_table` (required, may be schema-qualified `schema.table`), `pg_id_column="id"`, `pg_text_column="text"`, `pg_vector_column="embedding"`. The corpus is "already embedded" by someone else, so a fixed schema would be wrong. All identifiers are composed with `psycopg.sql.Identifier`, never string-formatted. | Mirrors S3, where `key` is the id and `metadata.text` the text. |
| D3 | Where the connection URL lives | **Environment variable first, then the OS keyring**, through the existing `keys.status/save` (which already work for any variable name). Config stores only the variable name: `pg_url_var`, default `HUNCHES_PG_URL`. `keys.VARS` stays LLM-only, so `load_into_env` is unchanged; `search` resolves the URL itself with `os.environ.get(var) or keys._stored(var)`. | `keys.py` takes a `var` argument everywhere. |
| D4 | Exact vs approximate search | `pg_search = "exact"` (default; Chris agreed 2026-10-09) or `"index"`. **Exact** answers **all seeds in one query** (D10) with a query shape that cannot use an ANN index, so the result equals the local numpy backend (up to the per-seed cap). **Index** lets an HNSW/IVFFlat index answer, one query per seed, with iterative scan (pgvector 0.8.0+, D9); it shows an `APPROXIMATE` warning on the Search screen every time. | See "Why exact is the default". |
| D5 | Similarity | `similarity = 1 - (column <=> query)`. pgvector documents cosine similarity as 1 minus cosine distance and `<=>` as cosine distance ([README](https://github.com/pgvector/pgvector#readme)); unlike S3 Vectors (001 open item), this is documented, not assumed. The operator is norm-invariant, so the corpus need not be normalised. **A zero vector gives distance `NaN`, and in Postgres `NaN` compares greater than every number, so `1 - NaN >= floor` is TRUE** (checked on PostgreSQL 16 + pgvector 0.6.0: a zero row passed the floor). The SQL therefore also requires `sim <> 'NaN'` (in Postgres `NaN = NaN` is true, so `isnan()`, which does not exist for `double precision`, is not needed). The local backend gives such rows similarity 0. | pgvector README; `candidates.FLOOR`; tested 2026-10-09, see "Verified on a real database". |
| D6 | Result cap | **Top `PG_TOP_K = 10_000` per seed in both modes** (Chris, 2026-10-09), same as S3 so the existing cap warning applies. `capped` is true when some seed has exactly `PG_TOP_K` hits. In `exact` mode the cap is applied per seed inside the single query (a window function; see below). In `index` mode it is the `LIMIT` the index needs anyway, and the permanent `APPROXIMATE` warning also applies. | S3 precedent (`search.S3_TOP_K`). |
| D7 | Embedding model | Recorded in `config.toml` as `embedding_model` (as for S3), chosen with the model picker. There is no `meta.json` in a table, so hunches cannot detect a mismatch by itself; **Check store** (below) reports the column dimension so a human can compare it with the model's. | 002 New project, S3 path. |
| D8 | Saved stores in `system.json` | **Not in this spec.** S3 stores exist so one bucket/index can back several projects (002). For Postgres the reusable parts are a secret (already shared by `pg_url_var`) and five short fields with defaults. Adding `pg_stores` also means a `system.json` schema change; defer until someone asks. | Minimal implementation. **ask.** |
| D9 | pgvector version | **`exact` mode has no version floor beyond "the `vector` extension is installed"** (tested on 0.6.0 and 0.8.1; older versions untested, so none is promised). **`index` mode needs 0.8.0+** (iterative scans; [changelog](https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md)). **`halfvec` columns exist only in 0.7.0+**, so a table that has one is already on 0.7.0+. hunches reads `pg_extension.extversion` at the start of every search (same connection, one tiny query) and, in `index` mode on < 0.8.0, stops before issuing any `SET` with a message that names the found version. See "Versions". | Changelog: HNSW 0.5.0, halfvec 0.7.0, iterative scans 0.8.0. |
| D10 | One query for all seeds | **Yes, for `exact`.** One scan of the table answers every seed, and the per-seed top-`PG_TOP_K` cap is kept, so the result is exactly what the per-seed loop would produce (`build_candidates` then merges per seed as today: highest similarity wins, ties to the earlier seed). `index` mode stays one query per seed: a per-row lateral lookup cannot use an ANN index. | Tested against numpy and against the per-seed SQL, 2026-10-09. |
| D11 | Authentication | Two modes, `pg_auth = "url"` (default: the full URL, password included, from the environment or keyring) and **`"rds_iam"`: RDS / Aurora IAM database authentication**. See "Authentication". | Chris, 2026-10-09: in this spec; he will test it against his RDS instance. |
| D12 | Result-size limit | **System-level** (`system.json`, `pg_max_result_mb`, default 512, editable in System settings, applies to every pgvector project on the machine); not a per-project field. `0` = no limit. | Chris, 2026-10-09. |

## Why exact is the default

`hunches` asks "every item at or above this similarity", not "the 10 nearest". pgvector's approximate indexes answer a `ORDER BY … LIMIT k` query by walking a graph with a candidate list of `hnsw.ef_search` (default 40), and "with approximate indexes, filtering is applied after the index scan" ([README](https://github.com/pgvector/pgvector#readme)). So an index-backed query asking for 10,000 rows returns about 40 unless iterative scan is on, and with iterative scan it still stops at `hnsw.max_scan_tuples` (default 20,000, approximate), after which it "will still return fewer than LIMIT rows". None of these is an error, and a short result is indistinguishable from "that is all there was". The local backend and S3 Vectors do not have this failure mode, and the whole pipeline (candidate pool, gold sampling, coverage) assumes the pool is complete.

Hence:

- **`exact` (default):** see "One query for all seeds" below. No index is used or needed (the query shape cannot use one), there is no `LIMIT` on the table scan, and the distance floor is applied in SQL.
- **`index`:** one query per seed (`SELECT id, text, 1 - (vec <=> q) AS sim FROM t WHERE … ORDER BY vec <=> q LIMIT PG_TOP_K`, the shape an index needs), but `SET LOCAL hnsw.iterative_scan = relaxed_order` (results may be slightly out of order; we re-sort client-side) and `SET LOCAL hnsw.max_scan_tuples = <PG_MAX_SCAN>`, with `WHERE 1 - (vec <=> q) >= floor` pushed into SQL so the scan continues until `LIMIT` or `max_scan_tuples`. Always shows: `WARNING: APPROXIMATE pgvector search; the index may hide hits above the floor. Switch to exact in Project settings for a complete pool.` (The 1000 upper bound of `ef_search` I remember is **not** in the README; do not hard-code it. Set only the parameters named here.)

**Measured (see "Verified on a real database"):** on a 300,000-row table with an HNSW index and one seed whose true hit count above the floor was 1,296, an index query with the default settings returned **40** hits; with `hnsw.iterative_scan = relaxed_order` **884**; with `strict_order` **547**; raising `hnsw.max_scan_tuples` to 1,000,000 did not add any. (Synthetic random vectors, one seed, pgvector 0.8.1; indicative, not a benchmark.) The silent shortfall this spec is designed around is real.

## One query for all seeds (`exact`)

Yes: one scan of the table returns the candidates for every seed, with the top-`PG_TOP_K` cap applied **per seed**. The seed vectors are embedded first (as today, cached) and sent once as a text array. Every (row, seed) similarity is computed once; pairs below the floor (or `NaN`) are dropped; the survivors are ranked within each seed; the top `PG_TOP_K` of each seed are returned **without their text**. A second, cheap query then fetches the text of the distinct ids.

Both queries run in one read-only `REPEATABLE READ` transaction (one snapshot), so a table being written to during a long scan cannot give inconsistent results.

```sql
-- step 1: ids only, so the sort carries a few bytes per pair, not the document text
WITH seeds AS MATERIALIZED (
  SELECT u.i - 1 AS i, u.q::{vtype} AS q          -- parse each seed once, not once per row
  FROM unnest(%s::text[]) WITH ORDINALITY AS u(q, i)
),
pairs AS (
  SELECT t.{id} AS id, d.i, d.sim
  FROM {table} t
  CROSS JOIN LATERAL (                              -- refers to t, so the table is the outer side:
    SELECT s.i, 1 - (t.{vec} OPERATOR({schema}.<=>) s.q) AS sim   -- it is scanned once, whatever S is
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
SELECT id, i, sim FROM ranked WHERE rn <= {PG_TOP_K};

-- step 2: text for the distinct ids (an index lookup when there are few, a scan when there are many)
SELECT {id}, {text} FROM {table} WHERE {id} = ANY(%s);
```

`{vtype}` is the schema-qualified type of the vector column (`vector` or `halfvec`, see "Column types and schemas") and `{schema}` the schema that holds the extension. The query vectors are sent as `[x,y,…]` text literals. The exact query does **not** change any planner setting: it has no `ORDER BY` on a distance, so no ANN index can answer it (checked: on a table with an HNSW index every plan was a plain sequential scan). Each of `OFFSET 0`, the `LATERAL` over `t`, the `MATERIALIZED` CTE, the `NaN` test, and the two-step text fetch is there for a reason shown below; do not "simplify" them away without re-running the checks.

**Result.** Step 1 returns at most `S × PG_TOP_K` rows `(id, seed index, similarity)`; step 2 returns text for the distinct ids. `search.search_pg_exact(vectors, floor)` joins them into one hit list per seed (`list[list[(id, text, sim)]]`, best first) plus `capped` (any seed with exactly `PG_TOP_K` rows). `build_candidates` takes a plain `if config.backend == "pgvector" and config.pg_search == "exact":` to get those lists in one call instead of calling `search()` per seed; **the merge, sort, write and meta code below it is unchanged**, so the output is identical to the per-seed path. Ids are passed back to step 2 in the type the driver returned them (text, integer, uuid) and converted with `str()` only when building hits, so an integer or uuid id column still uses its index. Local, S3 and `index` mode are untouched.

**Cost, honestly.** The table is read once, but the database still computes S × N distances and ranks the pairs that pass the floor. The saving over S separate scans is **I/O**, which matters when the table does not fit in cache; when it does fit, the work is CPU-bound and one query is no faster than S queries (measured below). Other reasons to prefer one query: one pass over a table too big to cache, one round trip, one `statement_timeout`, one Stop, one progress display.

**Streaming and progress.** Both queries are read with a server-side (named) cursor in batches. One query has no per-seed progress, so the Search screen shows running time and rows received; `progress` is called as `(received, 0, "")` on this path and the screen handles the zero-total case (`LabelBar` has no total; test at 80×24).

## Versions

- hunches never creates or upgrades the extension. At the start of each search (and in Check store) it runs `SELECT extversion FROM pg_extension WHERE extname = 'vector'` on the connection it already has. No row: `The vector extension is not installed in this database (CREATE EXTENSION vector needs a DBA).` Otherwise the version is parsed as integers (`0.8.1` → `(0, 8, 1)`; any non-numeric suffix ignored) and shown in Check store.
- `exact`: no version check beyond presence (D9).
- `index`: `< (0, 8, 0)` stops with `pg_search = "index" needs pgvector 0.8.0 or newer (found 0.6.0). Use pg_search = "exact", or upgrade the extension.` before any `SET`. The same text appears next to the mode selector when Check store has seen the version.
- A column of type `halfvec` on a pre-0.7.0 server cannot exist, so no separate check.
- Managed services lag upstream: per AWS's announcements, [RDS for PostgreSQL](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-rds-for-postgresql-pgvector-080/) offers 0.8.0 from engine versions 17.1, 16.5, 15.9, 14.14 and 13.17, and [Aurora PostgreSQL](https://aws.amazon.com/about-aws/whats-new/2025/04/pgvector-0-8-0-aurora-postgresql) from 16.8, 15.12, 14.17 and 13.20 (April 2025). A database on an older minor version can therefore be limited to `exact`, which is why `exact` has no 0.8 requirement.

## Column types and schemas

**`halfvec`, in plain terms.** pgvector's `vector` type stores each dimension as a 4-byte float. `halfvec` (added in 0.7.0) stores 2 bytes per dimension: half the storage, a little less precision. It matters here because pgvector can build an HNSW or IVFFlat index on a `vector` column only up to 2,000 dimensions, but on a `halfvec` column up to 4,000 ([README](https://github.com/pgvector/pgvector#readme)); I confirmed the first limit (`column cannot have more than 2000 dimensions for hnsw index` on a `vector(3072)` column). So a corpus embedded with a model that outputs more than 2,000 dimensions is commonly stored as `halfvec` so that it can be indexed, and hunches must read such tables.

**Support in v1: `vector` and `halfvec`.** Anything else (`sparsevec`, `bit`, an array) is refused with `Column "embedding" has type sparsevec; hunches supports vector and halfvec.` The column's type is read from the catalog (`pg_attribute` → `pg_type` → `pg_namespace`: type name and schema; exact queries to be verified in task 02) at the start of the search and in Check store. The seed vectors are cast to that type, so the distance is computed natively. Tested on 0.8.1: a `halfvec(3072)` column with 3,000 rows gave similarities within 2e-5 of numpy float32; casting the seeds to `vector` also ran (Postgres has a cast), but the native type is the right one.

**Schemas.** Some services install the extension outside the default search path: Supabase's own [guide](https://supabase.com/docs/guides/database/extensions/pgvector) enables it with `create extension vector with schema extensions`. Tested: with the extension in schema `extensions` and the default `search_path`, `'[1,2,3]'::vector` fails (`type "vector" does not exist`) and so does the bare `<=>`; `'[1,2,3]'::extensions.vector` with `OPERATOR(extensions.<=>)` works. So the query uses the schema of the column's own type for both the cast and the operator, all quoted with `psycopg.sql.Identifier`, and never depends on `search_path`.

## Result size and memory guards

There are two different places "too much data" can pile up, and they need different guards.

**1. On the server (the ranking sort).** The sort in step 1 holds one small row per (item, seed) pair that clears the floor. Measured on 300,000 rows × 10 seeds with the floor at 0.0 (every pair passes: 3,000,000 pairs) and `work_mem` at 4MB:

| Variant | Sort | Time |
|---|---|---|
| Text carried through the sort (my first draft) | spilled **2,046,896 kB** (about 2 GB) to disk, rows of 1 KB text | 12.6 s |
| Ids only, text fetched after (this spec) | spilled 78,448 kB (about 78 MB) | 5.0 s |

Postgres does not run out of memory here: a sort that exceeds `work_mem` spills to temporary files on the server's disk, and the table is streamed by a sequential scan (observed: 4MB and 64kB `work_mem` both completed, 80 MB spill). The risk is disk, not RAM, and the setting that caps temporary-file space, `temp_file_limit`, has context `superuser` (`pg_settings`), so a read-only role on RDS, Aurora or Supabase cannot set it. hunches therefore does three things:
- Keep the sort narrow (the two-step query above: a 26x smaller spill in the test).
- Show, in Check store and before a search, the worst-case pair count `S × estimated rows` with the note `A low floor on a large table sorts up to this many pairs on the server (spills to temporary files). Ask your DBA about temp_file_limit.`
- Honour Stop and `pg_statement_timeout_s`; both end the query on the server.

**2. In hunches (the result).** Bounded by construction: at most `S × PG_TOP_K` rows. But rows carry text, so that bound can still be large (30 seeds × 10,000 × 2 KB = 600 MB). **The escape hatch is the system-level setting `pg_max_result_mb`** (D12; default **512** MB, `0` = no limit; stored in `system.json`, edited in System settings, read at the start of every search):
- **Before the scan starts** (the failure that matters is the one that comes after a ten-minute scan), hunches reads the column's average width from the planner statistics (`pg_stats.avg_width` for the text column; **verify the view and column names in task 02**) and computes the worst case `S × PG_TOP_K × (avg_width + overhead)`. If that exceeds the limit it refuses to start: `Search could return up to ~N MB (S seeds × 10,000 hits × ~W bytes) which exceeds the result limit of 512 MB. Use fewer seeds or raise the limit in System settings (F5).` No statistics (table never analysed) skips this check.
- **While streaming**, hunches counts bytes received (id + text + a fixed per-row overhead) and when the limit is passed it calls `cancel_safe()`, closes the connection and raises the same message with the real count. Tested: a named cursor over a 303 MB result stopped after 4,931 rows / 5.0 MB against a 5 MB budget, without reading the rest.
- Python's merge dict holds one entry per distinct candidate, never more than the rows received, so it is covered by the same limit.

A hard failure is deliberate: a partial candidate list would silently change stage 2's results.

## Managed services (RDS, Aurora, Supabase, other hosted Postgres)

Requirement from Chris: any managed service must work. hunches needs only a login that can `SELECT` from the table and a `vector` extension someone else installed; it never creates anything and needs no superuser, so the privileges are the same on every host. What differs is below; each item says whether I tested it, read it in docs, or could not check.

| Concern | What hunches does | Basis |
|---|---|---|
| Connection string and TLS | The URL is passed to psycopg/libpq unchanged, so `?sslmode=require` / `verify-full` and `sslrootcert=` work as the host documents. Check store shows whether the connection is encrypted (`SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()`; the view exists, local value was `false` as expected; not tested against a TLS server). Supabase [recommends](https://supabase.com/docs/guides/database/connecting-to-postgres) SSL on all connection types and `verify-full` for verification. | docs; partly tested |
| Extension in another schema | Schema-qualified cast and operator taken from the column's type (above). | **tested** (local schema `extensions`); Supabase's schema from its docs |
| Poolers in transaction mode (Supabase port 6543, PgBouncer, RDS Proxy) | psycopg is opened with `prepare_threshold=None` (never auto-prepare): the psycopg [docs](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html) say poolers are not compatible with prepared statements unless they declare otherwise, and Supabase [says](https://supabase.com/docs/guides/database/connecting-to-postgres) transaction mode does not support them. Everything runs inside **one transaction** (`SET LOCAL`, the named cursor, both queries), which is the only thing transaction mode guarantees; Supabase notes cursors work only within a single transaction. | docs; the single-transaction design is mine and **not tested against a pooler** |
| Long queries through a pooler | Check store notes when the URL's port or host looks like a transaction pooler (6543, or a `pooler.` host) and suggests the direct or session-mode URL for the search. This is a hint, not a block. | docs; heuristic |
| Server-side timeouts | Supabase's own [guide](https://supabase.com/docs/guides/database/postgres/timeouts) lists default role timeouts (anon 3 s, authenticated 8 s, `postgres` capped at 2 min by a global default; one copy of the page looked garbled, so confirm there) and shows `alter role … set statement_timeout`. A full scan on a large table can exceed them. Our error carries the hint from "Tables with no index"; `pg_statement_timeout_s` overrides it for the one transaction with `SET LOCAL`. Whether `SET LOCAL` is honoured through a given pooler is untested. | docs; untested |
| Read replicas (RDS replicas, Aurora readers) | Allowed (the transaction is read-only anyway). A long query on a replica can be cancelled by replication: `canceling statement due to conflict with recovery`, a standby setting (`max_standby_streaming_delay`, [default 30 s on the source I found](https://docs.azure.cn/en-us/postgresql/troubleshoot/troubleshoot-canceling-statement-due-to-conflict-with-recovery)). hunches recognises that message and adds `Fix: run the search against the primary/writer endpoint, or a replica configured for long queries.` The sources I found were general PostgreSQL and Azure; Aurora's behaviour may differ. | docs (not AWS-specific); error hint only |
| IAM / token authentication (RDS, Aurora) | In scope (D11); see "Authentication". | AWS docs; **untested against a real instance** until Chris runs it |
| Connection limits, IP allow-lists, VPN / bastion / SSH tunnel | Out of scope; the user arranges network access. Supabase's direct host is IPv6 unless the project has the IPv4 add-on; the shared pooler is IPv4 only ([docs](https://supabase.com/docs/guides/database/connecting-to-postgres)). | docs |
| Extension version lag | Handled by "Versions": `exact` works without 0.8. | docs |

**Cannot be tested in the build container:** every managed service above (no network access to AWS or Supabase, and no accounts). The acceptance for this requirement is a manual checklist in task 05 that a human runs once per service: Check store, an `exact` search on a small table, a search that deliberately exceeds the host's statement timeout (to see the hint), and the pooler URL variants. **Needs a human.**

### Verified on a real database (2026-10-09)

PostgreSQL 16.15 (Ubuntu package) in the build container. pgvector **0.6.0** (apt) for the first checks and **0.8.1** (built from the `v0.8.1` tag) for the later ones, as marked; psycopg **3.3.6**. Scripts were scratch, not committed; task 05 turns them into the integration test.

| Claim | Result |
|---|---|
| The query equals the numpy per-seed reference | 0.6.0: 20,000 rows × 32 dims, 5 seeds, cap 300, floor 0.30: 1,451 candidates, same `max_similarity` (1e-5) and `best_seed`, 0 mismatches. **0.8.1, final two-step form, with two true zero vectors in the table:** 1,450 candidates, 0 mismatches, zero-vector rows excluded, text fetched for every candidate, cap detected on all 5 seeds. |
| It equals the per-seed SQL (`ORDER BY … LIMIT`) | 0.6.0: 300,000 rows × 64 dims, S = 2, 10, 30: identical `(seed, id)` hit sets. |
| One scan of the table whatever S is | `Seq Scan on big t (actual rows=300000 loops=1)` for S = 2, 10, 30. My first draft (`FROM docs t CROSS JOIN seeds s CROSS JOIN LATERAL …`) did **not** guarantee this: with 2 seeds the table was scanned twice (`loops=2`). Making the lateral subquery iterate the seeds (so it depends on `t`) fixes it. |
| `OFFSET 0` prevents double evaluation | Without it the plan shows `1 - (t.embedding <=> s.q)` in both the output and a join filter. |
| The exact query cannot use an ANN index | 0.8.1, table with a primary key and an HNSW index: every plan was `Seq Scan` only, with no planner setting changed. (An earlier version of this spec turned `enable_indexscan` off; that also blocks the primary-key lookup in step 2 and is not needed.) For `ORDER BY embedding <=> q LIMIT n` queries, turning `enable_indexscan` off did move the plan from an index scan to `Sort` over a seq scan; the PostgreSQL [docs](https://www.postgresql.org/docs/current/runtime-config-query.html) describe the setting. |
| Text join-back must be a separate query | A single query with `JOIN … ON t.id = top.id` scanned the table twice even with a primary key and one result row (the planner cannot estimate the ranked row count). The two-step form: 1 hit with a PK → `Index Scan using …_pkey` (0.02 s); 85,656 distinct ids → `Seq Scan` with a filter (0.7 s). |
| Memory behaviour | See "Result size and memory guards": 78 MB vs 2 GB spill, no out-of-memory at `work_mem` 4MB or 64kB. |
| Result-size guard | A named cursor stopped after 5.0 MB of a 303 MB result. |
| Read-only transaction | `CREATE TABLE` fails with `ReadOnlySqlTransaction`. |
| Server-side cursor | `conn.cursor(name=…)` with `itersize` streamed 20,000 rows in a read-only transaction. The psycopg [cursor docs](https://www.psycopg.org/psycopg3/docs/advanced/cursors.html) do not mention itersize or transactions; observed, not documented. |
| Stop | `Connection.cancel()` from another thread interrupted a running query (`QueryCanceled: canceling statement due to user request`). The psycopg [docs](https://www.psycopg.org/psycopg3/docs/api/connections.html) prefer `cancel_safe()` (3.2+; same behaviour on libpq < 17) and do not address cross-thread use. **Use `cancel_safe()`.** |
| `statement_timeout` | `SET LOCAL statement_timeout='1s'` raised `QueryCanceled: canceling statement due to statement timeout`. |
| Zero vectors | `'[0,0,0]' <=> '[1,2,3]'` is `NaN` and `1 - NaN >= 0.3` is **true**; `AND d.sim <> 'NaN'` removes the row. Corrected D5. |
| halfvec | 0.8.1: `halfvec(3072)` column, HNSW index on it created fine; same on `vector(3072)` fails (2,000-dimension limit); exact search on the halfvec column within 2e-5 of numpy. |
| Extension in a non-default schema | See "Column types and schemas". |
| `index` mode recall | See "Why exact is the default": 40 / 884 / 547 of 1,296. |
| Speed | 0.6.0, 300,000 × 64 table that fits in memory: S = 2: 0.2 s vs 0.1 s per-seed loop; S = 10: 0.5 s vs 0.4 s; S = 30: 1.2 s vs 1.3 s. No speed-up when cached. The I/O saving on a table larger than memory was **not** measured. |
| LATERAL semantics, CTE inlining | PostgreSQL [LATERAL docs](https://www.postgresql.org/docs/current/queries-table-expressions.html) (evaluated once per row of the referenced table, matching `loops`); [WITH docs](https://www.postgresql.org/docs/current/queries-with.html) (`MATERIALIZED`). |

**Not verified:** any managed service; a transaction-mode pooler; TLS; tables larger than memory (the I/O saving, and the temp-file spill at scale); `index` mode's `max_scan_tuples` plateau (why raising it to 1,000,000 added nothing; maybe `hnsw.scan_mem_multiplier`, untested); IVFFlat; partitioned tables and views as `pg_table` (the id join in step 2 should work, untested); integer and uuid id columns; pgvector versions other than 0.6.0 and 0.8.1.

## Tables with no index (very large, rarely queried)

Supported, and it is the case `exact` mode is built for: it needs no index and never looks for one, so a table with no index at all works the same as an indexed one. Nothing in Check store treats a missing index as a problem in `exact` mode (it only warns in `index` mode, where an index is the whole point). What changes is cost, so the spec adds these:

- **Say it is slow, honestly.** In `exact` mode the whole seed set is one full scan of the table, however many seeds there are (previous section, with the cost caveat there); only `index` mode, which needs an index anyway, runs a query per seed. Check store shows the planner's row estimate and, in `exact` mode with no usable index, a plain note: `No index: the search scans the whole table (~N rows).` Informational, not a warning; the user chose this.
- **Progress and Stop work.** The Search screen shows elapsed time and candidates received so far (see previous section) and lets the user cancel. Cancelling a worker thread blocked in a driver call does not interrupt the query, so on Stop the code calls `connection.cancel()` (psycopg's way to ask the server to cancel the running statement; **verify in the psycopg docs**) and closes the connection. Otherwise an abandoned multi-minute scan keeps running on the server.
- **Server timeouts are the user's, not ours.** We do not override `statement_timeout`; an admin may have set one on purpose. If a scan hits it, the error shown is Postgres's own (`canceling statement due to statement timeout`) plus `Fix: raise statement_timeout for this role, or set pg_statement_timeout_s in config.toml`. Optional field `pg_statement_timeout_s` (default unset = the server's setting); when set, `SET LOCAL statement_timeout` is issued. Setting it to `0` means no limit.
- **Memory and result size:** see "Result size and memory guards"; the system-level `pg_max_result_mb` applies here too.

What this spec does **not** promise: speed. A table of tens of millions of 1,536-dimension vectors will take a long time (minutes at least) for the one scan on typical hardware; I have not measured it. That is inherent to exact search without an index; the product answer is the progress display, working Stop, and the honest note in Check store.

## Config

`.hunches/config.toml` gains these fields, all optional, only read when `backend = "pgvector"`. **In the file they default to absent** (`write_config` omits `None`, so a local or S3 project's config is unchanged); the defaults in the "Default" column are applied when the value is read:

| Field | Default | Notes |
|---|---|---|
| `backend` | `"local"` | now `Literal["local", "s3", "pgvector"]` |
| `pg_table` | — | required for pgvector; `schema.table` or `table` |
| `pg_id_column` | `"id"` | |
| `pg_text_column` | `"text"` | |
| `pg_vector_column` | `"embedding"` | a `vector` or `halfvec` column; the type is read from the catalog, not configured |
| `pg_url_var` | `"HUNCHES_PG_URL"` | name of the env var / keyring entry holding the URL |
| `pg_search` | `"exact"` | `"exact"` or `"index"` |
| `pg_statement_timeout_s` | unset | seconds; unset = the server's `statement_timeout`; `0` = no limit |
| `pg_auth` | `"url"` | `"url"` or `"rds_iam"` (D11) |
| `pg_aws_region` | unset | `rds_iam` only; unset = boto3's default region resolution (like `s3_region`) |
| `pg_aws_profile` | unset | `rds_iam` only; a named AWS profile; unset = boto3's default credential chain |
| `embedding_model` | — | required, as for S3 |

Switching backend in Project settings writes only the active backend's fields and sets the others to `None` (002 rule, unchanged). Old configs have none of these and load unchanged.

**System level (`system.json`, per user, never in git):** one new field, `pg_max_result_mb: int = 512`. An older `system.json` without it loads with 512. `VERSION` stays 1: the field is additive and has a default; a hunches that predates it ignores the field when reading and drops it if it rewrites the file, which is the same exposure any additive field has had (002 added fields the same way).

## Authentication

`pg_auth = "url"` (default): `pg_url_var` names an environment variable, or a keyring entry, holding a full libpq URL including the password (D3).

`pg_auth = "rds_iam"`: for RDS and Aurora PostgreSQL with IAM database authentication enabled. `pg_url_var` holds a URL **without a password**: `postgresql://db_user@my-instance.abc123.us-east-1.rds.amazonaws.com:5432/mydb?sslmode=verify-full&sslrootcert=/path/global-bundle.pem`. At the start of every connection hunches asks boto3 for a token and uses it as the password:

```python
session = boto3.Session(profile_name=config.pg_aws_profile)           # None = default chain
region = config.pg_aws_region or session.region_name                   # error if neither
token = session.client("rds", region_name=region).generate_db_auth_token(
    DBHostname=host, Port=port, DBUsername=user, Region=region)        # host/port/user parsed from the URL
```

What the AWS docs say, and what follows from it ([IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html), [Python example](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.Connecting.Python.html), [IAM policy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.IAMPolicy.html)):
- A token lives 15 minutes and "is only used for authentication and doesn't affect the session after it is established". So a token is generated per connection, immediately before connecting, and never stored or refreshed; a search that runs longer than 15 minutes is unaffected. (A new token is generated for each search because each opens its own connection.)
- The host must be the real endpoint: "You cannot use a custom Route 53 DNS record instead of the DB instance endpoint to generate the authentication token." hunches uses the URL's host verbatim and says so in the error text if authentication fails.
- Tokens are large ("generally about 1 KB but can be larger") and a truncated one fails; hunches passes it to psycopg as the `password` argument, not through a URL string.
- If temporary credentials made the token, they must still be valid when connecting (docs); hunches generates the token immediately before connecting.
- The connection is encrypted (IAM database authentication runs over SSL/TLS). If the URL has no `sslmode`, hunches adds `sslmode=require`. `verify-full` with the AWS root bundle in the URL is the user's choice and is passed through.
- The database user needs the `rds_iam` role in Postgres, and the AWS identity needs `rds-db:connect` on `arn:aws:rds-db:<region>:<account>:dbuser:<DbiResourceId>/<db_user>` (for Aurora, the cluster resource id; through RDS Proxy, the proxy's `prx-…` id). hunches cannot check either; when authentication fails, the error text lists both as the likely causes.
- The sandbox cannot test this (no AWS account). Chris tests it against his own instance; the code is covered by tests with `boto3` and `psycopg` stubbed (arguments passed to `generate_db_auth_token`, the token reaching psycopg as `password`, `sslmode` defaulting, the token and URL scrubbed from errors).

Where the credentials come from is boto3's business (environment, `~/.aws`, SSO, instance role); hunches stores no AWS secrets. Errors from boto3 (no credentials, no region, expired SSO session) are shown as `AWS: <message>`.

## UI

- **New project** (`screens/new_project.py`): Backend Select gets a third option `PostgreSQL (pgvector)`. A `#pg` section (shown like `#s3`): table, id/text/vector column, URL variable (with a status word `env` / `keyring` / `missing` from `keys.status` and a **Save URL…** that stores it in the keyring via `keys.save`, input masked), search mode Select (Exact / Index), embedding model (picker). Required: location, table, embedding model. **Check store** runs in a thread worker like S3's `get_index` and is the only network call on the screen: it opens the connection read-only and shows
  - the pgvector version (`extversion`), the extension's schema, and whether the connection is encrypted,
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
| `rds_iam` without boto3 | `IAM authentication needs boto3: pip install hunches[rds]` |
| `rds_iam`, no credentials / region | `AWS: <botocore message>`; `pg_aws_region is not set and boto3 found no default region` |
| `rds_iam`, authentication failed | The server's message, then `Check: the database user has the rds_iam role, the AWS identity may rds-db:connect on this DbiResourceId/user, and the URL host is the instance endpoint (not a custom DNS name).` |
| Extension missing | `The vector extension is not installed in this database (CREATE EXTENSION vector needs a DBA).` |
| `index` mode on pgvector < 0.8.0 | `pg_search = "index" needs pgvector 0.8.0 or newer (found X). Use pg_search = "exact", or upgrade the extension.` |
| Unsupported column type | `Column "embedding" has type sparsevec; hunches supports vector and halfvec.` |
| Result too large (before or during) | `Search could return up to ~N MB … exceeds the result limit of 512 MB. Use fewer seeds or raise the limit in System settings (F5).` |
| Replica conflict | Postgres text, then `Fix: run the search against the primary/writer endpoint, or a replica configured for long queries.` |
| Column dimension ≠ query dimension | Postgres raises on the distance operator; pass its message through and append `Fix: embedding_model in .hunches/config.toml must be the model the table was embedded with.` |

## What changes in the code

- `pyproject.toml`: extras `pg = ["psycopg[binary]"]` and `rds = ["psycopg[binary]", "boto3"]`; add `psycopg` to the dev group so `ty` and tests can import it (as boto3 is handled today: check how and mirror it).
- `files.py`: `Config.backend` literal, the new fields (above), and a validator that the pgvector fields are present when `backend == "pgvector"`. Verify what, if anything, already validates the S3 fields before adding this; do not add a validator S3 lacks.
- `search.py`: a third branch in `search()` (a plain `if`/`elif`, not a class) for `index` mode, `PG_TOP_K`, and one new function `search_pg_exact(vectors, floor)` returning one hit list per seed (the single-query path, D10; two queries in one transaction). Local and S3 are untouched.
- `candidates.py`: `build_candidates` takes one `if` to get its per-seed hit lists from `search_pg_exact` instead of calling `search()` per seed, for `pgvector` + `exact`; the merge, sort, write and meta code is shared and unchanged. Docstring `S3 topK cap` → `backend cap`.
- `system.py`: `project_status` (one line), no schema change (D8).
- `screens/new_project.py`, `screens/project_settings.py`, `screens/projects.py`, `screens/search.py`, `app.py:857`: as under "UI".
- Docs: `README.md` (install `hunches[pg]`, a "pgvector" paragraph next to "S3 Vectors" at line ~95, the env var), `AGENTS.md` (Stack, Layout, "Needs a human"), and 001's "other vector backends" out-of-scope line is superseded by this spec (note it in the "Behaviour that changes" section below).
- `.github/workflows/ci.yml`: optional job for the integration test (below).

## Tests

All default-run tests are offline.

- **Stubbed connection (fast tier).** A fake `psycopg.connect` whose cursor records the SQL and parameters and returns canned rows, in the style of `FakeS3` in `tests/test_search.py`. Assert: results are `(id, text, similarity)` sorted best first with only `sim >= floor` kept (floor inclusive, hand-computed values); `capped` is true only when some seed returns exactly `PG_TOP_K` hits (use a small `PG_TOP_K` via monkeypatch); the `NaN` guard and the `OFFSET 0` / `LATERAL` / `MATERIALIZED` shape are asserted on the SQL text; `exact` sends **one** step-1 query for any number of seeds (assert the fake saw exactly one such `execute` with all seed vectors in one parameter, plus the step-2 text query) and changes no planner setting, `index` issues `hnsw.iterative_scan` and one query per seed; the rows `search_pg_exact` returns feed `build_candidates` to the same `candidates.jsonl` as the per-seed path would for the same data (hand-built, ties to the earlier seed); the connection is read-only; identifiers are quoted (a column named `"text"; DROP TABLE x` stays an identifier); the vector parameter is a text literal; missing `psycopg`, missing URL var, missing table each give the exact message in "Errors"; a connection error containing the URL does not leak the password.
- **Config:** old configs load; a pgvector config round-trips; switching backend nulls the other backend's fields.
- **Screens (Pilot):** New project with pgvector chosen (required fields, Check store with a stubbed connection showing dimension and the opclass warning, Create writes the expected `config.toml` and no URL anywhere in it); Project settings switch S3 → pgvector with the confirmation; Projects row shows `pgvector` and the table; Search shows the cap warning and the `APPROXIMATE` warning. Add to the size sweep.
- **No-index table (stubbed + integration):** a config with `pg_search = "exact"` and a table with no index searches normally; Check store shows the no-index note and no WARNING; in `index` mode with no index it shows the WARNING. Stop calls `cancel()` on the stub connection and closes it; `pg_statement_timeout_s` issues `SET LOCAL statement_timeout` with the value, and `0` is passed through (not treated as unset). The integration test also runs `exact` against a table created with no index, and compares its candidates (ids, `max_similarity`, `best_seed`) with the local backend on the same vectors with several seeds, including a tie; it also reads `EXPLAIN` to check the single-pass plan.
- **Guards (stubbed):** the pre-flight refusal (statistics say 2 KB average width, 30 seeds, limit 512 MB → refuses before any scan query is sent), the streaming abort (fake cursor yields rows until the budget is passed → `cancel_safe()` called, connection closed, message carries the real count), `0` disables both, and no statistics skips the pre-flight. Version handling: `0.8.1` / `0.6.0` / `0.8.0rc1` parse; `index` on `0.6.0` raises before any `SET`; extension missing; `halfvec` column → seeds cast to `halfvec`; `sparsevec` refused; the schema from the column type appears as `OPERATOR(schema.<=>)` and a quoted identifier. `prepare_threshold` is `None` on the connection. A recovery-conflict error gets the replica hint.
- **Integration extras (real Postgres):** a `halfvec` table, an extension in a non-default schema, integer and uuid id columns, a partitioned table and a view as `pg_table`, a table with a very low floor to see the spill, and `index` mode only when the server reports pgvector ≥ 0.8.0 (the CI image does).
- **Managed-service manual checklist (human, once per service):** Check store (version, schema, encryption), `exact` search on a small table, a search that deliberately exceeds the statement timeout (hint appears), the pooler URL variants where the host has them. Recorded in the task 05 report, not automated.
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
| 01 | Config fields, `pg` extra, `search()` `index` branch, `search_pg_exact` (two-step, guards, version and type checks) + `build_candidates` branch (stubbed), errors and scrubber | — |
| 02 | Check-store function and column-type / version / statistics queries (verified against PostgreSQL docs) | 01 |
| 03 | New project: third backend, URL status/save, Check store | 01, 02 |
| 04 | Project settings, Projects, status allow-list, Search warnings | 01 |
| 05 | Integration test + optional CI job; managed-service checklist; size sweep | all |
| 06 | README, AGENTS.md, 001/002 notes | all |

## Open items

- **ask:** saved Postgres stores in `system.json` (D8). My recommendation is defer.
- `index` mode needs pgvector 0.8+ for iterative scans; the build container only had 0.6.0, so that mode's `SET LOCAL` names and its recall are unverified. Task 05 runs them against the `pgvector/pgvector` image.
- **Needs a human:** a PostgreSQL instance with pgvector and an embedded table for the manual end-to-end check, and the "Not verified" list above, above all every managed service (RDS, Aurora, Supabase, each with and without its pooler) and tables larger than memory. Agents cannot fake these.
