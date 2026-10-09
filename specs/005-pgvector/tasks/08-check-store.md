# 08 — `check_store` (function only)

Spec: UI (New project → Check store), "Managed services" (encryption, pooler hint), "Tables with no index", "Result size and memory guards".

**Do** in `search.py`: `check_store(config) -> dict` (or a small dataclass-free dict; no new class unless the repo already does it) that opens a connection (task 02), and returns, with no writes and without `count(*)`:
- pgvector version and the extension's schema; whether the connection is encrypted (`pg_stat_ssl` for `pg_backend_pid()`; verify the view in the docs);
- the vector column's type and dimension, plus a warning string when the type is not `vector`/`halfvec`;
- the planner row estimate;
- the indexes on the column and their operator classes (**verify the catalog queries in the docs and put them in the spec**); warning strings: in `index` mode when no index uses `vector_cosine_ops`; in `exact` mode with no index, the informational `No index: the search scans the whole table (~N rows).` (not a warning);
- a one-row sample: id and the first 60 characters of text (proves the column mapping);
- the worst-case pair note from the spec (`S × estimated rows`) when the seed count is given, with the `temp_file_limit` sentence;
- a pooler hint when the port is 6543 or the host contains `pooler.` (a hint, not a block);
- in `index` mode on < 0.8.0, the version message from task 03.
Each piece that fails reports its own error text (scrubbed) without hiding the others where that is possible.

**Tests (red first, stubbed catalog rows)**: each bullet with hand-written canned rows; halfvec and sparsevec; both index modes with and without a cosine index; no-index informational note has no WARNING; `reltuples = -1` gives an unknown row estimate shown as `?` (never 0); pooler hint for port 6543 and a `pooler.` host; no `count(*)` appears in any executed SQL; scrubbed errors.

**Not in this task**: any screen.
