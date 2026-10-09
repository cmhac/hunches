# 11 — Project settings, Projects screen, open-project allow-list

Spec: UI (Project settings, Projects, Status), "Behaviour that changes in 001–004".

**Do**
- `screens/project_settings.py`: the same `#pg` section and Check store as task 10 (reuse the code that task wrote; do not copy-paste a second version), the same consequence confirmation as S3 when table, columns or model change (`Candidates were generated from the old corpus/model; re-run Search`). Switching backend writes only the active backend's fields and sets the others to `None` (the 002 rule), including switching S3 ↔ pgvector in both directions.
- `screens/projects.py`: Backend column shows `pgvector`; Where column shows the table, never the URL or host.
- `app.py` `open_project` (around line 857 in the spec): the backend allow-list gains `pgvector`; no network on open.

**Tests (red first, Pilot)**: Project settings opens on a pgvector project with the stored values; changing the table asks for confirmation and a decline writes nothing; switching S3 → pgvector and back nulls the other fields (hand-written expected config); Check store works from this screen with the stub; Projects row shows `pgvector` and the table and never the host; opening a pgvector project makes no connection (the fake `connect` asserts it was not called); size sweep.

**Not in this task**: docs.
