# 03 — `.hunches/` file I/O

Spec sections: The `.hunches/` folder, Classifier (taxonomy).

## Goal
Plain functions to read and write every file in `.hunches/`. No classes beyond Pydantic models or dataclasses for config, taxonomy and gold rows.

## Do
- `src/hunches/files.py`:
  - `root()` returns `Path(".hunches")`; helper to create it.
  - `config.toml` read/write (use `tomllib` to read; write by hand or `tomli_w` if you add it). Fields: backend (`local` | `s3`), paths or S3 bucket/index, `embedding_model`, `smart_model`, `cheap_model`, `target_metric`, `target_score` (default 0.90).
  - Provisional model defaults: `smart_model` and `cheap_model` as strings of the form `anthropic:...`. Look up current model IDs in the provider docs; the system the spec was written on suggests a Sonnet-class smart model and a Haiku-class cheap model, but do not trust that, verify. OpenAI must work by changing the prefix only.
  - `state.json` read/write: the five approval flags.
  - `read_jsonl` / `append_jsonl` / `write_jsonl` (append writes and flushes one line at a time so runs survive a crash).
  - `seeds.csv`, `brief.md`, `prompt.md` as simple text read/write.
  - `taxonomy.yaml`: model with `mode` (`single` | `multi`) and `labels` (name + description). Reject a label named `off_topic` in the file (built in). Provide `all_labels(taxonomy)` returning user labels plus `off_topic`.
  - `validate_labels(labels, taxonomy)`: the rules in the spec (at least one label; `off_topic` exclusive; exactly one in `single`). Used for both gold and predicted labels.
  - `gold.jsonl` rows `{id, text, labels, split}`.
  - `chat/<stage>.json` save/load using `ModelMessagesTypeAdapter` (check the current docs for the exact calls).
  - Resume helper `first_incomplete_stage()`: returns 1–9 from files plus `state.json` flags. Write its rules in a docstring and unit-test every transition.
- Tests with `tmp_path` and `monkeypatch.chdir`.

## Done when
- Every file type round-trips in tests; `validate_labels` has tests for each rule in both modes; `first_incomplete_stage` tested for all nine outcomes.
