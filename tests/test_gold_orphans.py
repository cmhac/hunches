"""Spec 004 task 06: gold orphans, coverage, removal."""

import json

import pytest
from test_status import complete_project, status

from hunches import files
from hunches.files import GoldRow
from hunches.screens import gold as gold_mod


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def pool(ids) -> None:
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": i, "text": f"item {i}", "max_similarity": 0.7, "best_seed": "x"}
            for i in ids
        ],
    )


def row(id, split="dev", labels=("a",)) -> GoldRow:
    return GoldRow(id=id, text=f"text {id}", labels=list(labels), split=split)


def test_orphaned_gold_is_exactly_the_rows_missing_from_the_pool():
    pool(["a", "b", "c"])
    files.write_gold(
        [row("a"), row("x"), row("b", "test"), row("y", "test"), row("z", labels=())]
    )
    assert [r.id for r in files.orphaned_gold()] == ["x", "y", "z"]
    assert [r.id for r in files.orphaned_gold("dev")] == ["x", "z"]
    assert [r.id for r in files.orphaned_gold("test")] == ["y"]


def test_orphaned_gold_with_no_candidates_file_is_every_row():
    files.write_gold([row("a")])
    assert [r.id for r in files.orphaned_gold()] == ["a"]


def test_gold_coverage_counts_per_split():
    pool(["a", "b"])
    files.write_gold(
        [
            row("a", labels=("p",)),
            row("x", labels=("p",)),
            row("y", labels=("p", "q")),
            row("z", labels=()),
            row("t1", "test"),
        ]
    )
    assert files.gold_coverage() == {
        "dev": {
            "rows": 4,
            "labelled": 3,
            "orphaned": 3,
            "orphaned_labelled": 2,
            "orphaned_by_label": {"p": 2, "q": 1},
        },
        "test": {
            "rows": 1,
            "labelled": 1,
            "orphaned": 1,
            "orphaned_labelled": 1,
            "orphaned_by_label": {"a": 1},
        },
    }


def test_remove_moves_rows_to_append_only_log_and_returns_count():
    pool(["a"])
    files.write_gold([row("a"), row("x", labels=("p", "q")), row("y", "test")])
    assert gold_mod.remove(["x", "nope"], "no longer in pool") == 1
    assert [r.id for r in files.read_gold()] == ["a", "y"]
    (logged,) = files.read_jsonl("gold_removed.jsonl")
    assert logged["id"] == "x" and logged["labels"] == ["p", "q"]
    assert logged["text"] == "text x" and logged["split"] == "dev"
    assert logged["reason"] == "no longer in pool" and logged["ts"]
    first = (files.root() / "gold_removed.jsonl").read_text()
    assert gold_mod.remove(["y"], "again") == 1
    assert (files.root() / "gold_removed.jsonl").read_text().startswith(first)
    assert [r["id"] for r in files.read_jsonl("gold_removed.jsonl")] == ["x", "y"]


def test_remove_nothing_writes_no_file():
    files.write_gold([row("a")])
    assert gold_mod.remove([], "r") == 0
    assert gold_mod.remove(["zz"], "r") == 0
    assert not (files.root() / "gold_removed.jsonl").exists()


def test_draw_never_returns_removed_ids():
    pool(["a", "b", "c"])
    files.write_gold([row("a")])
    gold_mod.remove(["a"], "r")
    drawn = gold_mod.draw("dev", 10)
    assert sorted(r.id for r in drawn) == ["b", "c"]
    assert all(r.labels == [] for r in drawn)


def test_removing_dev_rows_resumes_at_stage_4_and_marks_tuning_stale():
    complete_project()
    pool(["c1", "c2", "c3"])
    files.write_gold(
        [row(f"c{i}") for i in (1, 2, 3)]
        + [row(f"d{i}") for i in range(47)]
        + [row(f"t{i}", "test") for i in range(50)]
    )
    files.approve("dev_done", 5, "s")
    files.approve("test_done", 6, "s")
    assert files.first_incomplete_stage() != 4
    gold_mod.remove([f"d{i}" for i in range(6)], "r")
    assert files.stage_status()[4] == ("incomplete", "44 of 50 rows")
    assert files.stage_status()[5] == ("stale", "gold rows changed")
    assert files.first_incomplete_stage() == 4
    gold_mod.draw("dev", 6)  # unlabelled rows do not count
    assert status(4) == "incomplete"


def test_removing_test_rows_resumes_at_stage_6_and_marks_result_stale():
    complete_project()
    files.write_text(
        "test_result.json", json.dumps({"inputs": files.current_inputs("test_done")})
    )
    assert files.stage_status()[6][0] == "current"
    gold_mod.remove(["t0", "t1"], "r")
    assert files.stage_status()[6] == ("incomplete", "48 of 50 rows")
    assert files.first_incomplete_stage() == 6
