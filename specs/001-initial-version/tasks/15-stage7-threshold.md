# 15 — Stage 7: threshold

Spec section: Stages, item 7; Candidate generation (bands).

## Goal
Pick a similarity cutoff by measuring the off-topic rate in each band.

## Do
- `src/hunches/screens/threshold.py`.
- Sample ~30 random candidates from each band (fewer if the band has fewer), classify them with the cheap model, and compute the off-topic rate per band where off-topic means the predicted set is exactly `{off_topic}`. Sampling is persistent and reproducible (same approach as task 12) so reopening does not cost anything extra.
- Show a table: band, candidates in band, sampled, off-topic rate, cumulative candidates at or above the band's lower bound. Show the cost and time of the sampling run, and record timing for the later estimate.
- The user selects a band lower bound (or types a cutoff). Save `threshold.json`: cutoff, per-band sample results, and the number of candidates that will be classified. Set `threshold_chosen`.
- With small samples the rates are noisy; show the sample size next to each rate.
- Tests: band sampling counts; off-topic rate calculation with `FunctionModel` returning fixed labels; saving the threshold writes the file and flag; a band with zero candidates is handled.

## Done when
- Pilot tests pass.
