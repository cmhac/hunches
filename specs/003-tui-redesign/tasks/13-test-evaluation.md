# 13 — Stage 6 Test evaluation: buttons, run indicator, reasoning

Spec: conflict 4. Handoff: `design/README.md` §5 "Test: …" bullets and the "Classifier reasoning" change-log entry; mock `ui_kits/tui-rail/Test.jsx`; states `final/first-run`, `final/result`, `final/stale`, `final/stale-accept`, `final/rerun`, `final/running`, `final/run-failed`. `[behaviour]` + `[visual]`. File: `screens/final.py`. (Labelling the test set is `GoldScreen("test")`, task 09.)

## Goal
Restyle the held-out evaluation, add its buttons, show the centred run indicator with Stop/Resume, and show classifier reasoning.

## Do
- **Buttons** in an action row under the disagreements: **Re-run  r**, **Back to tuning  t**, and (right-aligned) **Accept  F2** (success). Accept is disabled while the result is stale or missing or a run is in progress; `action_accept` keeps its guards. The stale case returns silently from the button path; the existing note "The result is stale: re-run (r) before accepting." stays for the key path (state `final/stale-accept`).
- **Stale banner copy** (aligned in the mocks to main): "STALE: prompt.md or classifier model changed since this result was computed. Press r to re-run." — unchanged text; restyled with the left bar.
- **Run indicator.** While the test run is in progress or stopped (first run and `r`), hide the metrics and table panels and show `RunIndicator` (task 11): title "Running the held-out test set", counts from `done` in `run_test_set`, detail "classifier <model>" on the first run and "prompt changed since the last run" on a re-run (mock), `Stop  x`/`Resume  s`. When the run ends the panels appear; on failure show the existing panels or empty state with `Test run failed: …`. Remove the in-note `Running test set N/M...` text. Keep the success note `Test run finished, cost $…`.
- **Reasoning.** The detail panel is titled "text · classifier reasoning": item text, then a bold teal (`$accent`) `classifier reasoning` heading, then the reasoning. Failed items show no reasoning (only the existing failure line). Carry `reasoning` into each `result["disagreements"]` record (`"reasoning": p.reasoning`). **Tolerate its absence** in older `test_result.json` files (show text only; no STALE).
- Layout: disagreements table and text panel side by side under 120 columns, stacked at 120+ (as Tuning, task 15); `VerticalScroll` for long text at 80×24.
- Keep `prompt_hash` as is.

## Tests
- Accept disabled when stale/missing/running, enabled otherwise; `r`, `t` and the buttons trigger the same actions.
- A hand-written old-format `test_result.json` (no reasoning) renders without error; a new one shows the reasoning heading and text.
- Run flow: indicator shown during a stubbed run (panels hidden), then panels with the metrics; Stop/Resume as in task 11.
- Breakers in `tests/test_final_screen.py`: `#note` run text, `border_title`.

## Done when
- `final/*` states match at the three sizes.
