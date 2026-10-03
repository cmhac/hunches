# 02 — API keys (`keys.py`)

Spec section: API keys.

## Goal
Resolve, store and remove Anthropic/OpenAI keys, and inject keyring keys into the environment at startup.

## Do
- Add `keyring` (`uv add`). Read the keyring docs first for: `get_password`/`set_password`/`delete_password`, the exception hierarchy (`KeyringError`, `NoKeyringError`, `PasswordDeleteError`), the `fail` backend and `PYTHON_KEYRING_BACKEND`.
- Functions: `status(var) -> "env" | "keyring" | "missing"`, `save(var, key)`, `remove(var)`, `available() -> bool` (a usable backend exists), `load_into_env()` (never overrides an existing env var), `provider_var(model_string) -> str | None` (`anthropic:` / `openai:` map to their vars; embedding strings like `openai:text-embedding-3-small` too; others `None`).
- Service name `hunches`, username = env var name. Catch `KeyringError` on every call.
- Never log or render a key.
- Tests: resolution order, no override, no-keyring backend, delete-absent, sentinel key never appears in repr/str of any status object.

## Done when
- Tests pass using only the fake backends.
