# 11 — `RunIndicator`, ETA, Stop and Resume

Spec: D8, D9, conflict 7. Handoff: `design/README.md` §5 last bullet and the change-log entries on runs and time remaining; `design/BACKEND_CHANGES.md` §8, §12; mocks in `ui_kits/tui-rail/common.jsx` (`RunningView`, `RunIndicator`); states `tune/first-run`, `tune/stopped`, `tune/rerun`, `final/first-run`, `final/running`, `final/rerun`, `threshold/sampling`, `run/running`, `run/stopped`. `[visual]` + `[behaviour]` + `[backend]`. New code in `screens/progress.py` (created in task 01 with `LabelBar`).

## Goal
One shared widget and one shared helper for every classifier run, so tasks 12 to 15 are mostly wiring.

## Do
- **`RunIndicator`** (add to `screens/progress.py`): a centred block: a title ("Running the dev set", "Running the held-out test set", "Sampling each similarity band", "Classifying candidates", …), a 36-column `LabelBar`/`ProgressBar` (primary; success at 100 %), a counts line `N of M · about X left` (the `· about X left` part omitted until the ETA exists), an optional status/stats line (one `Static`, `.note`/`.warn`/`.error`), and an optional button slot. Methods to set title, progress, detail, status and the button (`Stop  x`, `Resume  s`, `Start  s`, or none). It is a plain `Vertical` subclass, no registry. Used full-screen on Tuning, Test and Threshold and inside the Full run block.
- **ETA helper** (`eta_text(done, total, live_done, elapsed) -> str | None`, pure): `None` until `live_done ≥ 3`; else `seconds_text((total − done) × elapsed / live_done)` (D8). `live_done` counts completions where `Prediction.cached` is false. Show it once, in the counts line, not beside the bar.
- **`seconds_text`** moves here from `screens/run.py` (and `screens/run.py` imports it) with the leading `0m` trimmed: `14s`, `1m05s`, `1h02m`. Update `screens/run.py`'s existing "ETA" live line later in task 14.
- **Stop and resume (BACKEND §12).** Each run screen keeps the `Worker` returned by `run_worker` and offers `x` (Stop) and `s` (Resume) bindings plus the buttons. Stop calls `worker.cancel()`; `classify_many`'s `finally` already cancels outstanding tasks, and finished predictions are in the classifier cache, so nothing is paid twice. Because `CancelledError` is a `BaseException`, run bodies need `try/finally` (as `RunScreen.run_all` has) to leave `running` false and set `stopped`. **Stopped state:** progress stays "N of M", the button reads `Resume  s`, results panels stay hidden (no metrics from a partial run), chat stays hidden. Resume calls the same method as Start; cached items return instantly.
- **Leaving (D9).** A stage switch removes the screen and cancels its workers; add a test per run screen. Overlays do not stop a run.
- **Dim and key rules.** While a run is in progress or stopped, results-panel keys (`e`, `o`, `m`, `+`, `-`, F2 Done/Accept) are no-ops; add `check_action` where the footer should dim them. The footer stays visible.
- Helper for the screens: a function `run_state(screen)`-like is not needed; each screen owns a boolean `running` and `stopped` and toggles `display` on the indicator vs the panels.

## Tests
- `eta_text` by hand: `live_done=2` → None; `done=10, total=50, live_done=10, elapsed=20` → `(50-10)×20/10 = 80s` → `1m20s`; all-cached → None.
- `seconds_text` cases: 14 → `14s`, 65 → `1m05s`, 3720 → `1h02m`.
- `RunIndicator` renders title, bar value and the exact counts line with and without ETA; the button slot shows each variant.
- A generic Pilot test over a stub screen: Stop mid-run keeps the finished count, shows `Resume  s`, and Resume completes without new model calls for finished items (`FunctionModel` call counter).
- `tests/test_run_screen.py`'s import of `seconds_text` (if any) follows the move.

## Done when
- `RunIndicator` and the helpers exist, are tested, and no screen is wired yet except where trivial (tasks 12 to 15 wire them).
