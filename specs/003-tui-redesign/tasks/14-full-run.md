# 14 — Stage 8 Full run: one centred block, untested-prompt block

Spec: D11, O2, conflict 2. Handoff: `design/README.md` change-log entries "Full run simplified…", "Runs: every classifier run…", "Full run: an untested prompt is a hard block"; mock `ui_kits/tui-rail/Run.jsx`; states `run/not-ready`, `run/idle`, `run/no-samples`, `run/price-unknown`, `run/untested`, `run/running`, `run/stopped`, `run/complete`, `run/failed`. `[visual]` + `[behaviour]`. File: `screens/run.py`.

## Goal
Make the Full run page match the other run screens and turn "untested prompt" from a warning into a hard block.

## Do
- **One centred block** (the `RunIndicator` from task 11 inside the page, no panels): title by state — "Ready to classify" (not started), "Classifying candidates" (running), "Complete", "Stopped", "Run failed"; a bar; "N of M · about X left"; **one status line**; **one button**. Remove the estimate and run panels, the live stats line (`cost | items/s | ETA`), and the failed-item list.
- **Status line by state.** Not started: the existing estimate text (`estimate()`: items, time, cost, including the "no timing samples yet…" and "cost ? (WARNING: price unknown for this model)" forms — `run/no-samples`, `run/price-unknown`). Stopped with failures: "N items failed and are retried on the next run". Failed run: the error text (`Run failed: …`). Complete: "Nothing to classify; every candidate at or above the threshold is done." Keep logging per-item errors to `results.jsonl` rows (`error` key) exactly as today; they are simply not listed.
- **Button:** `Start  s` / `Stop  x` / `Resume  s`; none when complete. Start is primary, Stop is error. The footer shows `s`/`x` accordingly.
- **Untested prompt is a hard block** (D11). When `test_result.json`'s `prompt_hash` differs from `final.prompt_hash()` (or no result exists): an error banner "Cannot start: prompt.md differs from the tested prompt (or was never tested). Run the dev set in the Tuning loop with this prompt first.", **no Start/Stop button, no `s`/`x` keys in the footer**, and a single **Go to Tuning loop** button (`app.goto_stage(5)`; Open item O2 asks whether it should be stage 6). Delete the `warned` flag and the "press s again to start anyway" path. **`action_start` returns without starting when the prompt differs, even if called by a key** (`check_action` returns `False` for `start`/`stop` in this state so the footer drops them; the guard also stays in the method).
- `pending()`, `run_all()`, resume semantics, row format, `x` cancelling the worker (task 11's stop/resume wiring replaces `workers.cancel_all()` with the stored worker) and `RESULT`/`prompt_hash` imports are unchanged. `seconds_text` now comes from `screens/progress.py` (task 11).
- Not-ready ("Finish stages 3 and 7 first.") uses task 01's centred style.

## Tests
- `run/untested`: no Start button, no `s`/`x` in the footer, `action_start()` called directly starts nothing and creates no worker (assert `results.jsonl` untouched); the Go button goes to stage 5.
- State table: for each of not-started / running / stopped-with-failures / complete / failed assert the title, status line text and button label.
- Existing resume behaviour, error rows retried next run, and `pending()` tests keep passing.
- Breakers in `tests/test_run_screen.py`: `#estimate`, `#live`, `#errors`, `#warn`, `press s again`, `border_title`, the estimate-panel assertions (move them to the status line).

## Done when
- `run/*` states match at the three sizes.
