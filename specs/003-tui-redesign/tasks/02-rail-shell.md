# 02 — Rail shell and footer

Spec: D2, D3, O4. Handoff: `design/README.md` §3.1; mock `components-rail/frame/Rail.jsx`, `Footer.jsx`. `[visual]`.

## Goal
At ≥100 columns, `StatusHeader` becomes a 26-column left rail; below 100 columns today's one-row header is unchanged.

## Do
- Keep the class name `StatusHeader` so every `yield StatusHeader()` still works. `on_resize` toggles a `-rail` class and `refresh_cost` renders either the existing single line or multi-line rail markup. TCSS: `StatusHeader.-rail { dock: left; width: 26; height: 100%; background: $surface; }` against today's `dock: top; height: 1`.
- Rail content, top to bottom (README §3.1): `hunches` (primary bold); project name (muted, ellipsis); blank; the nine stages (done `✓` success with muted name; current `●` primary with strong bold name, `$panel` background and a primary left bar; upcoming `·` and faint name); blank; **Projects F4**, **Project settings F3**, **System settings F5** (muted names, faint key; the current screen's one gets `▸`, strong bold and the same bar; "current" comes from `screen.stage_name`); at the bottom `n/p stage · q quit` (faint), then `cost` (muted) over `$0.3127` (strong bold). Unknown price: a warning reverse badge `cost ?` and the model names in warning colour below it. Never `$0` for an unknown price.
- **Content column.** The first row of content is level with the top of the rail (no blank row). Footer under the content column only (D2): in rail mode set `Footer` width to `screen width − 26` with `margin-left: 26` from `on_resize`. If this misbehaves, use the fallback in the spec and report it.
- **Footer keys (D3).** In rail mode the footer drops `q n p F3 F4 F5` (they are in the rail). Do it in a `Footer` subclass (`AppFooter`) or by hiding those `FooterKey`s; do **not** use `check_action`. The keys must keep working. Narrow mode keeps today's full footer. Replace `yield Footer()` in all screens with the subclass, or make the base filter apply to `Footer` globally via a class on the screen.
- **Boxes fill the space.** The rightmost panel in a row ends flush with the right edge (a 1-column gutter only *between* panels); with no rail (under 100 columns) side-by-side panels keep a 1-column gutter. Panels end at most one blank row above the footer (decide whole rows: `margin-bottom: 1` or none). Check Brief, Taxonomy, Gold, Browse at 100×30 and 120×36.
- Rail text on `SystemSettingsScreen`'s note: "the sidebar shows actual spend" at ≥100 columns, "header" below (task 04 owns the screen; this task exposes `app.rail` boolean, or a helper `wide()`, for it).
- The rail never hides `n/p`: `check_action("goto")` rules stay as in `app.py` (not on Projects).

## Tests
- Pilot: at 100×30 `StatusHeader` has `-rail`, is 26 wide and full height; at 99×30 it is one row; at both, `n`, `p`, `q`, `F3`, `F4`, `F5` still trigger their actions; the footer lists none of them at ≥100 and all of them below.
- Rail content: current stage marker, `✓` count equals `stage − 1`, cost line `$x.xxxx`; with an unpriced model the rail shows `cost ?` and the model name and never `$0` (extend the existing cost-unknown test).
- Footer geometry: at 100×30 the footer's left edge is at x=26.
- Existing `tests/test_app.py` header tests keep passing at 80×24.

## Done when
- At each of 80×24, 100×30, 120×36 every stage screen shows without clipping and the rail/footer behave as above.
- Needs human only if the D2 fallback is used (flag it).
