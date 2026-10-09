import hashlib
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
    # per approved flag, the components of its inputs at approval time (spec 004); absent = current
    inputs: dict[str, dict[str, str]] = {}


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
    _MEMO.pop(root().absolute() / name, None)
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


# ---- recorded inputs (spec 004): the named components a stage's work depends on
COMPONENTS = [  # most upstream first: the first one that differs is the reason shown
    "seeds",
    "embedding_model",
    "candidates",
    "prompt",
    "taxonomy",
    "classifier_model",
    "gold_dev",
    "gold_test",
]
INPUTS = {  # per approved flag; seeds_approved and taxonomy_approved record nothing
    "dev_done": ["prompt", "taxonomy", "classifier_model", "gold_dev"],
    "test_done": ["prompt", "taxonomy", "classifier_model", "gold_test"],
    "threshold_chosen": ["prompt", "taxonomy", "classifier_model", "candidates"],
}
REASONS = {  # at most 24 characters each
    "seeds": "seeds changed",
    "embedding_model": "embedding model changed",
    "candidates": "candidates changed",
    "prompt": "prompt changed",
    "taxonomy": "taxonomy changed",
    "classifier_model": "classifier model changed",
    "gold_dev": "gold rows changed",
    "gold_test": "gold rows changed",
    "classifier_input": "classifier input changed",
}
Status = Literal["current", "stale", "incomplete", "not_started"]

# big files are parsed once per change: (path) -> (stat stamp, parsed). Writers in this module drop
# their entry; a change from outside shows in the stamp.
_MEMO: dict[Path, tuple[tuple[int, int, int], object]] = {}


def _memo(name: str, parse):
    path = root().absolute() / name
    try:
        st = path.stat()
    except OSError:
        return parse()  # missing file: parse() handles it and is cheap
    stamp = (st.st_mtime_ns, st.st_size, st.st_ino)
    hit = _MEMO.get(path)
    if hit and hit[0] == stamp:
        return hit[1]
    value = parse()
    _MEMO[path] = (stamp, value)
    return value


def _sha(data) -> str:
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


def _candidates() -> tuple[str, list[tuple[str, float]]]:
    """(digest of the sorted candidate ids, [(id, max_similarity)])."""

    def parse():
        rows = read_jsonl("candidates.jsonl")
        sims = [(r["id"], r["max_similarity"]) for r in rows]
        return _sha(sorted(i for i, _ in sims)), sims

    return _memo("candidates.jsonl", parse)


def _gold() -> tuple[int, int, str, str]:
    """(labelled dev rows, labelled test rows, dev digest, test digest)."""

    def parse():
        by_split: dict[str, list] = {"dev": [], "test": []}
        for r in read_jsonl("gold.jsonl"):
            if r["labels"]:
                by_split[r["split"]].append([r["id"], sorted(r["labels"])])
        dev, test = (sorted(by_split[s]) for s in ("dev", "test"))
        return len(dev), len(test), _sha(dev), _sha(test)

    return _memo("gold.jsonl", parse)


def _results() -> list[tuple[str, str | None]]:
    """(id, run) of every successful row in results.jsonl; run is None on rows from before 004."""

    def parse():
        return [
            (r["id"], r.get("run"))
            for r in read_jsonl("results.jsonl")
            if "error" not in r
        ]

    return _memo("results.jsonl", parse)


def _config() -> Config | None:
    try:
        return read_config()
    except (OSError, ValueError):  # no config.toml yet (tests, a project being created)
        return None


def _taxonomy() -> Taxonomy | None:
    try:
        return read_taxonomy()
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        return None


def components() -> dict[str, str]:
    """Every component as it is now."""
    from hunches import candidates  # candidates imports this module

    config, taxonomy = _config(), _taxonomy()
    stripped = (read_text("prompt.md") or "").strip()
    return {
        "seeds": candidates.seeds_digest(candidates.read_seeds()),
        "embedding_model": config.embedding_model if config else "",
        "candidates": _candidates()[0],
        "prompt": hashlib.sha256(stripped.encode()).hexdigest(),
        "taxonomy": _sha(
            [taxonomy.mode, [[x.name, x.description] for x in taxonomy.labels]]
            if taxonomy
            else None
        ),
        "classifier_model": config.classifier_model if config else "",
        "gold_dev": _gold()[2],
        "gold_test": _gold()[3],
    }


