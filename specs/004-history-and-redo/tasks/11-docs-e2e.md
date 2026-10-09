# 11 — Docs, end-to-end, size sweep

README section; update `AGENTS.md`/`CLAUDE.md` current state (004 implemented; list human checks: F6-F9 in real terminals, manual pass from the spec); end-to-end test (edit prompt after a full run -> stages 5-8 stale -> plan counts match a real re-run with FunctionModel call counts -> undo restores current); confirm every new modal is in `tests/test_sizes.py`.
