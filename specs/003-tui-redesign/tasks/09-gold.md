# 09 — Stages 4 and 6 Gold labelling: no classification, pool errors, progress block, finish gating

Handoff: `design/README.md` §5 "4 and 6 Gold labelling"; `design/BACKEND_CHANGES.md` §6, §7; mock `ui_kits/tui-rail/Gold.jsx`; states `gold/single`, `gold/multi`, `gold/halfway`, `gold/almost`, `gold/confirm`, `gold/pool-short`, `test/pool-short`, `gold/exhausted`, `test/exhausted`, `test/single`, `gold/not-ready`. `[visual]` + `[behaviour]` + `[backend]`. File: `screens/gold.py` (also drives stage 6 labelling through `final.test_stage()`).

## Goal
Labelling is human only, cannot be finished incomplete, and fails loudly when the corpus is too small.

## Do

### A. No classification (BACKEND §6)
- Remove from `GoldScreen`: `predict()`, `show_prediction()`, `self.predictions`, `self.prompt`, `self.model`, the `#prediction` Static and its CSS, the `classify`/`Prediction`/`Model` imports, and the `run_worker(self.predict(...))` call in `action_confirm`. `action_confirm` validates the labels, writes `gold.jsonl`, moves on. The not-ready guard needs `taxonomy.yaml` only (not `prompt.md`). The `Model: …` line, `agrees`/`DIFFERS`, and the states `gold/classifying|agrees|differs|pred-failed|not-classified` (and `test/` twins) are gone.
- Consequence to document (task 17): the classifier cache is no longer warmed during labelling, so the first Tuning run classifies the whole dev set.

### B. Candidate pool errors (BACKEND §7)
- **Blocking (mount).** After the top-up on mount, if the split still has fewer than `files.SAMPLE_SIZE` rows: set a `pool_short` state holding `found` (rows in `candidates.jsonl`), `used` (gold rows taken by the other split; for the test split), `left` (unlabelled candidates not in `gold.jsonl`), `need` (`SAMPLE_SIZE`). Render the blocked view: a full-width error banner — dev: "Only 38 candidates were found; the dev set needs 50."; test: "Only 24 unlabelled candidates are left for the test set; it needs 50." — and a centred block titled "Your corpus may be too small for this analysis" with the numbers (candidates found, already in the dev set [test only], left to draw, needed) and two actions: **Add seeds** (`app.goto_stage(1)`) and **Project settings  F3**. Hide the item, labels and counts panels and the progress block. `d` and the label keys do nothing; the exact title wording is deliberate.
- **Non-blocking (`d` finds the pool empty).** When `action_draw_more` gets fewer than `DRAW_MORE` rows back and `left == 0`, show a persistent error banner above the progress block: "No more candidates to draw: only 6 were left, so the set has 56 items. If you need more, your corpus may be too small for this analysis." (N and M from the real counts). Clear it on the next label or move. This replaces the old warning note (`self.note` text "Only N unlabelled candidates were left to draw.").
- Dev and test share the pool (`draw()` already excludes ids in either split); the test message states found / already in dev / left / needed.

### C. Finish gating (README §5)
- `action_finish` returns silently when any row is unlabelled (no `"N items still unlabelled."` note). The F2 footer binding is conditional: use `check_action` returning `None` (dimmed) while rows remain (check against Textual 8.2.8; `False` would hide it). When all rows are labelled F2 opens the existing confirm ("All items labelled. Continue?"; behaviour unchanged, including the test split staying on stage 6).
- The states `gold/unfinished`, `test/unfinished` are removed.

### D. Buttons (README §5)
- Right column, under the counts: **Finish dev set  F2** (`Finish test set  F2` on stage 6; label `test set` per the handoff) on top, **Draw 10 more  d** below, stacked and centred. Finish is disabled until every row is labelled. Both call the matching `action_*`.

### E. Progress block (README §5, replaces `#progress`)
- A tinted block with a primary left bar at the top of the left column.
  Row 1: `dev set` (primary bold; `test set` on stage 6) · `item N` (muted) · right-aligned `33 to go` (strong bold), or `Complete` (success).
  Row 2: a `LabelBar` (task 01), full width, centred `17 / 50`, fill `$primary` (`$success` when complete), faint dividers at 25/50/75 %.
  Row 3: `Next milestone: halfway · 8 more` (muted) with the percentage right-aligned.
- **Milestones.** `done` = rows with labels; `total` = rows in the split (grows after `d`). Milestone counts are `ceil(total × f)` for f in 0.25, 0.5, 0.75, 1 (names for the "Next milestone" line, from `Gold.jsx`: "a quarter of the way", "halfway", "three quarters", "done"). When `done` equals a milestone exactly, row 3 shows a one-time message in success colour followed by `N to go.` (muted): 25 % "A quarter of the way there.", 50 % "Halfway there." (the README's quoted string; `Gold.jsx` renders just "Halfway." — the README wins, see spec conflict 8), 75 % "Three quarters of the way there.". When every row is labelled it reads "All labelled. Press F2 to finish." One-time means: show it when the count equals a milestone, clear it on the next label or move. No new data or state. Put the arithmetic in a pure function `milestone(done, total) -> tuple[str, int, str | None]` for testing.
- No blank rows between the stacked boxes in the middle column; they are told apart by tint: progress and labels on `$surface`, the item panel on `$background` with the focus bar on the item; the counts panel is flush to the same bottom edge.

### F. Label options and the rest
- Label options render as key cap, mark, name, description; the chosen row gets `$boost` and a primary left bar. The note and counts panel keep their content. The `#note` Static is `display: none` when empty.
- Not-ready ("Finish stage 3 (taxonomy and prompt) first.") uses task 01's centred style.

## Tests
- Milestone arithmetic by hand: total 50 → milestones 13 (25 %: ceil 12.5), 25, 38 (ceil 37.5); total 56 after a draw; "N to go"; complete state.
- Removing classification: labelling an item makes **zero** classifier/model calls (a `FunctionModel` that fails the test if invoked); `GoldScreen` has no `predictions`/`#prediction`.
- Pool-short: a candidates file with 38 rows → blocked view with the exact banner and counts, panels hidden, `d` and label keys inert, **Add seeds** goes to stage 1; test split with 24 left → the test wording and numbers. Exhausted: `d` with 6 left → 56 rows and the exact banner; cleared on the next label.
- Finish: `action_finish` with unlabelled rows does nothing and `check_action` dims it; with all labelled it opens the confirm; the button's `disabled` mirrors it.
- Breakers in `tests/test_gold_screen.py`: `#prediction`, `Model:`, `agrees`/`DIFFERS`, `still unlabelled`, `#progress`, `Only N unlabelled candidates`.

## Done when
- `gold/*` and `test/*` labelling states match at the three sizes; labelling never touches the network.
