
# hunches TUI kit, rail design

Same states and triggers as `ui_kits/tui`, restyled. The views are unchanged: the look comes from `components-rail/` (Panel, DataTable, Footer, Input, Select, Button, Notice, Modal, LabelOption, TextArea, Rail), loaded by `assets/hds-loader-rail.js`.

- 100 columns and wider: stage rail on the left (stage list, F3/F4/F5 destinations, cost). Footer shows only screen keys; n/p/q live in the rail.
- Under 100 columns: no rail; the one-row header returns.
- Panels are tinted blocks with a title row; focus is a left accent bar. Tables have no header fill; the cursor row is a tinted bar. Inputs and selects are tinted strips. Modals are raised blocks.
- Backend changes the design needs (taxonomy context message, tool-call display, search staleness and progress, and smaller items): `design_handoff_hunches_tui/BACKEND_CHANGES.md`.
- index.html: click-through. states.html: gallery at 100×30.


## Second change set: history, stale stages, gold orphans
New file `History.jsx` (History F8 and Redo plan F9 modals). New states are in the sidebar group "History and redo plan" and in their own stages. Stale marks come from a `marks` field on a state (`{stageNumber: ['stale'|'incomplete', reason]}`), shown in the rail and the narrow header. See `design_handoff_hunches_tui/PLAN_004_INTEGRATION.md`.
