# 04 — `PathInput`, `PathPicker` and model picker

Spec section: Path input and browser.

## Goal
Reusable directory entry with auto-complete and a modal browser, in `src/hunches/screens/paths.py`.

## Do
- Read the Textual docs for `Input(suggester=...)`, `Suggester.get_suggestion`, `DirectoryTree` (`filter_paths`, `DirectorySelected`), and `ModalScreen`. Do not use a third-party picker.
- `PathSuggester`, `PathInput`, `PathPicker` per spec (directories only, `~`, relative to cwd, trailing `/`, hidden rule, `use_cache=False`, listing cap, errors → no suggestion).
- A small helper to wire a Browse button to an input (a function, not a base class).
- Tests: suggester unit tests on a `tmp_path` tree; Pilot test for the picker (browse, Up, Select, Cancel) at 80×24.

- Model picker per spec "Model picker" (`KnownModelName`/`KnownEmbeddingModelName` for the list, `genai-prices` only for annotations, Other… entry), in `screens/paths.py` or its own small module; tests per the spec.

## Done when
- Tests pass at 80×24; the picker never selects without an explicit Select.