def current_inputs(flag: str) -> dict[str, str]:
    """The components `flag`'s stage depends on, as they are now."""
    names = INPUTS.get(flag, [])
    now = components() if names else {}
    return {name: now[name] for name in names}


def changed(recorded: dict[str, str], now: dict[str, str] | None = None) -> list[str]:
    """The recorded components that differ from `now` (default: the current ones), upstream first."""
    now = components() if now is None else now
    return [c for c in COMPONENTS if c in recorded and recorded[c] != now.get(c)]


def run_digest(prompt: str, taxonomy: Taxonomy, model: str) -> str:
    """What the classifier cache key hashes minus the item text: equal digests mean cache hits."""
    from hunches import classifier  # classifier imports this module

    return _sha([model, classifier.system_prompt(prompt, taxonomy)])


def current_run() -> str | None:
    """run_digest of the project as it is now; None while there is no taxonomy or config."""
    config, taxonomy = _config(), _taxonomy()
    if config is None or taxonomy is None:
        return None
    return run_digest(read_text("prompt.md") or "", taxonomy, config.classifier_model)


def legacy_prompt_hash() -> str:
    """The 001-003 `test_result.json` hash; only used to compare a file that has no `inputs`."""
    config = _config()
    return _sha(
        [read_text("prompt.md") or "", config.classifier_model if config else ""]
    )


def result_changes(result: dict, now: dict[str, str] | None = None) -> list[str]:
    """Components a test_result.json was computed under that differ now. Legacy files compare `prompt_hash`."""
    if "inputs" in result:
        return changed(result["inputs"], now)
    if "prompt_hash" in result and result["prompt_hash"] != legacy_prompt_hash():
        return ["prompt"]
    return []


def done_result_ids() -> set[str]:
    """Ids with a successful row classified under the current run (rows without `run` count)."""
    run = current_run()
    return {i for i, r in _results() if r is None or r == run}


def approve(flag: str, stage: int, summary: str) -> None:
    """Set a State flag, record the inputs it was approved under and log the approval."""
    from hunches import history  # history imports this module

    state = read_state()
    setattr(state, flag, True)
    state.inputs[flag] = current_inputs(flag)
    write_state(state)
    history.approval(stage, flag, state.inputs[flag], summary)


def read_jsonl(name: str) -> list[dict]:
    path = root() / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(name: str, rows: list[dict]) -> None:
    write_text(name, "".join(json.dumps(r) + "\n" for r in rows))


def append_jsonl(name: str, row: dict) -> None:
    ensure_root()
    _MEMO.pop(root().absolute() / name, None)
    with (root() / name).open("a") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()


def read_taxonomy() -> Taxonomy:
    return Taxonomy.model_validate(
        yaml.safe_load((root() / "taxonomy.yaml").read_text())
    )


def taxonomy_yaml(taxonomy: Taxonomy) -> str:
    return yaml.safe_dump(taxonomy.model_dump(), sort_keys=False)


def write_taxonomy(taxonomy: Taxonomy) -> None:
    write_text("taxonomy.yaml", taxonomy_yaml(taxonomy))


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


RESULT_FILE = "test_result.json"


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
    for flag in ("taxonomy_approved", "dev_done", "test_done", "threshold_chosen"):
        state.inputs.pop(flag, None)  # inputs only describe a flag that is set
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


def _union(*lists: list[str]) -> list[str]:
    return [c for c in COMPONENTS if any(c in x for x in lists)]


def _recorded_in(name: str) -> dict[str, str]:
    """The `inputs` a derived file recorded, {} if it has none or is unreadable."""
    try:
        return json.loads(read_text(name) or "{}").get("inputs", {})
    except (ValueError, AttributeError):
        return {}


