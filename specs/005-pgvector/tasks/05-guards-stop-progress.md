# 05 — Result-size guards, Stop, progress

Spec: D12, "Result size and memory guards", "Tables with no index" (Progress and Stop), "Streaming and progress".

**Do** in `search_pg_exact` (and shared helpers in `search.py`):
- `pg_max_result_mb` is read from `system.read_system()` at the start of every search (`0` = no limit; no system file → 512).
- **Pre-flight**: with the statistics from task 03, worst case `S × PG_TOP_K × (avg_width + per-row overhead)`; over the limit → refuse before sending any scan query with `Search could return up to ~N MB (S seeds × 10,000 hits × ~W bytes) which exceeds the result limit of 512 MB. Use fewer seeds or raise the limit in System settings (F5).` (use the real numbers and limit). No statistics → skip. `0` → skip. Pick the per-row overhead constant, name it, and document it in the spec.
- **Streaming guard**: count bytes received (id + text + the same fixed overhead) over both steps; past the limit call `cancel_safe()` (psycopg ≥ 3.2; verify the docs, and fall back plainly if the installed version lacks it), close the connection, raise the same message with the real count so far. `0` disables.
- **Progress**: an optional `progress(received, 0, "")` callback called as rows arrive (the `(done, total, label)` shape `build_candidates` already uses; a zero total means unknown).
- **Stop**: the function needs a way to be stopped from another thread. Keep it minimal: it exposes or accepts a handle the Search screen can call (for example an object holding the live connection) that runs `cancel_safe()` then closes. After Stop the function raises a recognisable cancellation, not a generic error. Cancelling the Textual worker alone does not stop a blocked driver call (the spec says so).

**Tests (red first, stubbed)**: pre-flight refusal with statistics of 2 KB × 30 seeds × limit 512 → raises before any scan `execute`; no statistics and `0` both skip it; the streaming abort with a fake cursor yielding rows until the budget is passed → `cancel_safe()` called once, connection closed, message carries the exact count (hand-computed); limit read from a `system.json` fixture; progress called with increasing `received`; calling the stop handle from a second thread while the fake cursor blocks calls `cancel_safe()` and the search raises the cancellation.

**Not in this task**: the Search screen's Stop button and display (07).
