# 12 — Stage 4: gold dev set

Spec section: Stages, item 4; Classifier.

## Goal
Sample 50 candidates and let the user label them in the TUI while the classifier runs in the background.

## Do
- `src/hunches/screens/gold.py`, written so the same screen class is reused for the test split in task 14 (a `split` argument, not a subclass).
- Sampling: 50 random candidates, without replacement, excluding anything already in `gold.jsonl`. Persist the sample immediately (rows with empty labels) so a restart keeps the same items. Use a fixed seed stored in `config.toml` or derived from the project name so reruns are reproducible.
- Labelling UI: one item at a time showing the text, a keyed list of labels. In `single` mode, a key picks a label and moves on. In `multi` mode, keys toggle labels, `off_topic` clears the others and vice versa, and Enter confirms. Enforce `validate_labels`. Back/skip keys.
- A live per-label count table (including `off_topic`) updating as labels are saved.
- Classifier runs on each item as it is labelled, in a worker, results kept next to gold in memory and the cache. Do not show the model's prediction before the user labels the item (avoids anchoring); show it after.
- "Draw 10 more" key adds more samples to the dev split if the user wants more coverage of a label.
- Mark `dev_done` when all items are labelled and the user confirms.
- Tests: sample size and exclusion rules; `single` and `multi` key flows through Pilot; the invalid combination is refused; resume mid-labelling keeps progress.

## Done when
- Pilot tests pass.
