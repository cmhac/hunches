import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError


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
