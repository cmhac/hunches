import json
import re
from pathlib import Path

import pytest

from hunches import files


def tax(mode="single", labels=(("a", "x"), ("b", "y"))):
    return files.Taxonomy(
        mode=mode, labels=[files.Label(name=n, description=d) for n, d in labels]
    )


def project(tmp_path, monkeypatch, dev=50, test=50):
    """A finished-through-threshold project: 100 labelled gold rows and every derived file."""
    monkeypatch.chdir(tmp_path)
    files.write_taxonomy(tax())
    files.write_text("prompt.md", "Classify.\n")
    rows = [
        files.GoldRow(id=f"d{i}", text=f"dev text {i}", labels=["a"], split="dev")
        for i in range(dev)
    ] + [
        files.GoldRow(id=f"t{i}", text=f"test text {i}", labels=["b"], split="test")
        for i in range(test)
    ]
    files.write_gold(rows)
    files.write_text("seeds.csv", "seed\nx\n")
    files.write_jsonl(
        "candidates.jsonl", [{"id": "d0", "text": "t", "max_similarity": 0.9}]
    )
    files.write_state(
        files.State(
            seeds_approved=True,
            taxonomy_approved=True,
            dev_done=True,
            test_done=True,
            threshold_chosen=True,
        )
    )
    files.write_text("test_result.json", '{"accuracy": 0.9}')
    files.write_text("threshold.json", '{"threshold": 0.7}')
    files.write_text("threshold_sample.json", '{"sample": []}')
    files.write_jsonl("results.jsonl", [{"id": "d0", "labels": ["a"]}])


