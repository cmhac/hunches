# hunches design system

Design system for **hunches**, an interactive Textual TUI for content analysis over an already-embedded corpus: seed phrases → semantic search → candidates → LLM classifier validated against a hand-labelled gold set → classified output. A smart model talks to the user; a cheap model does bulk classification. Python, `uv`, `pydantic-ai`, `textual`. Everything lives as plain files in `.hunches/`, tracked in git.

There is one product surface: the terminal app (`hunches` console script). No web UI, no marketing site.

## Sources
- GitHub: `cmhac/hunches`, branch `main`. Read: `src/hunches/app.py` (StatusHeader, SetupScreen, ConfirmScreen, ChatPanel, STAGES, bindings), every file in `src/hunches/screens/`, and `files.py`, `candidates.py`, `metrics.py` for messages, bands and validation rules.
- Spec: `specs/001-initial-version/spec.md` (pasted into chat, same as repo) and the author's original Notion idea notes.
- Every screen state in the kit is traced to a code path; each state lists the condition that produces it.

## Index
- `styles.css` — entry point (imports only) → `tokens/fonts.css`, `colors.css`, `type.css`, `grid.css`
- `textual/theme.py`, `textual/hunches.tcss` — the real deliverable for the app. See `textual/README.md`.
- `guidelines/` — foundation specimen cards (Colors, Type, Spacing, Brand)
- `components/` — React mock primitives, one dir per concern, each with `.jsx`, `.d.ts`, `.prompt.md` and a card
  - frame: Terminal, StatusHeader, Footer
  - layout: Panel, Modal
  - data: DataTable, Bar, ProgressBar, Sparkline, Badge, LabelTag, Diff
  - chat: ChatPanel
  - forms: Input, Button, Select, TextArea, LabelOption
  - feedback: Notice, Toast
- `ui_kits/tui/` — every state of Setup + all 9 stages: `index.html` (click-through) and `states.html` (gallery)
- `assets/hds-loader.js` — loads the components into cards/kits without a build
- `SKILL.md` — Agent Skill wrapper; `github.md` — repo link

Components are HTML mocks of Textual widgets for design work. They are not used by the Python app; the app gets its look from `textual/`.

## CONTENT FUNDAMENTALS

The voice is a careful lab notebook: literal, specific, unexcited. It names files and counts instead of describing feelings.

- **Address.** UI text is impersonal or addresses "you" sparingly. The agent speaks as "I" only in chat. Never "we".
- **Casing.** Sentence case everywhere: footer labels ("Approve seeds"), panel titles (lowercase file or thing: `seeds.csv · 14`, `disagreements · 7`), notices. Status flags are one UPPERCASE word: PASS, FAIL, STALE, WARNING, DIFFERS.
- **Name the file.** "Done. 4,812 candidates written to candidates.jsonl." not "Your results are ready." Files appear in code-literal form without quotes: prompt.md, taxonomy.yaml, .hunches/config.toml.
- **Status, then reason, then fix.** `Search failed: embedding model mismatch` / `Fix: set embedding_model in .hunches/config.toml to the model the corpus was embedded with.` Refusals start with the outcome: "Not saved: …", "Cannot approve: …".
- **Confirmations are one question with the count**: "Approve 14 seeds and continue to search?", "accuracy 0.860 is below the target 0.90. Accept tuning anyway?"
- **Progress uses "...":** "Searching...", "Running dev set 12/50...", "Asking the smart model...".
- **Numbers.** Cost $0.4213 (4 dp, always; unknown = "?", never $0). Metrics 0.913 (3 dp), targets 0.90 (2 dp), P/R/F1 0.88 (2 dp), similarity 0.6412 (4 dp), counts 4,812, time 0:08:02.
- **Labels** are shown verbatim in snake_case from taxonomy.yaml (`layoff_story`, `off_topic`). Never prettified.
- **Agent tone.** Short questions, one or two at a time. No preamble, no praise, no "Great question". Tool use is shown as `↳ propose_seeds · added 6 seeds`.
- **No emoji. No exclamation marks.** No "Oops", "Awesome", "Let's".
- **Warn about validity honestly.** "Tuning against test disagreements weakens this held-out result."

## VISUAL FOUNDATIONS

