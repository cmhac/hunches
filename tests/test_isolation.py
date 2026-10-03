import os
from pathlib import Path

import keyring


def test_home_points_at_tmp(tmp_path: Path):
    assert Path(os.environ["HUNCHES_HOME"]).is_relative_to(tmp_path)


def test_keyring_is_in_memory():
    keyring.set_password("hunches-test", "k", "v")
    assert keyring.get_password("hunches-test", "k") == "v"
    assert type(keyring.get_keyring()).__name__ == "MemoryKeyring"
    assert keyring.get_password("hunches-test", "other") is None
