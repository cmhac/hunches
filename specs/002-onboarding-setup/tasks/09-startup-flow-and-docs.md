# 09 — Startup flow, always-on keys, end-to-end, docs

Spec sections: Startup flow, Changes to 001 (2, 4, 6, 7), Testing.

## Do
- `HunchesApp.on_mount` flow per spec; `main()` calls `keys.load_into_env()` after `load_dotenv()`.
- Always-available Projects/Settings keys (verify F-keys; fall back if swallowed), not active with a modal open.
- Startup matrix tests; extend `tests/test_e2e.py` through first run → new project → stage 1 → Projects → open another project.
- README (install, first run, keys and keyring caveats, projects, system vs project state, what to commit), `AGENTS.md` layout and "Current state", example config.
- Manual check needs a human: real key + real keyring; optional real S3 index.

## Done when
- All checks pass; README matches behaviour.
