"""Undo/redo history of seeds.csv, taxonomy.yaml and prompt.md (spec 004).

Plain files only: `.hunches/history/objects/<sha256>` holds every saved version, `.hunches/history/log.jsonl` is
append-only. Undo and redo stacks are not stored; they are derived by replaying the log.
"""

import hashlib
import json
import os
from datetime import UTC, datetime

import yaml

from hunches import files

ARTIFACTS = {
    "seeds": "seeds.csv",
    "taxonomy": "taxonomy.yaml",
    "prompt": "prompt.md",
}
# sources that are new edits: they push onto the undo stack and clear the redo stack
EDITS = {"user", "assistant", "external", "restore", "baseline"}


class NeedsVersion(Exception):
    """A label-set change while gold labels exist; wired in by the taxonomy tasks."""

    def __init__(self, kind: str, taxonomy: files.Taxonomy, number: int):
        super().__init__(f"needs a taxonomy version ({kind}, version {number})")
        self.kind = kind  # "restore" or "new_version"
        self.taxonomy = taxonomy
        self.number = number


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dir():
    return files.root() / "history"


def _current(artifact: str) -> str | None:
    path = files.root() / ARTIFACTS[artifact]
    return _digest(path.read_bytes()) if path.exists() else None


def _put_object(data: bytes) -> str:
    name = _digest(data)
    path = _dir() / "objects" / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        _replace(path, data)
    return name


