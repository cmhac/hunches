# 08 — Project settings screen

Spec section: Project settings, Model pinning (changing a project's models).

## Goal
`screens/project_settings.py`: edit the current project's `config.toml`.

## Do
- Fields per spec; local embedding model read-only from `meta.json`; S3 fields with saved-store picker; models with `RECOMMENDED`/`DIFFERS` markers.
- Consequence confirmation before saving model/corpus/embedding changes; nothing is deleted automatically.
- Pick a free key binding; register it in the footer.
- Tests: edit and save each group; confirmation text states the consequences; classifier change flips the test result to STALE; cancel leaves the file unchanged.

## Done when
- Smoke tests pass; works at 80×24.
