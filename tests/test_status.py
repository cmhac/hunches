"""Spec 004 task 04: components, run_digest, stage_status, first_incomplete_stage."""

import hashlib
import json

import pytest

from hunches import candidates, classifier, files
from hunches.files import Config, GoldRow, Label, Taxonomy

SINGLE = Taxonomy(mode="single", labels=[Label(name="a", description="the a")])


def sha(data) -> str:
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def config(classifier_model="m1", embedding_model="e1") -> None:
    files.write_config(
        Config(
            assistant_model="am",
            classifier_model=classifier_model,
            embedding_model=embedding_model,
        )
    )


def gold(n_dev=50, n_test=50, ids_from=0) -> list[GoldRow]:
    return [
        GoldRow(id=f"d{i}", text="t", labels=["a"], split="dev")
        for i in range(ids_from, ids_from + n_dev)
    ] + [
        GoldRow(id=f"t{i}", text="t", labels=["a"], split="test") for i in range(n_test)
    ]


def meta(seeds=("x",), embedding_model="e1") -> str:
    m = {"seeds_digest": candidates.seeds_digest(list(seeds)), "floor": 0.6}
    if embedding_model is not None:
        m["embedding_model"] = embedding_model
    return json.dumps(m)


def complete_project() -> None:
    """Every stage done under the inputs below, approved through files.approve."""
    config()
    files.write_text("seeds.csv", "seed\nx\n")
    files.approve("seeds_approved", 1, "s")
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": "c1", "text": "t", "max_similarity": 0.9, "best_seed": "x"},
            {"id": "c2", "text": "t", "max_similarity": 0.7, "best_seed": "x"},
            {"id": "c3", "text": "t", "max_similarity": 0.62, "best_seed": "x"},
        ],
    )
    files.write_text("candidates.meta.json", meta())
    files.write_taxonomy(SINGLE)
    files.write_text("prompt.md", "p")
    files.approve("taxonomy_approved", 3, "s")
    files.write_gold(gold())
    files.approve("dev_done", 5, "s")
    files.write_text(
        "test_result.json", json.dumps({"inputs": files.current_inputs("test_done")})
    )
    files.approve("test_done", 6, "s")
    files.write_text(
        "threshold.json",
        json.dumps(
            {"threshold": 0.65, "inputs": files.current_inputs("threshold_chosen")}
        ),
    )
    files.approve("threshold_chosen", 7, "s")
    run = files.run_digest("p", SINGLE, "m1")
    files.write_jsonl(
        "results.jsonl",
        [{"id": i, "text": "t", "labels": ["a"], "run": run} for i in ("c1", "c2")],
    )


def status(n: int) -> str:
    return files.stage_status()[n][0]


def reason(n: int) -> str:
    return files.stage_status()[n][1]


def only(**expected: str) -> None:
    """Assert stage statuses given as s1="current"..., the rest unchecked."""
    for key, want in expected.items():
        assert status(int(key[1:])) == want, (key, files.stage_status())


# ---- components


def test_prompt_component_strips_whitespace_and_hashes_text():
    files.write_text("prompt.md", "  p\n\n")
    assert (
        files.current_inputs("dev_done")["prompt"] == hashlib.sha256(b"p").hexdigest()
    )


def test_components_recorded_per_flag():
    complete_project()
    assert set(files.current_inputs("dev_done")) == {
        "prompt",
        "taxonomy",
        "classifier_model",
        "gold_dev",
    }
    assert set(files.current_inputs("test_done")) == {
        "prompt",
        "taxonomy",
        "classifier_model",
        "gold_test",
    }
    assert set(files.current_inputs("threshold_chosen")) == {
        "prompt",
        "taxonomy",
        "classifier_model",
        "candidates",
    }
    assert files.current_inputs("seeds_approved") == {}
    assert files.current_inputs("taxonomy_approved") == {}


