# 01 — System state file and recommendations

Spec sections: System state, Recommended models, Model pinning (recommendation updates), Testing.

## Goal
`src/hunches/system.py`: read/write `system.json`, project and S3-store list helpers, the hard-coded recommendations. No UI.

## Do
- Add `platformdirs` to dependencies (`uv add`).
- Pydantic model `System` (fields per spec), `system_dir()` honouring `HUNCHES_HOME`, `read_system() -> System | None` (None = first run), `write_system()` atomic (temp file + `os.replace`), refuse to overwrite a file with a newer `version`.
- Helpers (plain functions): `add_project(path)`, `remove_project(path)`, `touch_project(path)` (sets `last_opened`), `projects_by_recent()`, `add_store(...)`, `delete_store(name)`.
- `RECOMMENDED` dict per provider + `RECOMMENDED_REVISION`; `recommended_changed(system) -> bool`; apply helpers for "use new" / "keep mine" (which only touch the system file).
- Verify the four model IDs against the provider docs and `genai-prices` `calc_price`; stop and report if any fails to resolve.
- `tests/conftest.py`: autouse fixture setting `HUNCHES_HOME` to `tmp_path` and installing an in-memory keyring backend (check the keyring docs for `set_keyring`/`KeyringBackend`).

## Done when
- Tests per spec "Testing → system.py" pass; no test reads the real home directory.
