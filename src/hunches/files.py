import json
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator, model_validator
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    UserPromptPart,
)
from pydantic_ai.settings import ModelSettings, ThinkingEffort

OFF_TOPIC = "off_topic"
SAMPLE_SIZE = 50  # gold rows per split (spec stages 4 and 6)


class Config(BaseModel):
    backend: Literal["local", "s3"] = "local"
    corpus_dir: str | None = (
        None  # local backend: dir with vectors.npy, items.jsonl, meta.json
    )
    s3_bucket: str | None = None
    s3_index: str | None = None
    embedding_model: str = ""
    s3_region: str | None = None  # None: boto3's default resolution
    assistant_model: str
    assistant_thinking: ThinkingEffort | None = None  # None: no thinking setting
    classifier_model: str
    target_metric: Literal["accuracy", "macro_f1", "micro_f1", "exact_match"] = (
        "accuracy"
    )
    target_score: float = 0.90

    @model_validator(mode="before")
    @classmethod
    def _old_keys(cls, data):
        # 001 wrote smart_model/cheap_model; a new key wins over an old one
        if isinstance(data, dict):
            data = dict(data)
            for old, new in [
                ("smart_model", "assistant_model"),
                ("cheap_model", "classifier_model"),
            ]:
                if old in data:
                    data.setdefault(new, data.pop(old))
                    data.pop(old, None)
        return data


def thinking_settings(config: Config) -> ModelSettings | None:
    """model_settings for assistant Agents; None leaves the provider's default."""
    if config.assistant_thinking is None:
        return None
    return {"thinking": config.assistant_thinking}


class State(BaseModel):
    seeds_approved: bool = False
    taxonomy_approved: bool = False
    dev_done: bool = False
    test_done: bool = False
    threshold_chosen: bool = False


class Label(BaseModel):
    name: str
    description: str = ""


class Taxonomy(BaseModel):
    mode: Literal["single", "multi"]
    labels: list[Label]

    @field_validator("labels")
    @classmethod
    def _no_off_topic(cls, labels: list[Label]) -> list[Label]:
        if any(label.name == OFF_TOPIC for label in labels):
            raise ValueError(f"'{OFF_TOPIC}' is built in; do not list it")
        return labels


class GoldRow(BaseModel):
    id: str
    text: str
    labels: list[str]
    split: Literal["dev", "test"]


def root() -> Path:
    return Path(".hunches")


def ensure_root() -> Path:
    root().mkdir(exist_ok=True)
    return root()


def read_text(name: str) -> str | None:
    """Read a text file in .hunches/ (seeds.csv, brief.md, prompt.md, ...); None if missing."""
    path = root() / name
    return path.read_text() if path.exists() else None


def write_text(name: str, text: str) -> None:
    ensure_root()
    (root() / name).write_text(text)


def read_config(project: Path | None = None) -> Config:
    """Read config.toml of `project` (default: the current directory's project)."""
    path = (project / ".hunches" if project else root()) / "config.toml"
    return Config.model_validate(tomllib.loads(path.read_text()))


def write_config(config: Config, project: Path | None = None) -> None:
    # json.dumps output is a valid TOML basic string / number / bool for our value types
    lines = [
        f"{k} = {json.dumps(v)}"
        for k, v in config.model_dump().items()
        if v is not None
    ]
    text = "\n".join(lines) + "\n"
    if project:  # another project's config: never chdir to it
        (project / ".hunches" / "config.toml").write_text(text)
    else:
        write_text("config.toml", text)


def read_state() -> State:
    path = root() / "state.json"
    return State.model_validate_json(path.read_text()) if path.exists() else State()


def write_state(state: State) -> None:
    write_text("state.json", state.model_dump_json(indent=2) + "\n")


def read_jsonl(name: str) -> list[dict]:
    path = root() / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(name: str, rows: list[dict]) -> None:
    write_text(name, "".join(json.dumps(r) + "\n" for r in rows))


