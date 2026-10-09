# 10 — New project: third backend

Spec: UI (New project), D2, D3, D7, "Authentication", Tests (Screens, secret leak).

**Do** `screens/new_project.py` (read it and `tests/test_new_project.py` first; mirror how the `#s3` section is built):
- Backend Select gains `PostgreSQL (pgvector)`. A `#pg` section shown only for it: table, id column, text column, vector column (defaults shown as placeholders, left unset in the file when unchanged), URL variable name (default `HUNCHES_PG_URL`), auth mode (URL / RDS IAM) with region and profile inputs shown only for `rds_iam`, search mode Select (Exact default / Index), statement timeout (optional), embedding model (the existing picker).
- URL status word `env` / `keyring` / `missing` from `keys.status`, and **Save URL…** storing in the keyring via `keys.save` with a masked input. The URL never reaches a widget value that is later written to a file.
- **Check store** (task 08) in a thread worker like S3's `get_index`; the only network call on the screen; renders the returned lines (WARNING lines styled and worded per the repo's "never colour alone" rule). Disabled while running.
- Required to create: location, table, embedding model. Create writes only pgvector's fields and sets the other backends' to `None`; no URL, password or token anywhere.

**Tests (red first, Pilot, `check_store` and keyring stubbed)**: choosing the backend shows `#pg` and hides `#s3`; required-field validation; Check store output shown for a canned result including the opclass warning, and the no-index note; Create writes the expected `config.toml` (hand-written expected text) and the project registers; **secret leak**: after Create with a sample password, no file under the project, `system.json` or the config contains it; `rds_iam` fields appear only for that mode; Save URL stores via the stubbed keyring; 80×24, 100×30, 120×36 sweep.

**Not in this task**: Project settings, Projects screen.
