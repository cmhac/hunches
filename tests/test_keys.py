import os

import keyring

from hunches import keys

SENTINEL = "sk-sentinel-DO-NOT-LEAK"
VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")


def clear_env(monkeypatch):
    for var in VARS:
        monkeypatch.delenv(var, raising=False)


def test_status_missing(monkeypatch):
    clear_env(monkeypatch)
    assert keys.status("ANTHROPIC_API_KEY") == "missing"


def test_status_keyring(monkeypatch):
    clear_env(monkeypatch)
    keyring.set_password("hunches", "ANTHROPIC_API_KEY", SENTINEL)
    assert keys.status("ANTHROPIC_API_KEY") == "keyring"
    assert keys.status("OPENAI_API_KEY") == "missing"


def test_env_beats_keyring(monkeypatch):
    keyring.set_password("hunches", "ANTHROPIC_API_KEY", SENTINEL)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert keys.status("ANTHROPIC_API_KEY") == "env"


def test_save_uses_service_and_var_name(monkeypatch):
    clear_env(monkeypatch)
    assert keys.save("OPENAI_API_KEY", SENTINEL) is True
    assert keyring.get_password("hunches", "OPENAI_API_KEY") == SENTINEL
    assert keys.status("OPENAI_API_KEY") == "keyring"


def test_remove(monkeypatch):
    clear_env(monkeypatch)
    keys.save("OPENAI_API_KEY", SENTINEL)
    keys.remove("OPENAI_API_KEY")
    assert keys.status("OPENAI_API_KEY") == "missing"


def test_remove_absent_is_not_an_error():
    keys.remove("OPENAI_API_KEY")


def test_remove_leaves_env_alone(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    keys.save("OPENAI_API_KEY", SENTINEL)
    keys.remove("OPENAI_API_KEY")
    assert keys.status("OPENAI_API_KEY") == "env"


def test_load_into_env_copies_keyring_values(monkeypatch):
    clear_env(monkeypatch)
    keyring.set_password("hunches", "ANTHROPIC_API_KEY", SENTINEL)
    keys.load_into_env()

    assert os.environ["ANTHROPIC_API_KEY"] == SENTINEL
    assert "OPENAI_API_KEY" not in os.environ


def test_load_into_env_never_overrides(monkeypatch):

    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    keyring.set_password("hunches", "ANTHROPIC_API_KEY", SENTINEL)
    keys.load_into_env()
    assert os.environ["ANTHROPIC_API_KEY"] == "from-env"


def test_available_with_backend():
    assert keys.available() is True


def test_no_keyring_backend(monkeypatch, no_keyring):

    clear_env(monkeypatch)
    assert keys.available() is False
    assert keys.status("ANTHROPIC_API_KEY") == "missing"
    assert keys.save("ANTHROPIC_API_KEY", SENTINEL) is False
    keys.remove("ANTHROPIC_API_KEY")
    keys.load_into_env()
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_no_keyring_env_still_works(monkeypatch, no_keyring):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert keys.status("ANTHROPIC_API_KEY") == "env"


def test_provider_var():
    assert keys.provider_var("anthropic:claude-sonnet-5-5") == "ANTHROPIC_API_KEY"
    assert keys.provider_var("openai:gpt-6-sol") == "OPENAI_API_KEY"
    assert keys.provider_var("openai:text-embedding-3-small") == "OPENAI_API_KEY"
    assert keys.provider_var("google-gla:gemini-3") is None
    assert keys.provider_var("sentence-transformers:all-MiniLM-L6-v2") is None
    assert keys.provider_var("noprefix") is None


def test_sentinel_never_in_any_returned_text(monkeypatch):
    clear_env(monkeypatch)
    keys.save("ANTHROPIC_API_KEY", SENTINEL)
    results = [
        keys.status("ANTHROPIC_API_KEY"),
        keys.status("OPENAI_API_KEY"),
        keys.save("OPENAI_API_KEY", "other"),
        keys.available(),
        keys.provider_var("anthropic:x"),
    ]
    assert SENTINEL not in repr(results) + str(results)


def test_providers_follow_the_keys_present(monkeypatch):
    for var in keys.VARS:
        monkeypatch.delenv(var, raising=False)
    assert keys.providers() == []
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert keys.providers() == ["openai"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert keys.providers() == ["anthropic", "openai"]