def append_jsonl(name: str, row: dict) -> None:
    ensure_root()
    with (root() / name).open("a") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()


def read_taxonomy() -> Taxonomy:
    return Taxonomy.model_validate(
        yaml.safe_load((root() / "taxonomy.yaml").read_text())
    )


def write_taxonomy(taxonomy: Taxonomy) -> None:
    write_text("taxonomy.yaml", yaml.safe_dump(taxonomy.model_dump(), sort_keys=False))


def all_labels(taxonomy: Taxonomy) -> list[str]:
    return [label.name for label in taxonomy.labels] + [OFF_TOPIC]


def validate_labels(labels: list[str], taxonomy: Taxonomy) -> None:
    """Raise ValueError unless labels obey the spec rules (gold and predicted alike)."""
    if not labels:
        raise ValueError("at least one label is required")
    unknown = set(labels) - set(all_labels(taxonomy))
    if unknown:
        raise ValueError(f"unknown labels: {sorted(unknown)}")
    if OFF_TOPIC in labels and len(set(labels)) > 1:
        raise ValueError(f"'{OFF_TOPIC}' must be the only label")
    if taxonomy.mode == "single" and len(labels) != 1:
        raise ValueError("single mode requires exactly one label")


def read_gold() -> list[GoldRow]:
    return [GoldRow.model_validate(r) for r in read_jsonl("gold.jsonl")]


def write_gold(rows: list[GoldRow]) -> None:
    write_jsonl("gold.jsonl", [r.model_dump() for r in rows])


# ---- taxonomy versions (spec 003, D12): archives are only ever added to, never deleted
VERSIONED = ["taxonomy.yaml", "prompt.md", "gold.jsonl", "state.json"]
DERIVED = [
    "test_result.json",
    "threshold.json",
    "threshold_sample.json",
    "results.jsonl",
]


def taxonomy_in_use() -> bool:
    """True when any gold row has labels, i.e. changing the label set would invalidate work."""
    return any(r["labels"] for r in read_jsonl("gold.jsonl"))


def labels_changed(old: Taxonomy, new: Taxonomy) -> bool:
    """The mode or the set of label names differs (order and descriptions do not matter)."""
    return old.mode != new.mode or {x.name for x in old.labels} != {
        x.name for x in new.labels
    }


def version_numbers() -> list[int]:
    path = root() / "versions"
    if not path.exists():
        return []
    return sorted(int(p.name) for p in path.iterdir() if p.name.isdigit())


def list_versions() -> list[dict]:
    return [
        json.loads((root() / "versions" / str(n) / "meta.json").read_text())
        for n in version_numbers()
    ]


