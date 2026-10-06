# 12 — Stage 7 Threshold: choose a band, run indicator

Spec: conflict 2, behaviour change 7. Handoff: `design/README.md` §5 "5 Tuning buttons, 6 Test evaluation, 7 Threshold…" and the change-log entry "Threshold: no text input"; mock `ui_kits/tui-rail/Threshold.jsx`; states `threshold/sampling`, `threshold/sampled`, `threshold/picked`, `threshold/failed`, `threshold/not-ready`. `[behaviour]` + `[visual]`. File: `screens/threshold.py`.

## Goal
The cutoff is a band's lower bound chosen by selecting a row; no text input; sampling shows the centred run indicator with Stop/Resume.

## Do
- **Remove** the cutoff `Input` (`#cutoff`), float parsing and the "Enter a number or pick a band with Enter." note. Free in-between cutoffs can no longer be entered (spec change 7); `files`/`threshold.json` format is unchanged and an existing off-edge saved value still loads and is still used by Full run.
- **Selection.** Enter or a click on a band row chooses it: that row is marked `●` in its Band cell (`● 0.650`, others `  0.650`; the last band keeps `+`), and a line under the table reads `Cutoff 0.650` (strong). With nothing chosen: `No cutoff chosen` (muted). If `threshold.json` exists and its `threshold` equals a band edge, preselect that band on open; if it exists and is off-edge, show `Saved cutoff 0.652` until a band is chosen. The value saved on F2 is the chosen band's lower bound (`candidates.BANDS[i]`), written exactly as today, with `bands` and `n_candidates`.
- **Button.** **Save cutoff  F2** (primary) next to the `Cutoff …` line, centred; disabled until a band is chosen. `action_save` keeps its guard (silent return when nothing is chosen). The explanatory sentence reads "Off-topic = predicted exactly {off_topic}. Small samples are noisy; mind n. Enter on a row chooses its lower bound as the cutoff." (the mock's text; the code string today ends "picks its lower bound").
- **Sampling.** While `run_sample` is running (and when stopped), hide the bands panel; show the `RunIndicator` (task 11): title "Sampling each similarity band", counts `N of M` with the ETA, detail "30 items per band" (`PER_BAND`), `Stop  x`/`Resume  s`. Use `self.progress` (`(sampled, total)`) that the screen already tracks. When the run ends the panel appears. On failure show the panel (finished rows are kept) with `Sampling failed: …` as the note. The existing success note `Sampled N items in Ts, cost $…` stays.
- `Footer` keys: `Enter Choose band`, `F2 Save cutoff`, plus `x`/`s` from task 11.
- Not-ready: centred (task 01).

## Tests
- Choosing a row marks `●`, shows `Cutoff 0.650`, enables Save; Save writes `threshold.json` with `threshold == 0.65` and sets `threshold_chosen`; with nothing chosen the Save button is disabled and `action_save` does nothing.
- Preselect: `threshold.json` at `0.7` preselects that band; at `0.652` shows the saved-cutoff line and nothing marked.
- Sampling: bands panel hidden and indicator shown while running; Stop keeps finished predictions in `threshold_sample.json`, Resume classifies only the remainder (call counter); failure shows the panel and note.
- Breakers: `#cutoff` in `tests/test_threshold_screen.py` and `tests/test_e2e.py` (the e2e flow chooses a band with Enter instead of typing).

## Done when
- `threshold/*` states match at the three sizes.
