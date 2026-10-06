# 07 — Stage 2 Search: staleness, progress, buttons, bands as bars, top seeds

Handoff: `design/README.md` §5 "2 Search"; `design/BACKEND_CHANGES.md` §3 (Search bullets); mock `ui_kits/tui-rail/Search.jsx`; states `search/never-run`, `search/not-approved`, `search/running`, `search/done`, `search/seeds-changed`, `search/confirm`, `search/top-filtered`, `search/threshold-open`, `search/capped`. `[behaviour]` + `[backend]` + `[visual]`. Files: `screens/search.py`, `candidates.py`.

## Goal
Make the search button honest about whether a run is needed, show per-seed progress, and restyle the results.

## Do
- **Stored digest.** `build_candidates` writes `.hunches/candidates.meta.json` = `{"seeds_digest": sha256 of the JSON seed list, "written_at": ISO UTC, "floor": FLOOR}` after `candidates.jsonl`. Add `candidates.seeds_digest(seeds) -> str` and `candidates.seeds_changed() -> bool`: true only when the meta exists and its digest differs from the digest of `read_seeds()`. **Meta missing with `candidates.jsonl` present (old projects) is "unchanged".**
- **Progress callback.** `build_candidates(embedder=None, progress=None)`; `progress(done, total, seed)` is called after each seed's search (embedding all seeds first stays as is; show `0/N` until the first call). No finer progress (local is one matrix product; S3 pages are sequential with unknown total).
- **Top row.** A primary button reading **Run search  r**. Label **Rerun search  r** when results exist and seeds are unchanged; **Searching…** (disabled) while running; disabled when seeds are not approved (`files.read_state().seeds_approved`). Remove the `#status` "Seeds are not approved yet." label if the disabled button's state is clear; keep a note "Seeds are not approved yet." beside it (as `.warn`) so the reason is visible.
- **Staleness.** Seeds changed since `candidates.jsonl`: label "Run search", **no confirmation**, and "Seeds changed, rerun needed" (`.warn`) next to the button. Unchanged with results: "Rerun search" opens a `ConfirmScreen` with exactly: "You've already run the searches, and haven't changed the seed candidates. Depending on the size of the corpus, this can take a long time. Are you sure you want to rerun searches?". Never run: "Run search", no confirmation.
- **Progress bar** (`LabelBar`, task 01) to the right of the button while searching: filled by seeds done, label `4/12  <seed phrase>` left-aligned, label colour inverts over the filled part. Remove the separate "Searching..." text label.
- **Dim results** (panels inactive and dimmed, e.g. a `-inactive` class) whenever there are no results: not approved, never run, running (first run), failed.
- **Results panels.** "Candidates by similarity" (was `candidates.jsonl · by similarity band`): one row per band, a bar scaled to its count, right-aligned count (thousands separators); no "At or above" column; no Total row; the total goes in the panel subtitle (`N candidates`). Band names as today (`0.6-0.625`, …, `0.75+`, `:g`).
  "Top seeds" (was `best seed (items won)`): ranked rows `rank  count  bar  phrase`, top 10; the top row's bar is teal (`$accent`). Counts are right-aligned.
- **Top-seeds threshold.** A `Select` in the panel subtitle ("similarity at or above 0.6 ▼"); options are the band edges formatted `:g` (`0.6`, `0.625`, …); default `candidates.FLOOR`. Counts are recomputed from `candidates.jsonl`: `Counter(r["best_seed"] for r in rows if r["max_similarity"] >= t)`. Exact, because `best_seed` is the argmax seed of each item. Ranking can change with `t`; no new data.
- **Early pool warning (BACKEND §7 "Optional", now wanted by Chris).** When `candidates.jsonl` exists and has fewer than `2 * files.SAMPLE_SIZE` rows (100), show an error banner (`.banner.-stale`) above the results: "Only N candidates found. Labelling needs at least 100: 50 dev and 50 test." (N with a thousands separator, 100 from `2 * SAMPLE_SIZE`). It is a warning, not a block: the user can still continue, and Gold shows the blocking error (task 09) if the pool really is too small. Hidden when the count is ≥ 100, when there are no results, or while running.
- Remove the "Done. N candidates written…" paragraph (`#done`). The S3 cap warning reads exactly "WARNING: S3 returned its cap of 10,000 hits for at least one seed; only the 10,000 highest-scoring hits are kept." (format the number from `search.S3_TOP_K` with a thousands separator; the code and tests still say "topK cap" internally, only the text changes).
- Keep the failure line (`Search failed: …` plus the embedding-model mismatch hint) and the `r` binding. `r` while running or unapproved is a silent no-op.

## Tests
- `candidates.seeds_digest`/`seeds_changed`: hand-written cases (unchanged, edited, reordered counts as changed, meta missing = unchanged).
- `build_candidates` calls `progress` once per seed with `(i, total, seed)` (hand-built tiny vectors, as in `tests/test_candidates.py`) and writes the meta file.
- Top-seeds counts at two thresholds from a hand-built `candidates.jsonl` (expected counts written by hand, including a ranking change).
- Pool warning: 99 rows shows the exact banner with `99`; 100 rows hides it; no results hides it; it is not shown while running.
- Pilot: button label and confirmation in each of the four conditions; confirm text exact; "Seeds changed, rerun needed" shown and no confirmation when seeds differ; disabled when unapproved; panels dimmed when no results; progress bar updates during a stubbed run.
- Breakers in `tests/test_search_screen.py`: `Searching...`, `Done. `, `#done`, `At or above`, `Total` row, `topK`, `#status`; `tests/test_search.py` mentions `topK` only for the S3 cap (keep).

## Done when
- `search/*` states match at the three sizes.