def snapshot_bytes(directory: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def test_labels_changed():
    base = tax()
    assert files.labels_changed(base, tax(labels=(("a", "x"), ("c", "y"))))  # rename
    assert files.labels_changed(base, tax(labels=(("a", "x"), ("b", "y"), ("c", ""))))
    assert files.labels_changed(base, tax(labels=(("a", "x"),)))  # delete
    assert files.labels_changed(base, tax(mode="multi"))
    assert not files.labels_changed(base, tax(labels=(("a", "other"), ("b", ""))))
    assert not files.labels_changed(base, tax(labels=(("b", "y"), ("a", "x"))))


def test_taxonomy_in_use(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not files.taxonomy_in_use()  # no gold file
    files.write_gold([files.GoldRow(id="1", text="t", labels=[], split="dev")])
    assert not files.taxonomy_in_use()  # sampled but unlabelled
    files.write_gold([files.GoldRow(id="1", text="t", labels=["a"], split="dev")])
    assert files.taxonomy_in_use()


def test_archive_copies_and_writes_meta(tmp_path, monkeypatch):
    project(tmp_path, monkeypatch, dev=3, test=2)
    before = snapshot_bytes(Path(".hunches"))
    assert files.list_versions() == []
    assert files.archive_version("hello") == 1
    assert snapshot_bytes(Path(".hunches")) == {
        **before,
        **{
            f"versions/1/{name}": before[name]
            for name in (
                "taxonomy.yaml",
                "prompt.md",
                "gold.jsonl",
                "state.json",
                "test_result.json",
                "threshold.json",
                "threshold_sample.json",
                "results.jsonl",
            )
        },
        "versions/1/meta.json": Path(".hunches/versions/1/meta.json").read_bytes(),
    }
    [meta] = files.list_versions()
    assert {k: v for k, v in meta.items() if k != "created_at"} == {
        "version": 1,
        "mode": "single",
        "labels": ["a", "b"],
        "dev_labelled": 3,
        "test_labelled": 2,
        "note": "hello",
    }
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT.*(\+00:00|Z)", meta["created_at"])
    assert files.archive_version() == 2  # never overwrites


def test_archive_skips_missing_derived_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.write_taxonomy(tax())
    files.write_gold([])
    assert files.archive_version() == 1
    assert sorted(p.name for p in Path(".hunches/versions/1").iterdir()) == [
        "gold.jsonl",
        "meta.json",
        "taxonomy.yaml",
    ]


def test_start_new_version(tmp_path, monkeypatch):
    project(tmp_path, monkeypatch)
    old = snapshot_bytes(Path(".hunches"))
    new = tax(labels=(("a", "x"), ("c", "z")))
    assert files.start_new_version(new) == 1
    live = Path(".hunches")
    gold = files.read_gold()
    assert [(r.id, r.text, r.split) for r in gold] == [
        (f"d{i}", f"dev text {i}", "dev") for i in range(50)
    ] + [(f"t{i}", f"test text {i}", "test") for i in range(50)]
    assert all(r.labels == [] for r in gold)
    for name in (
        "test_result.json",
        "threshold.json",
        "threshold_sample.json",
        "results.jsonl",
    ):
        assert not (live / name).exists()
    assert files.read_state() == files.State(seeds_approved=True)
    assert files.read_taxonomy() == new
    assert files.read_text("prompt.md") == "Classify.\n"
    assert (live / "seeds.csv").exists() and (live / "candidates.jsonl").exists()
    assert files.first_incomplete_stage() == 3
    archived = snapshot_bytes(live / "versions" / "1")
    assert {k: v for k, v in archived.items() if k != "meta.json"} == {
        k: v
        for k, v in old.items()
        if k
        in (
            "taxonomy.yaml",
            "prompt.md",
            "gold.jsonl",
            "state.json",
            "test_result.json",
            "threshold.json",
            "threshold_sample.json",
            "results.jsonl",
        )
    }
    meta = json.loads(archived["meta.json"])
    assert meta["dev_labelled"] == 50 and meta["test_labelled"] == 50
    assert meta["labels"] == ["a", "b"]
    assert not files.taxonomy_in_use()


def test_restore_returns_bytes_and_archives_current(tmp_path, monkeypatch):
    project(tmp_path, monkeypatch)
    live = Path(".hunches")
    original = {
        name: (live / name).read_bytes()
        for name in (
            "taxonomy.yaml",
            "prompt.md",
            "gold.jsonl",
            "state.json",
            "test_result.json",
            "threshold.json",
            "threshold_sample.json",
            "results.jsonl",
        )
    }
    files.start_new_version(tax(mode="multi", labels=(("q", ""),)))
    files.write_text("prompt.md", "Revised.\n")
    v1 = snapshot_bytes(live / "versions" / "1")
    after_change = {
        n: (live / n).read_bytes() for n in ("taxonomy.yaml", "prompt.md", "gold.jsonl")
    }
    files.restore_version(1)
    for name, data in original.items():
        assert (live / name).read_bytes() == data
    assert snapshot_bytes(live / "versions" / "1") == v1  # untouched
    v2 = live / "versions" / "2"
    assert (v2 / "taxonomy.yaml").read_bytes() == after_change["taxonomy.yaml"]
    assert (v2 / "prompt.md").read_bytes() == after_change["prompt.md"]
    assert (v2 / "gold.jsonl").read_bytes() == after_change["gold.jsonl"]
    assert "before restoring version 1" in files.list_versions()[1]["note"]


def test_restore_removes_derived_files_the_version_lacked(tmp_path, monkeypatch):
    project(tmp_path, monkeypatch)
    files.start_new_version(tax(labels=(("z", ""),)))  # v1 has derived files
    files.write_text("results.jsonl", '{"id": "n"}\n')  # a live one v2 will own
    files.start_new_version(tax(labels=(("y", ""),)))  # v2 archived without them...
    files.write_text("threshold.json", '{"threshold": 0.1}')
    files.restore_version(2)  # v2 had no threshold.json
    assert not Path(".hunches/threshold.json").exists()
    assert Path(".hunches/versions/3/threshold.json").exists()  # kept in the archive


def test_versions_only_grow_and_no_code_deletes_them(tmp_path, monkeypatch):
    project(tmp_path, monkeypatch)
    counts = []

    def count() -> int:
        return (
            sum(1 for _ in Path(".hunches/versions").rglob("*"))
            if Path(".hunches/versions").exists()
            else 0
        )

    for step in (
        lambda: files.start_new_version(tax(labels=(("c", ""),))),
        lambda: files.restore_version(1),
        lambda: files.restore_version(1),
        lambda: files.archive_version(),
        lambda: files.start_new_version(tax(mode="multi")),
        lambda: files.restore_version(2),
    ):
        step()
        counts.append(count())
    assert counts == sorted(counts) and len(set(counts)) == len(counts)
    assert len(files.list_versions()) == 6
    # 4 restores/starts/archives each made one directory: 1,2,3,4,5,6 all present
    assert [v["version"] for v in files.list_versions()] == [1, 2, 3, 4, 5, 6]


def test_restore_unknown_version_changes_nothing(tmp_path, monkeypatch):
    project(tmp_path, monkeypatch)
    before = snapshot_bytes(Path(".hunches"))
    with pytest.raises(FileNotFoundError):
        files.restore_version(7)
    assert snapshot_bytes(Path(".hunches")) == before


def test_no_source_line_deletes_under_versions():
    """A grep-style guard: nothing that removes files may mention the versions directory."""
    src = Path(__file__).parent.parent / "src" / "hunches"
    removal = re.compile(
        r"rmtree|\.unlink\(|os\.remove|os\.rmdir|\.rmdir\(|shutil\.move"
    )
    for path in src.rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if removal.search(line):
                assert "versions" not in line.lower(), f"{path.name}:{number}: {line}"
    text = (src / "files.py").read_text()
    # every removal in files.py is of a live file, named by a variable that is a derived name
    for line in text.splitlines():
        if ".unlink(" in line:
            assert "DERIVED" in line or "name" in line
