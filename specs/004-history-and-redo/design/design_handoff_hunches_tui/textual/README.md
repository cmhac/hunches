# Textual files

- `theme.py` → copy to `src/hunches/theme.py`. Registers the `hunches` theme and exposes `label_color()`.
- `hunches.tcss` → copy to `src/hunches/hunches.tcss`, set `CSS_PATH = "hunches.tcss"` on `HunchesApp`.

Screen-specific layout stays in each screen's `DEFAULT_CSS`; shared look lives here. Variable names in `theme.py` follow Textual's theme docs at the time of writing; check them against the current docs before use (AGENTS.md).