def test_component_values_follow_the_spec_formulas():
    complete_project()
    got = files.current_inputs("threshold_chosen")
    assert got["classifier_model"] == "m1"
    assert got["taxonomy"] == sha(["single", [["a", "the a"]]])
    assert got["candidates"] == sha(["c1", "c2", "c3"])
    dev = files.current_inputs("dev_done")["gold_dev"]
    assert dev == sha(sorted([f"d{i}", ["a"]] for i in range(50)))
    assert files.current_inputs("test_done")["gold_test"] == sha(
        sorted([f"t{i}", ["a"]] for i in range(50))
    )


def test_gold_component_counts_only_labelled_rows_and_ignores_order():
    complete_project()
    before = files.current_inputs("dev_done")["gold_dev"]
    rows = gold()
    files.write_gold(
        [*reversed(rows), GoldRow(id="u", text="t", labels=[], split="dev")]
    )
    assert files.current_inputs("dev_done")["gold_dev"] == before
    rows[0].labels = ["off_topic"]
    files.write_gold(rows)
    assert files.current_inputs("dev_done")["gold_dev"] != before


def test_embedding_model_component_is_the_plain_name():
    config(embedding_model="emb-x")
    assert files.components()["embedding_model"] == "emb-x"


def test_components_do_not_need_config_or_files():
    # old projects and tests without config.toml must not crash
    assert files.current_inputs("dev_done")["classifier_model"] == ""


# ---- run_digest


def test_run_digest_is_the_hash_the_classifier_cache_uses():
    expected = hashlib.sha256(
        json.dumps(["m1", classifier.system_prompt("p", SINGLE)]).encode()
    ).hexdigest()
    assert files.run_digest("p", SINGLE, "m1") == expected


def test_run_digest_changes_with_prompt_taxonomy_and_model_but_not_whitespace():
    base = files.run_digest("p", SINGLE, "m1")
    assert files.run_digest(" p\n", SINGLE, "m1") == base
    assert files.run_digest("q", SINGLE, "m1") != base
    assert files.run_digest("p", SINGLE, "m2") != base
    other = Taxonomy(mode="multi", labels=SINGLE.labels)
    assert files.run_digest("p", other, "m1") != base


def test_current_run_reads_the_project_and_is_none_without_one():
    assert files.current_run() is None
    complete_project()
    assert files.current_run() == files.run_digest("p", SINGLE, "m1")


def test_result_changes_for_new_legacy_and_bare_results():
    complete_project()
    inputs = files.current_inputs("test_done")
    assert files.result_changes({"inputs": inputs}) == []
    assert files.result_changes(
        {"inputs": inputs | {"gold_test": "x", "prompt": "y"}}
    ) == [
        "prompt",
        "gold_test",
    ]
    legacy = hashlib.sha256(json.dumps(["p", "m1"]).encode()).hexdigest()
    assert files.result_changes({"prompt_hash": legacy}) == []
    assert files.result_changes({"prompt_hash": "other"}) == ["prompt"]
    assert files.result_changes({}) == []  # nothing recorded counts as current


# ---- statuses


def test_new_project_is_all_not_started_and_resumes_at_1():
    assert files.stage_status() == {n: ("not_started", "") for n in range(1, 10)}
    assert files.first_incomplete_stage() == 1


def test_complete_project_is_all_current_and_resumes_at_9():
    complete_project()
    assert files.stage_status() == {n: ("current", "") for n in range(1, 10)}
    assert files.first_incomplete_stage() == 9


def test_project_with_no_recorded_inputs_is_all_current():
    complete_project()
    state = files.read_state()
    state.inputs = {}
    files.write_state(state)
    files.write_text("test_result.json", "{}")
    files.write_text("threshold.json", json.dumps({"threshold": 0.65}))
    files.write_text("candidates.meta.json", meta(embedding_model=None))
    files.write_jsonl(
        "results.jsonl", [{"id": "c1", "labels": ["a"]}, {"id": "c2", "labels": ["a"]}]
    )
    assert files.stage_status() == {n: ("current", "") for n in range(1, 10)}