def _replace(path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _append(entry: dict) -> dict:
    log = _dir() / "log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    entry = {"seq": len(entries()) + 1, "ts": datetime.now(UTC).isoformat(), **entry}
    with log.open("a") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
    return entry


def _edit(
    artifact: str,
    before: str | None,
    after: str | None,
    source: str,
    summary: str,
    group: str | None,
    snapshot: int | None = None,
) -> dict:
    entry = {
        "kind": "edit",
        "summary": summary,
        "artifact": artifact,
        "before": before,
        "after": after,
        "source": source,
    }
    if group is not None:
        entry["group"] = group
    if snapshot is not None:
        entry["snapshot"] = snapshot
    return _append(entry)


def _write(
    artifact: str, data: bytes, source: str, summary: str, group: str | None
) -> dict:
    """Object, then file, then log line, in that order (a crash between the last two is recovered by sync)."""
    after = _put_object(data)
    before = _current(artifact)
    _replace(files.root() / ARTIFACTS[artifact], data)
    return _edit(artifact, before, after, source, summary, group)


def entries(artifact: str | None = None) -> list[dict]:
    """Oldest first. With `artifact`, only that file's edit entries."""
    rows = files.read_jsonl("history/log.jsonl")
    if artifact is None:
        return rows
    return [r for r in rows if r["kind"] == "edit" and r["artifact"] == artifact]


def text(object_hash: str | None) -> str | None:
    if object_hash is None:
        return None
    path = _dir() / "objects" / object_hash
    return path.read_text() if path.exists() else None


def sync() -> list[dict]:
    """Log files that no longer match their last entry (edited in an editor, git checkout, a crash
    between file write and log append). A project with no log gets one baseline entry per file."""
    first = not entries()
    added = []
    for artifact, name in ARTIFACTS.items():
        current = _current(artifact)
        mine = entries(artifact)
        last = mine[-1]["after"] if mine else None
        if current == last:
            continue
        if current is not None:
            _put_object((files.root() / name).read_bytes())
        if first:
            added.append(
                _edit(artifact, last, current, "baseline", f"Baseline: {name}", None)
            )
        else:
            added.append(
                _edit(
                    artifact, last, current, "external", f"{name} changed outside", None
                )
            )
    return added


def save(
    artifact: str,
    text: str,
    source: str,
    summary: str = "",
    group: str | None = None,
) -> bool:
    """Write the file and log the change. False (and nothing written) if the content is unchanged."""
    files.ensure_root()
    sync()  # an unlogged outside edit must not be overwritten unrecorded
    data = text.encode()
    if _digest(data) == _current(artifact):
        return False
    _write(artifact, data, source, summary, group)
    return True


def _stacks(
    artifact: str,
) -> tuple[list[list[dict]], list[tuple[list[dict], dict]]]:
    """(undo, redo): lists of units, a unit being the entries of one group, oldest first. A redo item
    also carries the undo entry that put it there."""
    undo: list[list[dict]] = []
    redo: list[tuple[list[dict], dict]] = []
    for e in entries(artifact):
        if e["source"] in EDITS:
            if (
                e.get("group") is not None
                and undo
                and undo[-1][-1].get("group") == e["group"]
            ):
                undo[-1].append(e)
            else:
                undo.append([e])
            redo.clear()
        elif e["source"] == "undo" and undo:
            redo.append((undo.pop(), e))
        elif e["source"] == "redo" and redo:
            undo.append(redo.pop()[0])
    return undo, redo


def can_undo(artifact: str) -> bool:
    # never delete a file: undoing the creation of a file (before is None) is not offered
    undo, _ = _stacks(artifact)
    return bool(undo) and undo[-1][0]["before"] is not None


def can_redo(artifact: str) -> bool:
    return bool(_stacks(artifact)[1])


def _next_version() -> int:
    numbers = files.version_numbers()
    return numbers[-1] + 1 if numbers else 1


def _taxonomy(data: str | None) -> files.Taxonomy | None:
    try:
        return files.Taxonomy.model_validate(yaml.safe_load(data or ""))
    except ValueError:
        return None


def _log_changes(source: str, summary: str, snapshot: int) -> dict:
    """Log what a version restore changed. The taxonomy entry is the move itself; other files that
    came back with the version are plain restores."""
    moved = entries("taxonomy")[-1] if entries("taxonomy") else {}
    for artifact, name in ARTIFACTS.items():
        current = _current(artifact)
        mine = entries(artifact)
        last = mine[-1]["after"] if mine else None
        if current == last:
            continue
        if current is not None:
            _put_object((files.root() / name).read_bytes())
        if artifact == "taxonomy":
            moved = _edit(artifact, last, current, source, summary, None, snapshot)
        else:
            _edit(artifact, last, current, "restore", summary, None)
    return moved


def restore_version(n: int, summary: str) -> None:
    """`files.restore_version`, logged as a restore of the taxonomy (and of whatever else came back)."""
    sync()
    number = _next_version()
    files.restore_version(n)
    _log_changes("restore", summary, number)


def start_new_version(
    new: files.Taxonomy, summary: str = "", source: str = "user"
) -> int:
    """`files.start_new_version`, logged: the taxonomy edit (carrying `snapshot`) and a version entry."""
    sync()
    before = _current("taxonomy")
    n = files.start_new_version(new)
    after = _put_object(files.taxonomy_yaml(new).encode())
    _edit("taxonomy", before, after, source, summary, None, n)
    _append({"kind": "version", "summary": summary, "snapshot": n})
    return n


def _move(
    artifact: str,
    target: str | None,
    source: str,
    summary: str,
    confirmed: bool,
    snapshot: int | None = None,
) -> dict:
    """Make `artifact` match object `target` (or, for the start of a taxonomy version, restore the
    version `snapshot`). A label change while gold labels exist needs the caller's confirmation."""
    if snapshot is not None:
        number = _next_version()
        if files.taxonomy_in_use() and not confirmed:
            archived = _taxonomy(files.read_text(f"versions/{snapshot}/taxonomy.yaml"))
            raise NeedsVersion("restore", archived, number)  # ty: ignore[invalid-argument-type]
        files.restore_version(snapshot)
        return _log_changes(source, summary, number)
    if artifact == "taxonomy" and files.taxonomy_in_use():
        new = _taxonomy(text(target))
        old = _taxonomy(files.read_text("taxonomy.yaml"))
        if new and old and files.labels_changed(old, new):
            if not confirmed:
                raise NeedsVersion("new_version", new, _next_version())
            start_new_version(new, summary, source)
            return entries("taxonomy")[-1]
    return _write(artifact, _object(target), source, summary, None)


def undo(artifact: str, confirmed: bool = False) -> dict | None:
    """Raises NeedsVersion when the caller must ask first; call again with `confirmed=True`."""
    sync()
    if not can_undo(artifact):
        return None
    unit = _stacks(artifact)[0][-1]
    return _move(
        artifact,
        unit[0]["before"],
        "undo",
        f"Undid: {unit[-1]['summary']}",
        confirmed,
        unit[0].get("snapshot"),
    )


def redo(artifact: str, confirmed: bool = False) -> dict | None:
    sync()
    if not can_redo(artifact):
        return None
    unit, undone = _stacks(artifact)[1][-1]
    return _move(
        artifact,
        unit[-1]["after"],
        "redo",
        f"Redid: {unit[-1]['summary']}",
        confirmed,
        undone.get("snapshot") if unit[0].get("snapshot") else None,
    )


def _object(object_hash: str | None) -> bytes:
    return (_dir() / "objects" / str(object_hash)).read_bytes()


def restore(artifact: str, seq: int, confirmed: bool = False) -> dict:
    """Make the file as it was after entry `seq`; a normal, undoable edit."""
    sync()
    entry = next(e for e in entries(artifact) if e["seq"] == seq)
    if entry["after"] is None:
        raise ValueError(f"entry {seq} left no file to restore")
    if entry["after"] == _current(artifact):
        return entries(artifact)[-1]
    return _move(
        artifact,
        entry["after"],
        "restore",
        f"Restored: {entry['summary']}",
        confirmed,
    )


def is_current(entry: dict) -> bool:
    """The newest entry of its file."""
    if entry["kind"] != "edit":
        return False
    return entries(entry["artifact"])[-1]["seq"] == entry["seq"]


def approval(stage: int, flag: str, inputs: dict, summary: str) -> None:
    _append(
        {
            "kind": "approval",
            "summary": summary,
            "stage": stage,
            "flag": flag,
            "inputs": inputs,
        }
    )
