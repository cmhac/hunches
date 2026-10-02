# hunches

An interactive terminal toolkit for content analysis over an already-embedded corpus:
seed phrases, semantic search, candidates, an LLM classifier validated against a hand-labelled
gold set, and classified output. A smart model talks to you; a cheap model does the bulk work.

Status: early scaffold. See `specs/001-initial-version/spec.md`.

## Install

```
uv sync --all-extras
```

API keys come from the environment or a git-ignored `.env` file.

## Run

From the directory that contains (or should contain) `.hunches/`:

```
uv run hunches
```

Press `q` to quit.

## Develop

```
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```
