import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError
from pydantic_ai import models


class MemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self):
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise PasswordDeleteError("not found")
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def isolated_system(tmp_path, monkeypatch):
    """No test may reach the real ~/.config or the real keyring."""
    monkeypatch.setenv("HUNCHES_HOME", str(tmp_path / "hunches-home"))
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    yield
    keyring.set_keyring(previous)


class _ModelRequestsBlocked:
    """Falsy stand-in for `ALLOW_MODEL_REQUESTS` that remembers it was consulted.

    Screens swallow run errors into a status line, so a blocked request alone would not fail the
    test; the fixture below fails it at teardown instead.
    """

    def __init__(self):
        self.hits = 0

    def __bool__(self):
        self.hits += 1
        return False


@pytest.fixture(autouse=True)
def no_real_models(monkeypatch):
    """No test may reach a real LLM: unusable keys, and any un-stubbed model request fails the test."""
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AWS_ACCESS_KEY_ID"):
        monkeypatch.setenv(key, "test-invalid")
    blocked = _ModelRequestsBlocked()
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", blocked)
    yield
    assert not blocked.hits, (
        "test made an un-stubbed (real) model request; use TestModel/FunctionModel"
    )


@pytest.fixture
def stub_taxonomy_assistant(monkeypatch):
    """The taxonomy screen sends the assistant its context on mount; these tests are not about that."""
    import hunches.app  # noqa: F401  (import order: screens import the app)
    from hunches.screens.taxonomy import TaxonomyScreen

    async def no_context_turn(self):
        pass

    monkeypatch.setattr(TaxonomyScreen, "sync_context", no_context_turn)


@pytest.fixture(autouse=True)
def quiet_tune_assistant(request, monkeypatch):
    """A finished dev run on the tuning screen messages the assistant; only tests that ask for the
    `assistant` fixture (tests/test_tune_screen.py, which stubs the model) want that."""
    if "assistant" in request.fixturenames:
        return
    import hunches.app  # noqa: F401  (import order: screens import the app)
    from hunches.screens.tune import TuneScreen

    async def no_context_turn(self):
        pass

    monkeypatch.setattr(TuneScreen, "sync_context", no_context_turn)


@pytest.fixture
def no_keyring():
    """The `fail` backend keyring picks on headless systems: every call raises NoKeyringError."""
    from keyring.backends.fail import Keyring as FailKeyring

    keyring.set_keyring(FailKeyring())


@pytest.fixture
def system_ready(tmp_path):
    """A finished first run (system.json, recommendation seen) and a stub corpus `c/` in tmp_path.

    For tests whose project is tmp_path with `corpus_dir="c"`: startup opens it through
    `open_project`, which refuses a project whose corpus files are missing.
    """
    from hunches import system

    (tmp_path / "c").mkdir()
    for name in ("vectors.npy", "items.jsonl", "meta.json"):
        (tmp_path / "c" / name).write_text("x")

    system.write_system(
        system.System(
            provider="anthropic",
            assistant_model="a",
            classifier_model="c",
            recommendation_seen=system.RECOMMENDED_REVISION,
        )
    )


def panel_title(widget) -> tuple[str, str]:
    """(title, subtitle) markup of a `panel()`'s own title row (the first one under it)."""
    return (
        str(widget.query(".panel-title").first().content),
        str(widget.query(".panel-subtitle").first().content),
    )
