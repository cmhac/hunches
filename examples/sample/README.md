# Sample project

Eight items with hand-built 2-D vectors (`corpus/`) and a ready `.hunches/config.toml`.

```
cd examples/sample
uv run hunches
```

The UI opens on stage 1 (brief and seeds) and needs `ANTHROPIC_API_KEY` for the chat agent.

The vectors are not real embeddings: `meta.json` names the made-up model `hand-built-2d`, so
the search stage (which embeds your seed phrases with `embedding_model`) will fail until you
point `corpus_dir` and `embedding_model` at a real embedded corpus. The automated end-to-end
test (`tests/test_e2e.py`) uses the same kind of hand-built vectors with a stubbed embedder.