def archive_version(note: str = "") -> int:
    """Copy the live version into the next `versions/<n>/` and return n. Copies; changes nothing else."""
    numbers = version_numbers()
    n = numbers[-1] + 1 if numbers else 1
    target = root() / "versions" / str(n)
    target.mkdir(parents=True)  # raises if it exists: an archive is never overwritten
    for name in [*VERSIONED, *DERIVED]:
        if (root() / name).exists():
            shutil.copy2(root() / name, target / name)
    gold = read_jsonl("gold.jsonl")
    try:
        taxonomy = read_taxonomy()
        mode, names = taxonomy.mode, [x.name for x in taxonomy.labels]
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        mode, names = None, []
    meta = {
        "version": n,
        "created_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "labels": names,
        "dev_labelled": sum(r["split"] == "dev" and bool(r["labels"]) for r in gold),
        "test_labelled": sum(r["split"] == "test" and bool(r["labels"]) for r in gold),
        "note": note,
    }
    (target / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return n


def start_new_version(new: Taxonomy) -> int:
    """Archive the current version, then write `new` with the same gold items unlabelled. Returns the
    archived version's number. Archiving comes first so a crash afterwards loses nothing."""
    n = archive_version()
    write_taxonomy(new)
    write_gold([r.model_copy(update={"labels": []}) for r in read_gold()])
    state = read_state()
    state.taxonomy_approved = state.dev_done = state.test_done = False
    state.threshold_chosen = False
    write_state(state)
    for (
        name
    ) in DERIVED:  # the archive holds them; the live copies describe the old labels
        (root() / name).unlink(missing_ok=True)
    return n


def restore_version(n: int) -> None:
    """Make archived version n live again. The current state is archived first as a new version."""
    source = root() / "versions" / str(n)
    if not (source / "meta.json").exists():
        raise FileNotFoundError(f"no archived version {n}")
    archive_version(f"before restoring version {n}")
    for name in [*VERSIONED, *DERIVED]:
        if (source / name).exists():
            shutil.copy2(source / name, root() / name)
        elif name in DERIVED:
            (root() / name).unlink(missing_ok=True)


def edit_message(summary: str, body: str) -> ModelRequest:
    """The record of a user edit, delivered with the agent's next turn (no model call). `body` carries the
    diff detail and the `# Current <artifact>` section; the chat shows `summary` as a YOU EDITED line."""
    text = (
        f"# What changed\n{summary}\n\n{body}\n\n# Instructions\n"
        "No reply needed. Treat this as the current state in your next turn."
    )
    return ModelRequest(
        parts=[UserPromptPart(content=text)],
        metadata={"hunches": "edit", "summary": summary},
    )


def save_chat(stage: str, messages: list[ModelMessage]) -> None:
    """Persist the history. Per-run `instructions` are recomputed every run, so they are not stored."""
    for message in messages:
        if isinstance(message, ModelRequest):
            message.instructions = None
    ensure_root()
    (root() / "chat").mkdir(exist_ok=True)
    (root() / "chat" / f"{stage}.json").write_bytes(
        ModelMessagesTypeAdapter.dump_json(messages)
    )


def load_chat(stage: str) -> list[ModelMessage]:
    path = root() / "chat" / f"{stage}.json"
    return (
        ModelMessagesTypeAdapter.validate_json(path.read_bytes())
        if path.exists()
        else []
    )


def first_incomplete_stage() -> int:
    """Return the first incomplete stage, 1-9. Rules, checked in order:

    1 seeds.csv missing or `seeds_approved` false
    2 candidates.jsonl missing or empty
    3 taxonomy.yaml or prompt.md missing, or `taxonomy_approved` false
    4 fewer than SAMPLE_SIZE labelled gold rows with split "dev" (sampled rows are persisted
      with empty labels, so unlabelled rows do not count)
    5 `dev_done` false (tuning not accepted)
    6 fewer than SAMPLE_SIZE labelled gold rows with split "test", or `test_done` false
    7 `threshold_chosen` false or threshold.json missing
    8 some candidate with max_similarity >= threshold.json["threshold"] has no successful row in results.jsonl (rows with an "error" key don't count)
    9 otherwise (browse)
    """
    state = read_state()
    gold = read_jsonl("gold.jsonl")
    if read_text("seeds.csv") is None or not state.seeds_approved:
        return 1
    if not read_jsonl("candidates.jsonl"):
        return 2
    if (
        read_text("taxonomy.yaml") is None
        or read_text("prompt.md") is None
        or not state.taxonomy_approved
    ):
        return 3
    if sum(r["split"] == "dev" and bool(r["labels"]) for r in gold) < SAMPLE_SIZE:
        return 4
    if not state.dev_done:
        return 5
    if (
        sum(r["split"] == "test" and bool(r["labels"]) for r in gold) < SAMPLE_SIZE
        or not state.test_done
    ):
        return 6
    threshold_text = read_text("threshold.json")
    if threshold_text is None or not state.threshold_chosen:
        return 7
    cutoff = json.loads(threshold_text)["threshold"]
    # error rows (failed items, retried by the next run) do not count as done
    done = {r["id"] for r in read_jsonl("results.jsonl") if "error" not in r}
    if any(
        c["max_similarity"] >= cutoff and c["id"] not in done
        for c in read_jsonl("candidates.jsonl")
    ):
        return 8
    return 9