- **Medium.** Everything is a grid of character cells: 1ch × 1 row (14px Source Code Pro on a 20px row in mocks). No sub-cell positioning, no font sizes, no images. Hierarchy comes from colour, bold, position and borders.
- **Theme.** Dark only. Cool ink backgrounds (`#0E1218` → `#252E3E`), fog text (`#CDD4DE`, strong `#EEF1F5`, muted `#8C96A6`).
- **Colour roles.** Blue `#6EA8FE` is focus and action: the focused panel's border/title, the row cursor, footer keys, the wordmark, the current stage dot. Teal `#5CC8B4` is the agent's voice (chat gutter, streaming text, sparklines). Sand `#D2BE94` is structure (yaml keys, diff hunks, info). Status green/amber/red only mean PASS/WARNING/FAIL-or-STALE. Taxonomy labels get `--label-1..8` by taxonomy.yaml order; off_topic is always grey.
- **Never colour alone.** Every coloured state carries a word or glyph: PASS, ✓ agrees, DIFFERS, ■ name, +/- in diffs.
- **One focus.** Exactly one blue border on screen. Unfocused panels use `$border-blurred` (`#344056`).
- **Borders.** `round` (5px corners in mocks) for panels with a bold title cut into the top edge and an optional muted subtitle bottom-right. `tall` for Input/Select. Modal: round in primary on `$surface`. No shadows anywhere inside the terminal; no gradients; no transparency except the modal scrim (ink at 72%) and tinted banners/diff lines.
- **Backgrounds.** Flat. `$background` for content, `$surface` for table headers/inputs, `$panel` for the header bar. No textures or imagery.
- **Layout.** Header 1 row (dock top), footer 1 row (dock bottom), body 22 rows at 80×24. Typical splits: chat | file (1fr 1fr), list | detail (2fr 1fr), main | coverage (1fr ~33 cols). One region is `1fr` and absorbs extra height; bigger terminals add space, never new content. Below 80 cols, stack.
- **Spacing.** Panel padding `0 1`; modal `1 2`; 2-cell gaps between footer/header items; one blank row between chat turns. No margins; cells only.
- **Tables.** Header row on `$surface`, muted bold. Cells padded 1 cell each side. Numbers right-aligned. Text truncates with …; full text goes in a detail panel. Cursor row = blue bg, ink text, bold; blurred cursor = `$boost`.
- **Hover** (mouse in Textual): `$boost` background on rows; no colour change on text. **Press**: none beyond Textual's button bevel flip. **Focus**: blue border + blue title; inputs show a blue block cursor.
- **Motion.** Almost none: streaming text, progress bars filling, a toast that appears and leaves. No easing showcases, no spinners beyond "...".
- **Data glyphs.** Block bars `▏▎▍▌▋▊▉█` with ─ track, progress `━╸`, sparkline `▁▂▃▄▅▆▇█`.

## ICONOGRAPHY

There is no icon set and no icon font: Textual renders text. Iconography is a small fixed vocabulary of Unicode glyphs (see the Glyphs card):

- Stage stepper ● done / ◉ current / ○ upcoming. Label marks ■ (filled) □ (multi, unchecked) ● ○ (single).
- Chat gutters › user, │ agent, ↳ tool call. Agreement ✓ / ✗ always followed by a word.
- Separators: · in titles, – in ranges, ≥ for targets, … for truncation, ▼▲ for Select.
- Keys are written as text (`F2`, `enter`, `tab`, `↑↓`, `^p`).
- **No emoji.** No Nerd Font glyphs (not every terminal has them). Use only glyphs in Unicode box-drawing, block elements and geometric shapes, which every modern terminal font covers.
- **Logo:** none exists. The brand mark is the word `hunches`, lowercase, bold, blue, in the header. Do not draw one.

## KEYBINDINGS

Same key, same meaning, on every screen.

Global: `q` quit · `n`/`p` next/previous stage · `F2` approve and continue (every gate) · `^p` command palette · `tab` next panel · `esc` leave input / cancel modal · `enter` confirm.

Screen-local (from the code's BINDINGS): `a`/`e`/`d` add/edit/delete seed (1) · `r` run search (2), re-run test set (6) · `1`–`9` label in taxonomy order, `0` off_topic, `←`/`→` back/skip, `enter` confirm labels (multi), `d` draw 10 more (4, 6) · `e` propose prompt edit, `m` cycle target metric, `+`/`-` target score (5) · `t` back to tuning (6) · `enter` on a band row picks its lower bound (7) · `s`/`x` start-resume/stop (8) · Browse has no bindings of its own; `tab` moves between search, labels and table.

Rules: number keys are reserved for labels. Footer order is screen actions → F2 → n/p → q, since it truncates on the right at 80 cols. When a button and a key do the same thing, the button says so: "Run search (r)".

Known conflict: `d` is delete on stage 1 and draw on stage 4; `e` is edit on stage 1 and propose on stage 5. Each meaning is close enough to keep; flag if it confuses users.

## Intentional additions
- Terminal: frame for mocks (sizes the cell grid).
- LabelTag, LabelOption, Bar, Sparkline: the current code prints these as plain text (`[x] 1 name`); the system gives them colour and glyphs.
- Setup uses compact 1-row inputs (`Input compact`) so all seven fields fit at 80×24; the code uses default 3-row inputs, which overflow.
- Browse puts the detail pane under the table below 100 columns; the code's 24 | 2fr | 1fr row leaves the text column unreadable at 80.
- Confirm modal button order is Cancel, Approve (primary last); the code has Approve first.
- StatusHeader uses `$panel` with a stepper; the code uses `$primary` background and plain text.
