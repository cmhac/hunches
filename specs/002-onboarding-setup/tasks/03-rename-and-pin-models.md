# 03 — Rename to assistant/classifier, config migration, pinning

Spec sections: Terminology, Config changes (project), Model pinning, Changes to 001 (1, 5, 7).

## Goal
Project config uses `assistant_model`, `assistant_thinking`, `classifier_model`, `s3_region`; old keys still load; the held-out result goes STALE on a classifier change; assistant agents get thinking settings.

## Do
- `files.Config`: rename fields, add the new ones, `model_validator(mode="before")` mapping `smart_model`/`cheap_model`. `write_config` writes new names only (and skips `None`, as today).
- Update every read site (grep `smart_model|cheap_model`): `brief.py`, `taxonomy.py`, `tune.py`, `gold.py`, `final.py`, `run.py`, `threshold.py`; UI strings ("Asking the smart model..." → "Asking the assistant..."); tests and `examples/sample/.hunches/config.toml`.
- One small helper that builds `model_settings` from `assistant_thinking` (None → no settings); check the pydantic-ai `thinking` setting in the docs and with `TestModel`/`FunctionModel`.
- `final.prompt_hash` includes `classifier_model`; update banner text.
- Test that the classifier cache key differs per model (hand-written inputs, not derived from the code under test).
- Remove the model defaults from `Config` if no longer needed (minimal wins).

## Done when
- A config with old keys loads; all existing tests updated and passing; stale flips on model change.
