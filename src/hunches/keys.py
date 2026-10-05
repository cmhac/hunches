import os
from typing import Literal

import keyring
from keyring.backends.fail import Keyring as FailKeyring
from keyring.errors import KeyringError

SERVICE = "hunches"
VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")


def available() -> bool:
    """False on headless systems, where keyring selects the `fail` backend."""
    return not isinstance(keyring.get_keyring(), FailKeyring)


def _stored(var: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, var)
    except KeyringError:
        return None


def status(var: str) -> Literal["env", "keyring", "missing"]:
    if os.environ.get(var):
        return "env"
    return "keyring" if _stored(var) else "missing"


def save(var: str, key: str) -> bool:
    try:
        keyring.set_password(SERVICE, var, key)
    except KeyringError:
        return False
    return True


def remove(var: str) -> None:
    """Never touches the environment. Absent key or no backend counts as already removed."""
    try:
        keyring.delete_password(SERVICE, var)
    except KeyringError:
        pass


def load_into_env() -> None:
    for var in VARS:
        if not os.environ.get(var) and (key := _stored(var)):
            os.environ[var] = key


def provider_var(model: str) -> str | None:
    return {"anthropic": VARS[0], "openai": VARS[1]}.get(model.partition(":")[0])


def providers() -> list[str]:
    """Providers that have an API key (env or keyring), in VARS order."""
    return [
        p for p, var in zip(("anthropic", "openai"), VARS) if status(var) != "missing"
    ]