def test_prompt_change_marks_5_to_8_stale_and_leaves_1_to_4_current():
    complete_project()
    files.write_text("prompt.md", "changed")
    only(s1="current", s2="current", s3="current", s4="current")
    for n in (5, 6, 7, 8):
        assert files.stage_status()[n] == ("stale", "prompt changed"), n
    assert files.first_incomplete_stage() == 5


def test_restoring_the_old_prompt_makes_everything_current_again():
    complete_project()
    files.write_text("prompt.md", "changed")
    files.write_text("prompt.md", "p")
    assert files.stage_status() == {n: ("current", "") for n in range(1, 10)}


def test_seeds_change_marks_2_stale_then_after_rerun_7_candidates_changed():
    complete_project()
    files.write_text("seeds.csv", "seed\nx\ny\n")
    assert files.stage_status()[2] == ("stale", "seeds changed")
    assert files.first_incomplete_stage() == 2
    only(s1="current", s3="current", s5="current", s6="current", s7="current")
    # the re-run: new candidates and a meta file for the new seeds
    files.write_jsonl(
        "candidates.jsonl",
        [{"id": "n1", "text": "t", "max_similarity": 0.9, "best_seed": "y"}],
    )
    files.write_text("candidates.meta.json", meta(seeds=("x", "y")))
    assert status(2) == "current"
    assert files.stage_status()[7] == ("stale", "candidates changed")


def test_embedding_model_change_alone_marks_2_stale():
    complete_project()
    config(embedding_model="e2")
    assert files.stage_status()[2] == ("stale", "embedding model changed")
    assert status(7) == "current"  # the candidate ids did not change


def test_meta_without_embedding_model_is_current():
    complete_project()
    files.write_text("candidates.meta.json", meta(embedding_model=None))
    config(embedding_model="anything")
    assert status(2) == "current"


def test_classifier_model_and_taxonomy_changes_have_their_reasons():
    complete_project()
    config(classifier_model="m2")
    assert files.stage_status()[5] == ("stale", "classifier model changed")
    config()
    files.write_taxonomy(
        Taxonomy(mode="single", labels=[Label(name="a", description="the a!")])
    )
    assert files.stage_status()[5] == ("stale", "taxonomy changed")


def test_removing_dev_rows_makes_4_incomplete_and_5_stale():
    complete_project()
    files.write_gold(gold(n_dev=44))
    assert files.stage_status()[4] == ("incomplete", "44 of 50 rows")
    assert files.stage_status()[5] == ("stale", "gold rows changed")
    assert files.first_incomplete_stage() == 4


def test_removing_test_rows_makes_6_incomplete_with_count():
    complete_project()
    files.write_gold(gold(n_test=45))
    assert files.stage_status()[6] == ("incomplete", "45 of 50 rows")
    assert files.first_incomplete_stage() == 6


def test_replacing_test_rows_marks_6_stale_gold_rows_changed():
    complete_project()
    rows = gold()
    rows[-1].labels = ["off_topic"]
    files.write_gold(rows)
    assert files.stage_status()[6] == ("stale", "gold rows changed")


def test_unapproved_flag_after_data_exists_is_not_started_not_incomplete():
    complete_project()
    state = files.read_state()
    state.dev_done = state.test_done = state.threshold_chosen = False
    files.write_state(state)
    (files.root() / "results.jsonl").unlink()
    only(s4="current", s5="not_started", s6="not_started", s7="not_started")
    assert files.first_incomplete_stage() == 5


def test_incomplete_when_a_later_stage_is_done():
    complete_project()
    state = files.read_state()
    state.seeds_approved = False
    files.write_state(state)
    assert files.stage_status()[1] == ("incomplete", "not approved")


def test_candidates_missing_after_later_work_is_incomplete():
    complete_project()
    (files.root() / "candidates.jsonl").unlink()
    assert files.stage_status()[2] == ("incomplete", "no candidates")


