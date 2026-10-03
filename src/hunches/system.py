import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import platformdirs
from pydantic import BaseModel

from hunches import files

VERSION = 1

# Bump RECOMMENDED_REVISION whenever this table changes (spec 002, "Recommended models").
RECOMMENDED_REVISION = 1
RECOMMENDED: dict[str, dict[str, str | None]] = {
    "anthropic": {
        "assistant": "anthropic:claude-sonnet-5-5",
        "thinking": "medium",
        "classifier": "anthropic:claude-haiku-4-5",
    },
    # thinking None: provider default (open item in the spec)
    "openai": {
        "assistant": "openai:gpt-6-sol",
        "thinking": None,
        "classifier": "openai:gpt-6-luna",
    },
}


class NewerSystemFile(Exception):
    """system.json was written by a newer hunches; refuse to overwrite it."""


class Store(BaseModel):
    name: str
    bucket: str
    index: str
    region: str | None = None
    embedding_model: str


class Project(BaseModel):
    path: str
    last_opened: str


class System(BaseModel):
    version: int = VERSION
    provider: Literal["anthropic", "openai"]
    assistant_model: str
    assistant_thinking: str | None = None
    classifier_model: str
    recommendation_seen: int = 0
    s3_stores: list[Store] = []
    projects: list[Project] = []


def system_dir() -> Path:
    home = os.environ.get("HUNCHES_HOME")
    return Path(home) if home else Path(platformdirs.user_config_dir("hunches"))


def _path() -> Path:
    return system_dir() / "system.json"


def read_system() -> System | None:
    """None means first run (no file)."""
    path = _path()
    return System.model_validate_json(path.read_text()) if path.exists() else None


def write_system(system: System) -> None:
    path = _path()
    if path.exists() and json.loads(path.read_text()).get("version", 1) > VERSION:
        raise NewerSystemFile(f"{path} was written by a newer hunches; not overwriting")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(system.model_dump_json(indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load() -> System:
    system = read_system()
    if system is None:
        raise RuntimeError("no system settings yet (first run)")
    return system


def _abs(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def add_project(path: str | Path) -> None:
    system = _load()
    key = _abs(path)
    if all(p.path != key for p in system.projects):
        system.projects.append(Project(path=key, last_opened=_now()))
        write_system(system)


def remove_project(path: str | Path) -> None:
    system = _load()
    key = _abs(path)
    system.projects = [p for p in system.projects if p.path != key]
    write_system(system)


def touch_project(path: str | Path) -> None:
    system = _load()
    key = _abs(path)
    for p in system.projects:
        if p.path == key:
            p.last_opened = _now()
    write_system(system)


def projects_by_recent() -> list[Project]:
    system = read_system()
    projects = system.projects if system else []
    return sorted(projects, key=lambda p: p.last_opened, reverse=True)


def add_store(
    name: str, bucket: str, index: str, region: str | None, embedding_model: str
) -> None:
    """Add a saved S3 store; a store with the same name is replaced."""
    system = _load()
    system.s3_stores = [s for s in system.s3_stores if s.name != name]
    system.s3_stores.append(
        Store(
            name=name,
            bucket=bucket,
            index=index,
            region=region,
            embedding_model=embedding_model,
        )
    )
    write_system(system)


def delete_store(name: str) -> None:
    system = _load()
    system.s3_stores = [s for s in system.s3_stores if s.name != name]
    write_system(system)


def rename_store(old: str, new: str) -> None:
    system = _load()
    if any(s.name == new for s in system.s3_stores):
        raise ValueError(f"a store named {new!r} already exists")
    for s in system.s3_stores:
        if s.name == old:
            s.name = new
    write_system(system)


def recommended_changed(system: System) -> bool:
    """True when the user must be asked about a newer recommendation.

    If the stored models already equal the new recommendation, the revision is
    bumped silently (this writes system.json) and False is returned.
    """
    if system.recommendation_seen >= RECOMMENDED_REVISION:
        return False
    rec = RECOMMENDED[system.provider]
    if (system.assistant_model, system.assistant_thinking, system.classifier_model) == (
        rec["assistant"],
        rec["thinking"],
        rec["classifier"],
    ):
        keep_mine()
        return False
    return True


def keep_mine() -> None:
    """Acknowledge the current recommendation without changing any model."""
    system = _load()
    system.recommendation_seen = RECOMMENDED_REVISION
    write_system(system)


def use_new() -> None:
    """Adopt the current recommendation for the stored provider (system file only)."""
    system = _load()
    rec = RECOMMENDED[system.provider]
    assert rec["assistant"] and rec["classifier"]
    system.assistant_model = rec["assistant"]
    system.assistant_thinking = rec["thinking"]
    system.classifier_model = rec["classifier"]
    system.recommendation_seen = RECOMMENDED_REVISION
    write_system(system)


def project_status(path: str | Path) -> tuple[str, str]:
    """(status word, detail) for a registered project; reads files only, no network."""
    if not Path(path).is_dir():
        return "MISSING DIR", str(path)
    try:
        config = files.read_config(Path(path))
    except (OSError, ValueError):  # missing, bad TOML (a ValueError) or invalid fields
        return "NO CONFIG", str(Path(path) / ".hunches" / "config.toml")
    if config.backend == "s3":
        return "OK (s3 not checked)", ""
    corpus = Path(path) / (config.corpus_dir or "")  # relative to the project
    missing = [
        f
        for f in ("vectors.npy", "items.jsonl", "meta.json")
        if not (corpus / f).exists()
    ]
    if missing:
        return "MISSING CORPUS", f"{corpus}: missing {', '.join(missing)}"
    return "OK", ""


def delete_project_files(path: str | Path) -> None:
    """Remove `<path>/.hunches/` and nothing else (never the corpus, S3 or the project dir)."""
    target = Path(path) / ".hunches"
    if target.is_symlink() or not target.is_dir():
        raise ValueError(f"{target} is not a directory")
    shutil.rmtree(target)