def stage_status() -> dict[int, tuple[Status, str]]:
    """Status and reason (at most 24 characters, "" if current) of stages 1-9.

    Completion rules:
    1 seeds.csv exists and `seeds_approved`
    2 candidates.jsonl is not empty
    3 taxonomy.yaml and prompt.md exist and `taxonomy_approved`
    4 at least SAMPLE_SIZE labelled gold rows with split "dev"
    5 `dev_done`
    6 at least SAMPLE_SIZE labelled "test" gold rows and `test_done`
    7 `threshold_chosen` and threshold.json exists
    8 every candidate with max_similarity >= the threshold has a successful row in results.jsonl
      classified under the current run (a row without `run` counts as current)
    9 stage 8 is complete (browse)

    A complete stage is `stale` when a component recorded for it differs now, else `current`. An
    incomplete one is `incomplete` if it was complete before (its flag is set or a later stage is
    complete), else `not_started`. Stage 8 is `stale` when it has rows made under another run.
    """
    state = read_state()
    now = components()
    dev_n, test_n = _gold()[:2]
    sims = _candidates()[1]
    threshold = json.loads(read_text("threshold.json") or "{}").get("threshold")
    above = {i for i, sim in sims if threshold is not None and sim >= threshold}
    run = current_run()
    rows = _results()
    stale_rows = any(r is not None and r != run and i in above for i, r in rows)
    done = {i for i, r in rows if r is None or r == run}
    has_taxonomy = read_text("taxonomy.yaml") is not None
    has_prompt = read_text("prompt.md") is not None
    complete = {
        1: read_text("seeds.csv") is not None and state.seeds_approved,
        2: bool(sims),
        3: has_taxonomy and has_prompt and state.taxonomy_approved,
        4: dev_n >= SAMPLE_SIZE,
        5: state.dev_done,
        6: test_n >= SAMPLE_SIZE and state.test_done,
        7: threshold is not None and state.threshold_chosen,
        8: threshold is not None and above <= done,
    }
    complete[9] = complete[8]
    flags = {
        1: state.seeds_approved,
        3: state.taxonomy_approved,
        5: state.dev_done,
        6: state.test_done,
        7: state.threshold_chosen,
    }
    meta = json.loads(read_text("candidates.meta.json") or "{}")
    recorded_meta = {}
    if "seeds_digest" in meta:
        recorded_meta["seeds"] = meta["seeds_digest"]
    if "embedding_model" in meta:
        recorded_meta["embedding_model"] = meta["embedding_model"]
    try:
        test_result = json.loads(read_text(RESULT_FILE) or "{}")
    except ValueError:
        test_result = {}
    differs = {
        2: changed(recorded_meta, now),
        5: changed(state.inputs.get("dev_done", {}), now),
        6: _union(
            changed(state.inputs.get("test_done", {}), now),
            result_changes(test_result, now),
        ),
        7: _union(
            changed(state.inputs.get("threshold_chosen", {}), now),
            changed(_recorded_in("threshold.json"), now),
        ),
    }
    not_done = {
        1: "not approved" if read_text("seeds.csv") is not None else "no seeds",
        2: "no candidates",
        3: "not approved" if has_taxonomy and has_prompt else "files missing",
        4: f"{dev_n} of {SAMPLE_SIZE} rows",
        5: "not accepted",
        6: f"{test_n} of {SAMPLE_SIZE} rows"
        if test_n < SAMPLE_SIZE
        else "not accepted",
        7: "not chosen",
    }
    status: dict[int, tuple[Status, str]] = {}
    for n in range(1, 10):
        if complete[n]:
            why = differs.get(n, [])
            status[n] = ("stale", REASONS[why[0]]) if why else ("current", "")
        elif n == 8 and stale_rows:
            upstream = status[7]
            status[n] = (
                "stale",
                upstream[1] if upstream[0] == "stale" else REASONS["classifier_input"],
            )
        elif flags.get(n) or any(complete[m] for m in range(n + 1, 10)):
            status[n] = ("incomplete", not_done[n])
        else:
            status[n] = ("not_started", "")
    return status


def first_incomplete_stage() -> int:
    """The lowest stage, 1-9, that is not current (stale, incomplete or not started); 9 when all are
    current. The completion rules are in `stage_status`."""
    status = stage_status()
    return next((n for n in range(1, 10) if status[n][0] != "current"), 9)
