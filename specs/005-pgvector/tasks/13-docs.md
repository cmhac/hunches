# 13 — Docs

Spec: "What changes in the code" (Docs), "Behaviour that changes in 001–004".

**Do**
- `README.md`: install `hunches[pg]` (and `hunches[rds]` for IAM), a "pgvector" paragraph next to "S3 Vectors" (what it reads, read-only, the env var / keyring URL, `exact` vs `index`, the 512 MB limit and where to change it, managed services, IAM), consistent with how S3 is documented there.
- `AGENTS.md` (the repo's `CLAUDE.md`/`AGENTS.md`, whichever is the tracked file; check): Current state gains 005; Stack (`psycopg`, extras `pg`/`rds`); Layout (where the pg code lives); "Needs a human" (a Postgres with pgvector, managed services, IAM, TLS, the manual checklist).
- `specs/001-initial-version/spec.md` and `specs/002-onboarding-setup/spec.md`: a one-line note where they say other vector backends are out of scope / list the two backends, pointing at 005 (do not rewrite them).
- `specs/005-pgvector/spec.md`: Status line to "implemented, pending Chris's test against his RDS database"; fill in any Clarifications that implementation produced.

**Tests**: none new; run the whole suite and the lint/type checks and report. Verify every command and file path in the docs exists as written.
