# 06 — New project screen

Spec section: New project; Changes to 001 (2, 3).

## Goal
`screens/new_project.py` replaces `SetupScreen` in `app.py` (delete `SetupScreen` and its tests; port the useful cases).

## Do
- Form per spec: location (+Browse, create dir if parent exists, refuse an existing project with an "open it" button), backend, local corpus (+Browse, validation listing missing files, embedding model read from `meta.json`), S3 (saved store picker, new store fields, save-store checkbox, optional Check store via `get_index`, stubbed in tests), read-only models summary, missing-key blocking message with a button to System settings that returns with form values intact.
- Verify the `get_index` parameter names in the boto3 `s3vectors` reference.
- Create: write self-contained `config.toml` (relative corpus path when inside the project), save store if asked, `system.add_project`, then `open_project` (task 07 provides it; until then chdir + `goto_stage(1)`).
- Tests: local and S3 happy paths, each validation error, missing key blocks Create, existing project refused, store saved and reusable.

## Done when
- Smoke tests pass; works at 80×24.
