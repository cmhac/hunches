# 05 — Projects screen and RemoveModal

Handoff: `design/README.md` §5 "Projects"; states `projects/list`, `projects/empty`, `projects/remove`, `projects/delete`, `projects/locate`. `[visual]` + `[behaviour]`. File: `screens/projects.py`.

## Goal
Restyle and give every key action a button.

## Do
- Table through the shared rules (zebra off: remove `zebra_stripes=True`). The attention banner ("N projects need attention") is a tinted block with a left bar (`.banner.-warning`).
- A button row under the table: **New project  n**, **Edit  e**, **Remove  x**, **Locate  l**, **Refresh  r** (`key_button`). Each calls the matching `action_*`. **Locate is enabled only when the highlighted row's status is `MISSING DIR` or `MISSING CORPUS`**; Edit and Remove are disabled with no projects. Re-evaluate on row highlight and after refresh.
- **Empty state:** centred message ("No projects yet.") plus a primary **New project** button below it (`action_new`). `n` still works.
- `RemoveModal`: restyled; copy and focus unchanged (starts on the safe action). The path picker is the restyled modal from task 04.

## Tests
- Pilot: buttons present; Locate disabled on an `OK` row, enabled on a missing-dir fixture; Edit/Remove disabled when empty; empty state shows the button and pressing it pushes `NewProjectScreen`.
- Existing `tests/test_projects.py` flows (open, remove, delete, locate) keep passing unchanged.

## Done when
- Matches `projects/*` at the three sizes.
