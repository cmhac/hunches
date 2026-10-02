# 18 — End-to-end test, docs, first release

Spec sections: Testing, CI/CD.

## Goal
Prove the whole pipeline works offline, document it, and get ready for a human to cut `v0.1.0`.

## Do
- One end-to-end Pilot test using a tiny local index fixture, `TestModel`/`FunctionModel` for every agent, and a scripted key sequence through all nine stages in a tmp dir. Assert the final `results.jsonl` and that quitting and restarting at several stages resumes in the right place.
- A tiny sample project under `examples/` (a handful of items with hand-built vectors, `meta.json`, and a note on how to try it). No real API calls needed to open the UI up to the stages that call a model.
- Expand `README.md`: install (`uv tool install` / `pipx`), the required data format for the local backend, the S3 setup (extra `s3`), API keys via environment or `.env`, each stage in one paragraph, what to commit, and cost-tracking behaviour. Keep it short.
- Check the open items in the spec are resolved and update the spec's "Open items" list with what you found (sources linked).
- Verify `uv build` produces a wheel/sdist and that `uv run hunches --help`-style start works from the built wheel in a clean venv.
- Do not tag or publish.

## Needs human
- Real-API check: run the TUI once against a real corpus with real keys (`ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY`) and confirm costs appear (and the `?` warning appears for an unpriced model). Agents cannot do this without a key and a corpus.
- Optional S3 check with real AWS credentials.
- Complete the PyPI trusted publisher and GitHub `pypi` environment setup (see task 02), then push the `v0.1.0` tag.
