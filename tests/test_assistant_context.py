"""Spec 004 task 07: status and gold-coverage context for the assistants."""

import pytest
from test_status import complete_project, config, gold

from hunches import files
from hunches.files import GoldRow


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_status_section_lists_the_nine_stages_with_marks_and_reasons():
    complete_project()
    files.write_text("prompt.md", "changed")
    text = files.pipeline_status_text()
    assert text.splitlines() == [
        "# Pipeline status",
        "1 Brief and seeds: current",
        "2 Search: current",
        "3 Taxonomy and prompt: current",
        "4 Gold dev set: current",
        "5 Tuning loop: STALE: prompt changed",
        "6 Gold test set: STALE: prompt changed",
        "7 Threshold: STALE: prompt changed",
        "8 Full run: STALE: prompt changed",
        "9 Browse: not started",
    ]


def test_status_section_marks_incomplete_and_not_started(tmp_path, monkeypatch):
    complete_project()
    files.write_gold(gold(n_dev=44))
    lines = files.pipeline_status_text().splitlines()
    assert "4 Gold dev set: INCOMPLETE: 44 of 50 rows" in lines
    assert "5 Tuning loop: STALE: gold rows changed" in lines
    (tmp_path / "fresh").mkdir()
    monkeypatch.chdir(tmp_path / "fresh")
    assert files.pipeline_status_text().splitlines()[1:3] == [
        "1 Brief and seeds: not started",
        "2 Search: not started",
    ]


def test_embedding_model_change_is_named_with_both_models():
    complete_project()
    config(embedding_model="e2")
    text = files.pipeline_status_text()
    assert (
        "2 Search: STALE: embedding model changed "
        "(the project now uses e2; the candidates were built with e1)" in text
    )


def test_gold_coverage_section_counts_and_lists_orphans_capped():
    files.write_jsonl(
        "candidates.jsonl",
        [{"id": "in", "text": "t", "max_similarity": 0.7, "best_seed": "x"}],
    )
    long = "x" * 100
    rows = [GoldRow(id="in", text="t", labels=["a"], split="dev")]
    rows += [
        GoldRow(
            id=f"o{i}",
            text=long if i == 0 else f"text {i}",
            labels=["a", "b"],
            split="dev",
        )
        for i in range(12)
    ]
    rows += [GoldRow(id="u", text="un", labels=[], split="test")]
    files.write_gold(rows)
    lines = files.gold_coverage_text().splitlines()
    assert lines[0] == "# Gold coverage"
    assert lines[1] == (
        "dev: 13 rows, 13 labelled, 12 orphaned (no longer in the candidate pool)"
    )
    assert lines[2] == f'- o0 "{"x" * 80}" [a, b]'
    assert lines[3] == '- o1 "text 1" [a, b]'
    assert lines[11] == '- o9 "text 9" [a, b]'
    assert lines[12] == "- ... and 2 more"
    assert (
        lines[13]
        == "test: 1 rows, 0 labelled, 1 orphaned (no longer in the candidate pool)"
    )
    assert lines[14] == '- u "un" [unlabelled]'
    assert len(lines) == 15


def test_gold_coverage_text_for_one_split_has_no_heading_of_the_other():
    files.write_gold([GoldRow(id="a", text="t", labels=["x"], split="test")])
    text = files.gold_coverage_text("test")
    assert "test: 1 rows" in text and "dev:" not in text


def test_assistant_context_is_both_sections():
    complete_project()
    text = files.assistant_context()
    assert text.startswith("# Pipeline status\n")
    assert "\n\n# Gold coverage\n" in text
