# Delta 01 — two-table layout (vectors and text in separate tables)

Status: implemented on 2026-10-09, not yet committed. This delta wins over `spec.md` where they differ.

## Why

`spec.md` assumes one table (or view) holds the id, text and vector columns. A common schema keeps the embeddings in a side table keyed to the source rows, for example:

- `item_embeddings(item_id, item_created_at, embedding vector(1536))`
- `items(item_id, created_at, text, ...)`

Before this delta the only fix was a view joining the two. That needs `CREATE` rights, which a read-only user on a read replica (the normal hunches setup) does not have.

## Config

Two new optional fields. Like the other `pg_*` fields, they are absent from the file when unset:

| Field | Default | Notes |
|---|---|---|
| `pg_text_table` | unset | unset = one-table layout (behaviour unchanged). Set = two-table layout: `pg_text_column` is read from this table |
| `pg_text_id_column` | the value of `pg_id_column` | the text table's column that equals `pg_id_column` in `pg_table`; only read when `pg_text_table` is set |

In the two-table layout, `pg_table` is the table with the vectors and `pg_id_column` is its id column. The join key is **one column**. Composite keys (such as `(item_id, created_at)`) are out of scope: use a column that is unique on its own.

The layout is not stored separately: it is two-table exactly when `pg_text_table` is set.

## Search

- `search.text_source(config)` returns the (table, id column) that the text is read from. All text reads go through it.
- **Exact:** step 1 is unchanged and reads only `pg_table`. Step 2 (`SELECT id, text … WHERE id = ANY(%s)`) reads the text table and its id column. The result-size guard reads the average text width from the text table's statistics.
- **Index:** in the one-table layout the query is unchanged. In the two-table layout the ANN query selects `NULL` instead of the text, and a second query in the same transaction fetches the text for the returned ids (the same SQL as exact step 2). A join inside the `ORDER BY … LIMIT` query was rejected because the planner might not use the HNSW index once a join is involved.
- An id with no text row raises `no text row for id '<id>'` in both modes, as exact step 2 already did.
- If the text id column is not unique, one of the duplicate rows wins without warning. Pick a unique key.

## Check store

- In the two-table layout the sample query is a join: `SELECT v.<id>, left(t.<text>, 60) FROM <table> v JOIN <text table> t ON t.<text id> = v.<id> LIMIT 1`. It checks both tables, all four columns and that the id types can be compared.
- If the join returns no row, Check store warns: `No row of the table has a matching row in the text table: check the id col and text id col.` (In the one-table layout an empty sample still shows nothing.)
- Row estimate, vector type and indexes are still read from `pg_table`.

## UI (New project and Project settings, `screens/pg.py`)

- The first row of the pgvector section is a **layout** Select: `One table` / `Two tables`. Under it, a one-line explanation:
  - One table: "One table (or view) has the id, text and vector columns."
  - Two tables: "Vectors in table, text in text table, joined where text id col = id col (empty: same name). For when you cannot create a view."
- The rows **text table** (`#pg-text-table`) and **text id col** (`#pg-text-id`, placeholder `same as id col`) only show in the two-table layout. Their rows have the ids `#pg-text-table-row` and `#pg-text-id-row`.
- Required in the two-table layout: text table. `pg_missing(screen)` returns the missing pgvector labels for both screens and for Check store.
- Choosing `One table` saves both new fields as unset, even if they were typed in.
- Project settings opens with `Two tables` when `pg_text_table` is set. Changing either new field triggers the existing "re-run Search" consequence.
- **Check store saves a pasted URL first** (any layout; superseded by delta 02, which also saves on Create/Save and names the entry by URL id): if the url box has text, Check store does what Save URL does (keyring, then clears the box) and only runs the check when the save worked. Before this, a pasted but unsaved URL was ignored and the check failed with `pg_url_var … is not set`.
- `tests/test_sizes.py` sweeps the two-table form, which is the tallest variant (rds_iam with two tables).

## Tests

- `tests/test_search_pg_exact.py`: step 2 SQL against the text table, the `pg_text_id_column` override, and that the field is ignored without `pg_text_table`.
- `tests/test_search_pg_index.py`: the `NULL` select and the second text query, the missing-text error, and that no text query runs when there are no hits.
- `tests/test_search_pg_check.py`: the join sample SQL, the no-match warning, and that an empty one-table sample does not warn.
- `tests/test_new_project.py`, `tests/test_project_settings.py`: row visibility, the help text, the required text table, the fields written, and the stored layout reopening.

## Verified on a real database (2026-10-09)

Aurora PostgreSQL reader, pgvector 0.8.0, `item_embeddings` (vector(1536), monthly partitions, no vector index) and `items` (text), joined on `item_id`. Check store returned the version, the type and dimension, and a joined sample row.

## Known limits (not addressed here)

- On a partitioned `pg_table` the row estimate shows `~?`: the parent's `reltuples` is -1, and the partitions are not summed. This was already true before this delta.
- Check store does not check that the text id column is indexed. Without an index, every text lookup scans the text table.
