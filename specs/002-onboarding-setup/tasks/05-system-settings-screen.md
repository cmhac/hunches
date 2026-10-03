# 05 — System settings screen and recommendation modal

Spec sections: System setup / System settings, Model pinning (recommendation updates).

## Goal
`screens/system.py`: first-run setup and later edits on one screen, plus the "Recommended models changed" modal.

## Do
- Layout per spec: provider, API keys panel (status word, masked input, Save/Remove, no-keyring message), models panel (editable, `DIFFERS` badge, Reset to recommended, unknown-price warning using the 001 rule), S3 stores panel (delete/rename), the "existing projects keep their models" notice.
- First run (no system file): no Cancel, Save requires at least one available key, writes `system.json`.
- Recommendation modal logic from task 01 helpers. "Use new"/"Keep mine" both set `recommendation_seen`.
- Needs human: confirm OpenAI reasoning level (spec open items); default is no setting.
- Tests: Pilot first-run path, edit path, no-keyring path, modal both buttons; assert no project `config.toml` is touched and no key text is rendered.

## Done when
- Smoke tests pass; works at 80×24.
