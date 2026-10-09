# 03 — Server probes

Spec: "Versions", "Column types and schemas", "Result size and memory guards" (statistics), D5, D9.

**Do** in `search.py`, plain functions that take an open connection (from task 02) and the config:
- `extension_version(conn)`: `pg_extension.extversion` for `vector`; `None` means absent. Parse to `(major, minor, patch)` ignoring non-numeric suffixes (`0.8.1`, `0.6.0`, `0.8.0rc1`). Absent raises `The vector extension is not installed in this database (CREATE EXTENSION vector needs a DBA).` Also return the extension's schema (needed for `OPERATOR(schema.<=>)`).
- `column_type(conn, table, column)`: the type name and the type's schema, and the dimension, from the catalogs (`pg_attribute`, `pg_type`, `pg_namespace`, `format_type`). **The spec says the exact queries are to be verified: read the PostgreSQL catalog docs, write the queries, and put the verified form into the spec.** Handle a schema-qualified `pg_table` (`schema.table`) and a table that does not exist (Postgres text passes through). Only `vector` and `halfvec` are supported; anything else raises `Column "embedding" has type sparsevec; hunches supports vector and halfvec.`
- `table_estimates(conn, table, text_column)`: planner row estimate (`pg_class.reltuples`, never `count(*)`) and average text width (`pg_stats.avg_width`; **verify the view and column names in the docs**); `None` for either when statistics are absent (never analysed, `reltuples = -1`).
- `require_index_mode_version(version)`: raises `pg_search = "index" needs pgvector 0.8.0 or newer (found X). Use pg_search = "exact", or upgrade the extension.` below `(0, 8, 0)`; no check for `exact`.

**Tests (red first, stubbed connection with canned catalog rows)**: version parsing table above; absent extension message; `index` on 0.6.0 raises and `exact` does not; `halfvec` and `vector` accepted, `sparsevec` refused with the exact message; schema-qualified and bare table names split correctly; every identifier reaches the query as an `Identifier`/parameter (a table named `x"; DROP TABLE t` is not interpolated); missing statistics give `None`.

**Not in this task**: the similarity query, guards that use the estimates (05), UI.
