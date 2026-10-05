# 04 — Settings family: System, recommendation modal, New project, Project settings, pickers

Handoff: `design/README.md` §5 "System settings", "Model picker, path picker", "New project", "Project settings"; mock `ui_kits/tui-rail/Settings.jsx`; states `system/edit`, `system/first`, `system/nokey`, `system/differs`, `system/noprice`, `system/recommend`, `new/local`, `new/corpus-ok`, `new/corpus-bad`, `new/s3`, `new/blocked`, `pset/problem`, `pset/differs`, `pset/confirm`, `picker/*`, `projects/locate`. `[visual]` + `[behaviour]`. Screens: `screens/system.py`, `new_project.py`, `project_settings.py`, `model_picker.py`, `paths.py`.

## Goal
Restyle the settings screens and make Save/Create disabled until valid, with the reason shown beside the button. The guards stay in `save()`/`create()`.

## Do
- **System settings.** Each group (API keys, Models, Saved S3 stores) is a tinted block with a bold title; notes move to the bottom. **Save is disabled until at least one API key has status KEYRING or ENV**; the message ("Add at least one API key to save", or the error) sits to the right of the button. Remove `"ERROR: save at least one API key first"` as the way to learn this; keep the guard in `save()`. Re-evaluate on every key save/remove.
- **Model rows.** Remove the `DIFFERS from recommended` line (`#differs`) and the `#pricewarn` line. Each model row (assistant, classifier) ends with `RECOMMENDED` (success text) or a `DIFFERS FROM RECOMMENDED` info badge; "recommended" compares that row's model (the assistant row also compares thinking) with `system.RECOMMENDED[provider]`. A blank row separates assistant from thinking; a divider and blank rows sit above the classifier row; `Reset to recommended` is spaced below. A model with no price shows `no price: cost will show ?` (warning) on its own row (`models.price_label` already returns it). Same markers on Project settings (`pset/differs`).
- **Note copy.** "Prices from genai-prices as of <date>; the sidebar shows actual spend." at ≥100 columns, "header" below (use the helper from task 02).
- **RecommendationModal** lays out as groups: **assistant** (now / new lines; new in success bold; prices muted), **thinking** (now / new), a divider, **classifier** ("unchanged" when equal), then the note ("Existing projects keep their models.") and buttons Keep mine / Use new (success, focused).
- **New project.** **Create is disabled until valid:** local needs a valid corpus (`check_corpus`); S3 needs bucket, index and an embedding model; and no required API key may be missing (today's `missing_keys`). The hint ("Required: corpus", or the corpus problem) sits to the right of the button. Remove the "Create with required fields empty" error state; keep the guards in `create()`. Models summary block restyled, with a divider between the thinking line and the classifier.
- **Project settings.** **Save is disabled while the corpus has an error** (the message sits beside it). The confirmation modal text is unchanged.
- **Pickers.** `ModelPicker` and `PathPicker` restyled as raised modals through task 01's modal rule. Rows unchanged (model, ` ★ recommended`, ` DEPRECATED`, price line).
- Buttons for every key action: **Save**/**Create**/**Cancel** carry their keys where they have them (`key_button`). The existing `Browse`, `Change`, `Pick`, `Check store`, `Remove` buttons keep their ids (tests query them).

## Tests
- Pilot: System settings with no key → Save disabled and the message shown; saving a key (in-memory keyring from `conftest`) enables it; pressing the disabled button's action path still hits the `save()` guard. Model rows: recommended vs differs markers; unpriced model row text. First-run title unchanged.
- New project: Create disabled for empty corpus, enabled for a `tmp_path` corpus with the three files; S3 disabled until bucket, index, embedding set; disabled when a required key is missing.
- Project settings: disabled with a corpus error, enabled after fixing it.
- Breakers: `test_system_screen.py` (`#differs`, `pricewarn`, `ERROR: save at least one…`), `test_project_settings.py` and `test_new_project.py` (any assertion on removed lines or on the error state), `test_model_picker.py`.

## Done when
- All three screens and both pickers match the mocks at the three sizes; no error text is needed to learn why Save/Create is unavailable.