def test_stale_stage_6_from_result_inputs_even_if_flag_inputs_match():
    complete_project()
    files.write_text(
        "test_result.json",
        json.dumps({"inputs": {**files.current_inputs("test_done"), "prompt": "old"}}),
    )
    assert files.stage_status()[6] == ("stale", "prompt changed")


def test_legacy_prompt_hash_in_test_result_is_compared_the_old_way():
    complete_project()
    legacy = hashlib.sha256(json.dumps(["p", "m1"]).encode()).hexdigest()
    files.write_text("test_result.json", json.dumps({"prompt_hash": legacy}))
    state = files.read_state()
    state.inputs.pop("test_done")
    files.write_state(state)
    assert status(6) == "current"
    files.write_text("prompt.md", "q")
    assert files.stage_status()[6] == ("stale", "prompt changed")


def test_stage_8_stale_rows_use_stage_7_reason_or_fallback():
    complete_project()
    # rows made under another run, stage 7's recorded inputs still match
    files.write_jsonl(
        "results.jsonl",
        [{"id": i, "labels": ["a"], "run": "old"} for i in ("c1", "c2")],
    )
    assert files.stage_status()[8] == ("stale", "classifier input changed")
    assert files.first_incomplete_stage() == 8
    files.write_text("prompt.md", "changed")
    assert files.stage_status()[7] == ("stale", "prompt changed")
    assert files.stage_status()[8] == ("stale", "prompt changed")


def test_partial_run_with_current_rows_is_not_stale_and_stage_8_resumes():
    complete_project()
    run = files.current_run()
    files.write_jsonl("results.jsonl", [{"id": "c1", "labels": ["a"], "run": run}])
    assert status(8) == "not_started"
    assert files.first_incomplete_stage() == 8


def test_error_rows_do_not_count_as_done():
    complete_project()
    run = files.current_run()
    files.write_jsonl(
        "results.jsonl",
        [
            {"id": "c1", "labels": ["a"], "run": run},
            {"id": "c2", "labels": [], "error": "boom"},
        ],
    )
    assert files.first_incomplete_stage() == 8


def test_row_without_run_counts_as_current_but_other_run_is_not_done():
    complete_project()
    files.write_jsonl(
        "results.jsonl",
        [{"id": "c1", "labels": ["a"]}, {"id": "c2", "labels": ["a"], "run": "old"}],
    )
    assert files.first_incomplete_stage() == 8


def test_every_reason_is_at_most_24_characters():
    for text in files.REASONS.values():
        assert len(text) <= 24, text
    complete_project()
    config(classifier_model="m2", embedding_model="e2")
    files.write_text("seeds.csv", "seed\nz\n")
    files.write_text("prompt.md", "zzz")
    files.write_gold(gold(n_dev=1, n_test=1))
    for _, why in files.stage_status().values():
        assert len(why) <= 24, why


def test_stage_9_follows_stage_8():
    complete_project()
    files.write_text("prompt.md", "changed")
    assert status(9) == "not_started"


# ---- performance: big files are parsed once per change


def test_stage_status_does_not_reread_unchanged_big_files(monkeypatch):
    complete_project()
    files.stage_status()
    reads = []
    real = files.read_jsonl

    def counting(name):
        reads.append(name)
        return real(name)

    monkeypatch.setattr(files, "read_jsonl", counting)
    files.stage_status()
    files.stage_status()
    assert reads == []
    files.write_jsonl("results.jsonl", [])  # a write through files invalidates
    files.stage_status()
    assert reads == ["results.jsonl"]
    files.append_jsonl("candidates.jsonl", {"id": "c9", "max_similarity": 0.8})
    files.stage_status()
    assert reads == ["results.jsonl", "candidates.jsonl"]


def test_change_behind_the_apps_back_is_seen_by_the_cache():
    complete_project()
    assert status(7) == "current"
    path = files.root() / "candidates.jsonl"
    path.write_text(
        path.read_text() + json.dumps({"id": "zz", "max_similarity": 0.8}) + "\n"
    )
    assert files.stage_status()[7] == ("stale", "candidates changed")
