# 02 — CI/CD workflows

Spec section: CI/CD.

## Goal
Two GitHub Actions workflows.

## Do
- `.github/workflows/ci.yml`: on push and pull_request. Steps: checkout, `astral-sh/setup-uv`, `uv sync --all-extras`, ruff check, ruff format --check, ty check, pytest. Pin action versions to current major tags (verify they exist).
- `.github/workflows/publish.yml`: on push of tags matching `v*`. Runs the same checks, then `uv build`, then publishes with `pypa/gh-action-pypi-publish` using **trusted publishing** (job `permissions: id-token: write`, `environment: pypi`). No API token, no secrets.
- Do not tag, release, or publish anything yourself.

## Done when
- Both files validate (YAML parses; run `actionlint` if installable, otherwise review by eye).
- CI passes on the branch once pushed (check via the GitHub tools; fix if red).

## Needs human
- Before the first tag: create a pending trusted publisher on PyPI (owner `cmhac`, repo `hunches`, workflow `publish.yml`, environment `pypi`) and create the `pypi` environment in the GitHub repo settings. Without this the publish job will fail by design. Say so in your final message.
