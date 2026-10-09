# 12 — Integration tests, optional CI job, manual checklist

Spec: Tests (Integration, Integration extras, No-index table), "Verified on a real database", "Not verified".

**Do**
- `tests/test_pg_integration.py`, skipped unless `HUNCHES_TEST_PG_URL` is set (and skip `index` tests unless the server reports pgvector ≥ 0.8.0). Create their own schema/tables in the test and drop them afterwards (the test, not hunches, may write). Cases: `exact` equals the numpy local backend on the same vectors for several seeds including a tie and two true zero vectors (candidates: ids, `max_similarity`, `best_seed`); a table with no index; a table with an HNSW `vector_cosine_ops` index (exact still equals numpy; `EXPLAIN` shows a single scan of the table whatever the seed count, no ANN index used); `halfvec`; the extension in a non-default schema; integer and uuid id columns; a partitioned table and a view as `pg_table`; a very low floor (the spill case); `index` mode under default settings showing what it returns versus `exact` (measured, printed, not asserted as an exact number); Stop cancels a running query (a `pg_sleep`-backed one or a large cross join); `statement_timeout` produces the hint.
- `.github/workflows/ci.yml`: an optional job using the `pgvector/pgvector` service container that sets `HUNCHES_TEST_PG_URL` and runs that file. Check the current image tags and service-container syntax in the docs; do not break the existing jobs.
- Size sweep: confirm `tests/test_sizes.py` covers every new screen state added in 07, 09, 10 and 11.
- Write the **managed-service manual checklist** (spec "Tests") into `specs/005-pgvector/manual-checklist.md`, including the IAM steps (the IAM policy, `rds_iam` role grant, the URL shape, what to expect on success and on each failure) so Chris can run it against his RDS instance. Mark every item **needs a human**; do not tick any.
- Update the spec's "Verified on a real database" / "Not verified" with whatever the integration run proves or disproves, noting the pgvector and PostgreSQL versions used. If no Postgres is available in your environment, run what you can, say plainly what was not run, and do not claim it passes.

**Not in this task**: docs.
