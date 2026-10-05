import json

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from hunches import files
from hunches.files import (
    Config,
    GoldRow,
    Label,
    State,
    Taxonomy,
    all_labels,
    validate_labels,
)


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_root_and_ensure_root(tmp_path):
    assert files.root() == files.Path(".hunches")
    files.ensure_root()
    files.ensure_root()
    assert (tmp_path / ".hunches").is_dir()


def test_config_round_trip():
    config = Config(
        backend="s3",
        s3_bucket="b",
        s3_index='i"x',
        embedding_model="openai:text-embedding-3-small",
        assistant_model="openai:gpt-5",
        assistant_thinking="medium",
        classifier_model="openai:gpt-5-mini",
        s3_region="eu-west-1",
        target_metric="macro_f1",
        target_score=0.85,
    )
    files.ensure_root()
    files.write_config(config)
    assert files.read_config() == config
    assert config.classifier_model == "openai:gpt-5-mini"
    assert Config(assistant_model="a", classifier_model="c").target_score == 0.90


def test_old_model_keys_load_and_are_not_written_back():
    files.write_text(
        "config.toml",
        'corpus_dir = "c"\nembedding_model = "m"\n'
        'smart_model = "anthropic:big"\ncheap_model = "anthropic:small"\n',
    )
    config = files.read_config()
    assert config.assistant_model == "anthropic:big"
    assert config.classifier_model == "anthropic:small"
    assert config.assistant_thinking is None  # old projects get no thinking
    files.write_config(config)
    text = (files.root() / "config.toml").read_text()
    assert 'assistant_model = "anthropic:big"' in text
    assert "smart_model" not in text and "cheap_model" not in text
    assert "assistant_thinking" not in text and "s3_region" not in text


def test_new_key_wins_over_old_key():
    files.write_text(
        "config.toml",
        'embedding_model = "m"\nclassifier_model = "c"\nsmart_model = "old"\n'
        'assistant_model = "new"\n',
    )
    assert files.read_config().assistant_model == "new"


def test_thinking_settings_only_when_set():
    assert (
        files.thinking_settings(Config(assistant_model="a", classifier_model="c"))
        is None
    )
    assert files.thinking_settings(
        Config(assistant_model="a", classifier_model="c", assistant_thinking="medium")
    ) == {"thinking": "medium"}


def test_state_round_trip():
    assert files.read_state() == State()
    state = State(seeds_approved=True, test_done=True)
    files.write_state(state)
    assert files.read_state() == state


def test_jsonl_write_append_read():
    assert files.read_jsonl("x.jsonl") == []
    files.write_jsonl("x.jsonl", [{"id": "a", "text": "héllo"}])
    files.append_jsonl("x.jsonl", {"id": "b", "text": "w"})
    assert files.read_jsonl("x.jsonl") == [
        {"id": "a", "text": "héllo"},
        {"id": "b", "text": "w"},
    ]


def test_append_jsonl_flushes_each_line():
    files.append_jsonl("x.jsonl", {"id": "a"})
    assert (files.root() / "x.jsonl").read_text() == '{"id": "a"}\n'


def test_text_files_round_trip():
    assert files.read_text("brief.md") is None
    for name in ("seeds.csv", "brief.md", "prompt.md"):
        files.write_text(name, f"content of {name}\n")
        assert files.read_text(name) == f"content of {name}\n"


def test_taxonomy_round_trip_and_all_labels():
    tax = Taxonomy(
        mode="multi", labels=[Label(name="a", description="A: thing"), Label(name="b")]
    )
    files.write_text("placeholder", "")
    files.write_taxonomy(tax)
    assert files.read_taxonomy() == tax
    assert all_labels(tax) == ["a", "b", "off_topic"]


def test_taxonomy_rejects_off_topic():
    with pytest.raises(ValidationError):
        Taxonomy(mode="single", labels=[Label(name="off_topic")])


def test_gold_round_trip():
    rows = [
        GoldRow(id="1", text="t", labels=["a"], split="dev"),
        GoldRow(id="2", text="u", labels=["a", "b"], split="test"),
    ]
    files.write_gold(rows)
    assert files.read_gold() == rows


def test_chat_round_trip():
    assert files.load_chat("brief") == []
    messages = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[TextPart(content="hello")]),
    ]
    files.save_chat("brief", messages)
    assert (files.root() / "chat" / "brief.json").exists()
    assert files.load_chat("brief") == messages


