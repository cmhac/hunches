# 005 — pgvector backend

Status: proposal, for review. Not implemented. Builds on `../001-initial-version/spec.md`, `../002-onboarding-setup/spec.md`, `../003-tui-redesign/spec.md` and `../004-history-and-redo/spec.md`, all implemented. Written 2026-10-09 against `main` at `c8ebdf1`.

**Read order for an implementer:** this spec → your task file (none yet; see "Proposed tasks") → the code named under "What changes in the code".

## What this is, in one paragraph

Today `hunches` searches an already-embedded corpus from either a local directory (`vectors.npy` + `items.jsonl` + `meta.json`, numpy) or an Amazon S3 Vectors index. This spec adds a third backend, **pgvector**: a table in a PostgreSQL database that has the `vector` extension and already holds the corpus embeddings. As with S3, hunches only **reads** it: it never creates tables, indexes or the extension, never inserts, and never embeds the corpus. Only `search.search()` talks to the database; everything downstream (candidates, gold, classifier, metrics, history) is untouched.

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
| D4 | Exact vs approximate search | `pg_search = "exact"` (default) or `"index"`. **Exact** forces a sequential scan so the result equals the local numpy backend: every row at or above the floor, up to the cap. **Index** lets an HNSW/IVFFlat index answer and enables iterative scan; it shows an `APPROXIMATE` warning on the Search screen every time. | See "Why exact is the default". |
| D5 | Similarity | `similarity = 1 - (column <=> query)`. pgvector documents cosine similarity as 1 minus cosine distance and `<=>` as cosine distance ([README](https://github.com/pgvector/pgvector#readme)); unlike S3 Vectors (001 open item), this is documented, not assumed. The operator is norm-invariant, so the corpus need not be normalised. Rows with a zero vector give NaN and never pass the floor; the local backend treats them as similarity 0. Equal outcome unless `floor <= 0`, which `FLOOR` never is. | pgvector README; `candidates.FLOOR`. |
| D6 | Result cap | `PG_TOP_K = 10_000` per seed, same as S3 so the UI warning is common. `capped` is `True` when exactly `PG_TOP_K` rows came back and the last one is still at or above the floor. In `"index"` mode `capped` cannot detect a scan that ended early (see below); that is what the permanent warning is for. | S3 precedent (`search.S3_TOP_K`). **ask:** is 10,000 right for Postgres, where there is no service limit? Exact search on a large table sorts every row regardless of `LIMIT`, so a bigger cap costs only transfer. |
| D7 | Embedding model | Recorded in `config.toml` as `embedding_model` (as for S3), chosen with the model picker. There is no `meta.json` in a table, so hunches cannot detect a mismatch by itself; **Check store** (below) reports the column dimension so a human can compare it with the model's. | 002 New project, S3 path. |
| D8 | Saved stores in `system.json` | **Not in this spec.** S3 stores exist so one bucket/index can back several projects (002). For Postgres the reusable parts are a secret (already shared by `pg_url_var`) and five short fields with defaults. Adding `pg_stores` also means a `system.json` schema change; defer until someone asks. | Minimal implementation. **ask.** |
| D9 | Version/compat | Needs pgvector with `<=>` (any release) and, for `"index"` mode, **0.8.0+** for iterative scans. | README: "Starting with 0.8.0, you can enable iterative index scans". |

## Why exact is the default

`hunches` asks "every item at or above this similarity", not "the 10 nearest". pgvector's approximate indexes answer a `ORDER BY … LIMIT k` query by walking a graph with a candidate list of `hnsw.ef_search` (default 40), and "with approximate indexes, filtering is applied after the index scan" ([README](https://github.com/pgvector/pgvector#readme)). So an index-backed query asking for 10,000 rows returns about 40 unless iterative scan is on, and with iterative scan it still stops at `hnsw.max_scan_tuples` (default 20,000, approximate), after which it "will still return fewer than LIMIT rows". None of these is an error, and a short result is indistinguishable from "that is all there was". The local backend and S3 Vectors do not have this failure mode, and the whole pipeline (candidate pool, gold sampling, coverage) assumes the pool is complete.

Hence:

- **`exact` (default):** within one read-only transaction, `SET LOCAL enable_indexscan = off` (and `enable_bitmapscan = off`) so the planner must do a sequential scan, then
  ```sql
  SELECT {id}, {text}, 1 - ({vec} <=> %s::vector) AS sim
  FROM {table}
  WHERE {vec} IS NOT NULL            -- NULL vectors are skipped; local has no NULLs
  ORDER BY {vec} <=> %s::vector
  LIMIT %s
  ```
  and the floor is applied in Python on `sim` (not in SQL, so the filter cannot interact with the planner). Cost is a full scan per seed; for the corpus sizes where that is too slow the user switches to `index`.
- **`index`:** same query, but `SET LOCAL hnsw.iterative_scan = relaxed_order` (results may be slightly out of order; we re-sort client-side) and `SET LOCAL hnsw.max_scan_tuples = <PG_MAX_SCAN>`, with `WHERE 1 - (vec <=> q) >= floor` pushed into SQL so the scan continues until `LIMIT` or `max_scan_tuples`. Always shows: `WARNING: APPROXIMATE pgvector search; the index may hide hits above the floor. Switch to exact in Project settings for a complete pool.` (The 1000 upper bound of `ef_search` I remember is **not** in the README; do not hard-code it. Set only the parameters named here.)

**Implementation must verify, on a real Postgres with pgvector, before this is trusted:** that `enable_indexscan = off` really yields a sequential scan on an HNSW-indexed table (`EXPLAIN`), that exact and local results agree on the same data, and the exact `SET LOCAL` names against the installed pgvector. These are marked "Needs a human" below because they need a database.

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
| `embedding_model` | — | required, as for S3 |

Switching backend in Project settings writes only the active backend's fields and sets the others to `None` (002 rule, unchanged). Old configs have none of these and load unchanged.

## UI

- **New project** (`screens/new_project.py`): Backend Select gets a third option `PostgreSQL (pgvector)`. A `#pg` section (shown like `#s3`): table, id/text/vector column, URL variable (with a status word `env` / `keyring` / `missing` from `keys.status` and a **Save URL…** that stores it in the keyring via `keys.save`, input masked), search mode Select (Exact / Index), embedding model (picker). Required: location, table, embedding model. **Check store** runs in a thread worker like S3's `get_index` and is the only network call on the screen: it opens the connection read-only and shows
  - the vector column's type and dimension (`format_type(atttypid, atttypmod)` from `pg_attribute`), with a WARNING when the column is not `vector`/`halfvec`,
  - the planner row estimate (`pg_class.reltuples`; **not** `count(*)`, which is a full scan),
  - the indexes on the column and their operator class, with a WARNING in `index` mode when none uses `vector_cosine_ops` (the index would not be used by `<=>`; the README says the operator class must match the operator),
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
- `search.py`: a third branch in `search()` (a plain `if`/`elif`, not a function per backend, not a class) and `PG_TOP_K`. Nothing else in the module changes.
- `candidates.py`: docstring only (`S3 topK cap` → `backend cap`); behaviour unchanged.
- `system.py`: `project_status` (one line), no schema change (D8).
- `screens/new_project.py`, `screens/project_settings.py`, `screens/projects.py`, `screens/search.py`, `app.py:857`: as under "UI".
- Docs: `README.md` (install `hunches[pg]`, a "pgvector" paragraph next to "S3 Vectors" at line ~95, the env var), `AGENTS.md` (Stack, Layout, "Needs a human"), and 001's "other vector backends" out-of-scope line is superseded by this spec (note it in the "Behaviour that changes" section below).
- `.github/workflows/ci.yml`: optional job for the integration test (below).

## Tests

All default-run tests are offline.

- **Stubbed connection (fast tier).** A fake `psycopg.connect` whose cursor records the SQL and parameters and returns canned rows, in the style of `FakeS3` in `tests/test_search.py`. Assert: results are `(id, text, similarity)` sorted best first with only `sim >= floor` kept (floor inclusive, hand-computed values); `capped` true only when exactly `PG_TOP_K` rows return with the last still above the floor; `exact` issues `SET LOCAL enable_indexscan = off` and `index` issues `hnsw.iterative_scan`; the connection is read-only; identifiers are quoted (a column named `"text"; DROP TABLE x` stays an identifier); the vector parameter is a text literal; missing `psycopg`, missing URL var, missing table each give the exact message in "Errors"; a connection error containing the URL does not leak the password.
- **Config:** old configs load; a pgvector config round-trips; switching backend nulls the other backend's fields.
- **Screens (Pilot):** New project with pgvector chosen (required fields, Check store with a stubbed connection showing dimension and the opclass warning, Create writes the expected `config.toml` and no URL anywhere in it); Project settings switch S3 → pgvector with the confirmation; Projects row shows `pgvector` and the table; Search shows the cap warning and the `APPROXIMATE` warning. Add to the size sweep.
- **Secret leak test:** after Create, grep `config.toml`, `system.json` and every `.hunches/` file for the password used in the test.
- **Integration (optional, skipped unless `HUNCHES_TEST_PG_URL` is set):** against a real database with pgvector (CI service container using the `pgvector/pgvector` image): create a table with a few hundred random unit vectors and an HNSW `vector_cosine_ops` index, then assert `exact` equals the numpy result on the same vectors, and show what `index` mode returns under the default settings so the "hides hits" claim in this spec is measured, not assumed. This is the only way to resolve the verification list above; it needs no cloud account.

## Behaviour that changes in 001–004

- 001 "Out of scope: other vector backends" is no longer true; pgvector is the third. The "Vector search" section gains the pgvector paragraph (this spec's "Why exact is the default" is the reference).
- 002 New project / Project settings gain a third backend; "S3 stores" behaviour is unchanged and there are no saved Postgres stores (D8).
- 003/004: nothing. `candidates.jsonl` and `candidates.meta.json` are backend-independent.

## Out of scope

Creating or loading a table, creating an index, embedding a corpus, writes of any kind, SSH tunnels, connection pooling (one short connection per seed, like S3's one client per call), other databases, hybrid (keyword + vector) search, metadata filters, saved Postgres stores (D8).

## Proposed tasks

Same one-commit-per-task, red/green TDD process as 004.

| # | Task | Depends on |
|---|------|-----------|
| 01 | Config fields, `pg` extra, `search()` pgvector branch (stubbed), errors and scrubber | — |
| 02 | Check-store function (catalog queries verified against PostgreSQL docs) | 01 |
| 03 | New project: third backend, URL status/save, Check store | 01, 02 |
| 04 | Project settings, Projects, status allow-list, Search warnings | 01 |
| 05 | Integration test + optional CI job; size sweep | all |
| 06 | README, AGENTS.md, 001/002 notes | all |

## Open items

- **ask:** `PG_TOP_K` value and whether `exact` should be the default (D4, D6). My recommendation is yes to exact, 10,000.
- **ask:** saved Postgres stores in `system.json` (D8). My recommendation is defer.
- Behaviour of `enable_indexscan = off` on an HNSW-indexed table, and the parameter names in `index` mode: verify with `EXPLAIN` on a real database (task 05).
- `halfvec` columns need a `::halfvec` cast on the query, and the README caps indexed `halfvec` at 4,000 dimensions vs 2,000 for `vector`. Task 01 picks the cast from the column type reported by Check store, or supports `vector` only and says so; decide when implementing.
- **Needs a human:** a PostgreSQL instance with pgvector and an embedded table for the manual end-to-end check, and the verification list above. Agents cannot fake these.
