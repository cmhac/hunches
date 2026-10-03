# 07 — Projects screen and `open_project`

Spec sections: Projects, Startup flow (open_project).

## Goal
`screens/projects.py` and `HunchesApp.open_project(path)`.

## Do
- DataTable with Name/Backend/Where/Status/Opened, status rules per spec (no network), attention banner, empty state, sorted by most recent.
- Keys per spec: open, new, edit (open then Project settings), remove/delete modal (two actions; delete requires typing the project name; only `<project>/.hunches/` is ever removed), locate, refresh.
- `open_project`: confirm if workers are running, cancel them, `os.chdir`, `touch_project`, reset stage stack and go to the first incomplete stage; errors shown, never raised.
- Tests: statuses for OK / MISSING DIR / NO CONFIG / MISSING CORPUS fixtures; open changes `os.getcwd()` and stage; delete removes only `.hunches/` (corpus dir and neighbours intact); remove only edits the registry; opening with a running worker asks first.

## Done when
- Smoke tests pass; works at 80×24.