SINGLE = Taxonomy(mode="single", labels=[Label(name="a"), Label(name="b")])
MULTI = Taxonomy(mode="multi", labels=[Label(name="a"), Label(name="b")])


@pytest.mark.parametrize("tax", [SINGLE, MULTI])
def test_validate_labels_rules_both_modes(tax):
    validate_labels(["a"], tax)
    validate_labels(["off_topic"], tax)
    with pytest.raises(ValueError, match="at least one"):
        validate_labels([], tax)
    with pytest.raises(ValueError, match="unknown"):
        validate_labels(["zzz"], tax)
    with pytest.raises(ValueError, match="only label"):
        validate_labels(["a", "off_topic"], tax)


def test_validate_labels_mode_specific():
    with pytest.raises(ValueError, match="exactly one"):
        validate_labels(["a", "b"], SINGLE)
    validate_labels(["a", "b"], MULTI)


def test_first_incomplete_stage_all_nine():
    files.ensure_root()
    assert files.first_incomplete_stage() == 1

    files.write_text("seeds.csv", "seed\nx\n")
    assert files.first_incomplete_stage() == 1  # not approved
    state = State(seeds_approved=True)
    files.write_state(state)
    assert files.first_incomplete_stage() == 2

    cands = [
        {"id": "1", "text": "t", "max_similarity": 0.9, "best_seed": "x"},
        {"id": "2", "text": "t", "max_similarity": 0.7, "best_seed": "x"},
    ]
    files.write_jsonl("candidates.jsonl", cands)
    assert files.first_incomplete_stage() == 3
    files.write_taxonomy(SINGLE)
    files.write_text("prompt.md", "p")
    state.taxonomy_approved = True
    files.write_state(state)
    assert files.first_incomplete_stage() == 4

    gold = [GoldRow(id=str(i), text="t", labels=["a"], split="dev") for i in range(50)]
    files.write_gold(gold)
    assert files.first_incomplete_stage() == 5
    state.dev_done = True
    files.write_state(state)
    assert files.first_incomplete_stage() == 6

    gold += [
        GoldRow(id=f"t{i}", text="t", labels=["a"], split="test") for i in range(50)
    ]
    files.write_gold(gold)
    assert files.first_incomplete_stage() == 6  # test not accepted
    state.test_done = True
    files.write_state(state)
    assert files.first_incomplete_stage() == 7

    files.write_text("threshold.json", json.dumps({"threshold": 0.65}))
    state.threshold_chosen = True
    files.write_state(state)
    assert files.first_incomplete_stage() == 8
    files.append_jsonl("results.jsonl", {"id": "1"})
    assert files.first_incomplete_stage() == 8  # id 2 still missing
    files.append_jsonl("results.jsonl", {"id": "2", "error": "boom"})
    assert files.first_incomplete_stage() == 8  # error rows are retried, not done
    files.append_jsonl("results.jsonl", {"id": "2"})
    assert files.first_incomplete_stage() == 9


def test_first_incomplete_stage_stage8_ignores_below_threshold():
    files.write_text("seeds.csv", "s")
    files.write_state(
        State(
            seeds_approved=True,
            taxonomy_approved=True,
            dev_done=True,
            test_done=True,
            threshold_chosen=True,
        )
    )
    files.write_jsonl(
        "candidates.jsonl", [{"id": "1", "text": "t", "max_similarity": 0.62}]
    )
    files.write_taxonomy(SINGLE)
    files.write_text("prompt.md", "p")
    files.write_gold(
        [
            GoldRow(id=str(i), text="t", labels=["a"], split=s)
            for i in range(50)
            for s in ("dev", "test")
        ]
    )
    files.write_text("threshold.json", json.dumps({"threshold": 0.7}))
    assert files.first_incomplete_stage() == 9


def test_first_incomplete_stage_unlabelled_gold_rows_do_not_count():
    files.write_text("seeds.csv", "s")
    files.write_state(State(seeds_approved=True, taxonomy_approved=True))
    files.write_jsonl(
        "candidates.jsonl", [{"id": "1", "text": "t", "max_similarity": 0.62}]
    )
    files.write_taxonomy(SINGLE)
    files.write_text("prompt.md", "p")
    files.write_gold(
        [GoldRow(id=str(i), text="t", labels=[], split="dev") for i in range(50)]
    )
    assert files.first_incomplete_stage() == 4


def test_models_have_no_default_so_system_settings_is_the_only_source():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Config()  # ty: ignore[missing-argument]
