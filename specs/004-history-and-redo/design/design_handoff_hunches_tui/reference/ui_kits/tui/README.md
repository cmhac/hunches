# hunches TUI kit

Every state of every screen in `cmhac/hunches@main`, as static views. Mock data: a layoffs corpus, single-mode taxonomy with 3 labels (multi mode shown in Gold).

- `index.html` — click-through: state list on the left, terminal at 80×24 / 100×30 / 120×36. ↑↓ or [ ] steps through states, n / p jumps stages, and listed keys follow the real transitions (F2 → confirm, e → proposal, ...).
- `states.html` — gallery of all states at 80×24, grouped by stage.
- `common.jsx` — STATES registry, footer keys, ConfirmModal, MetricsPanel, DisView, NotReady.
- One file per screen: each exports a pure `XView({ v, app })` and pushes its states to STATES with `when` = the code condition that produces it.
  - `Setup.jsx` app.py SetupScreen · `Brief.jsx` screens/brief.py · `Search.jsx` screens/search.py · `Taxonomy.jsx` screens/taxonomy.py · `Gold.jsx` screens/gold.py (stages 4 and 6) · `Tune.jsx` screens/tune.py incl. ProposalScreen · `Test.jsx` screens/final.py · `Threshold.jsx` screens/threshold.py · `Run.jsx` screens/run.py · `Browse.jsx` screens/browse.py
- `data.js` — sample data.

To add a state: push `{ stage, id, name, when, View, v }` in the screen's file.
