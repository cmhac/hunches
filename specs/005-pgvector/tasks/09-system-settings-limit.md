# 09 — System settings: result limit

Spec: D12, "Result size and memory guards", Config (system level).

**Do** `screens/system.py`: an editable field for `pg_max_result_mb` (integer megabytes, `0` = no limit, shown as such), saved to `system.json` through the existing write path (`system.write_system`, which refuses to overwrite a newer file). Invalid input (negative, non-integer) is rejected with a one-line message through `say()`. Label and help text say that it applies to every pgvector project on this machine and that `0` disables the guard. Follow the screen's existing layout, key/button rules and the 80×24 rule; add to `tests/test_sizes.py` if the screen's content changes size.

**Tests (red first, Pilot)**: the field shows 512 by default and the stored value afterwards; saving 1024 writes it; `0` is saved as `0` and displayed as no limit; `-1` and `abc` are rejected without writing; other settings on the screen are unaffected; 80×24 sweep.

**Not in this task**: using the value (done in 05).
