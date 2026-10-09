"""Spec 004 task 05: classifier.redo_plan counts what a real run then does."""

import json

import pytest
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage, RunUsage

from hunches import candidates, classifier, cost, files
from hunches.files import Config, GoldRow, Label, Taxonomy

SINGLE = Taxonomy(mode="single", labels=[Label(name="a", description="the a")])
N = 3  # gold rows per split in these tests


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(files, "SAMPLE_SIZE", N)


def counting_model():
    calls: list[str] = []

    def fn(messages, info: AgentInfo):
        calls.append(messages[-1].parts[-1].content)  # the item text
        out = {"reasoning": "r", "labels": ["a"]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])

    return FunctionModel(fn, model_name="m1"), calls


class CountingEmbedder(Embedder):
    def __init__(self):
        super().__init__(TestEmbeddingModel("e1"))
        self.calls: list[str] = []

    async def embed_query(self, query, *, settings=None):
        self.calls.append(query)
        return EmbeddingResult(
            [[1.0, 0.0]],
            inputs=[query],
            input_type="query",
            model_name="e1",
            provider_name="test",
            usage=RequestUsage(input_tokens=3),
        )


def complete_project(sample_text="s") -> None:
    """Every stage done and approved under prompt "p". Texts differ per stage unless asked."""
    files.write_config(
        Config(assistant_model="am", classifier_model="m1", embedding_model="e1")
    )
    files.write_text("seeds.csv", "seed\nx\n")
    files.approve("seeds_approved", 1, "s")
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": "c1", "text": "run1", "max_similarity": 0.9, "best_seed": "x"},
            {"id": "c2", "text": "run2", "max_similarity": 0.7, "best_seed": "x"},
            {"id": "c3", "text": sample_text, "max_similarity": 0.62, "best_seed": "x"},
            {"id": "c4", "text": "samp2", "max_similarity": 0.61, "best_seed": "x"},
        ],
    )
    files.write_text(
        "candidates.meta.json",
        json.dumps(
            {
                "seeds_digest": candidates.seeds_digest(["x"]),
                "embedding_model": "e1",
            }
        ),
    )
    files.write_taxonomy(SINGLE)
    files.write_text("prompt.md", "p")
    files.approve("taxonomy_approved", 3, "s")
    files.write_gold(
        [
            GoldRow(id=f"d{i}", text=f"dev{i}", labels=["a"], split="dev")
            for i in range(N)
        ]
        + [
            GoldRow(id=f"t{i}", text=f"test{i}", labels=["a"], split="test")
            for i in range(N)
        ]
    )
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
    files.write_text(
        "threshold_sample.json",
        json.dumps(
            {
                "ids": [["c3", "c4"]],
                "predictions": {},
                "inputs": files.current_inputs("threshold_chosen"),
            }
        ),
    )
    files.approve("threshold_chosen", 7, "s")
    run = files.run_digest("p", SINGLE, "m1")
    files.write_jsonl(
        "results.jsonl",
        [{"id": i, "text": "t", "labels": ["a"], "run": run} for i in ("c1", "c2")],
    )


def by_stage() -> dict[int, dict]:
    return {row["stage"]: row for row in classifier.redo_plan()}


async def real_run(stage: int, model) -> None:
    """What the stage's screen sends to the classifier, in the screen's own terms."""
    prompt = files.read_text("prompt.md") or ""
    if stage == 5:
        texts = [r.text for r in files.read_gold() if r.split == "dev" and r.labels]
    elif stage == 6:
        texts = [r.text for r in files.read_gold() if r.split == "test" and r.labels]
    elif stage == 7:
        sample = json.loads(files.read_text("threshold_sample.json") or "{}")["ids"]
        by_id = {c["id"]: c["text"] for c in files.read_jsonl("candidates.jsonl")}
        texts = [by_id[i] for band in sample for i in band]
    else:
        texts = [c["text"] for c in files.pending()]
    async for _ in classifier.classify_many(texts, prompt, SINGLE, model):
        pass


def test_new_project_plan_is_empty():
    assert classifier.redo_plan() == []


def test_current_project_plan_is_empty():
    complete_project()
    assert classifier.redo_plan() == []


def test_plan_lists_stale_and_incomplete_stages_in_order():
    complete_project()
    files.write_text("prompt.md", "changed")
    files.write_gold(files.read_gold()[1:])  # one dev row removed: 4 incomplete
    plan = classifier.redo_plan()
    assert [(r["stage"], r["status"], r["reason"]) for r in plan] == [
        (4, "incomplete", "2 of 3 rows"),
        (5, "stale", "prompt changed"),  # most upstream reason first
        (6, "stale", "prompt changed"),
        (7, "stale", "prompt changed"),
        (8, "stale", "prompt changed"),
    ]
    # stages that make no model calls have no counts
    assert plan[0]["live_calls"] is None and plan[0]["cached_calls"] is None
    assert plan[0]["price_unknown"] is False
    assert all(isinstance(r["live_calls"], int) for r in plan[1:])
    assert [r["stage"] for r in classifier.redo_plan(from_stage=7)] == [7, 8]


async def test_plan_equals_a_real_run_and_a_second_run_makes_no_calls():
    complete_project()
    files.write_text("prompt.md", "changed")
    model, calls = counting_model()
    # warm the cache under the new prompt: one dev row and one candidate
    await classifier.classify("dev0", "changed", SINGLE, model)
    await classifier.classify("run2", "changed", SINGLE, model)
    calls.clear()
    plan = by_stage()
    assert {n: (r["live_calls"], r["cached_calls"]) for n, r in plan.items()} == {
        5: (2, 1),
        6: (3, 0),
        7: (2, 0),
        8: (1, 1),
    }
    for stage, row in plan.items():
        before = len(calls)
        await real_run(stage, model)
        assert len(calls) - before == row["live_calls"], stage
    # redoing changed nothing in the inputs, so everything is now cached
    calls.clear()
    assert {n: (r["live_calls"], r["cached_calls"]) for n, r in by_stage().items()} == {
        5: (0, 3),
        6: (0, 3),
        7: (0, 2),
        8: (0, 2),
    }
    for stage in plan:
        await real_run(stage, model)
    assert calls == []


async def test_a_later_stage_counts_what_an_earlier_one_will_have_cached():
    complete_project(
        sample_text="run1"
    )  # the sample's c3 has the same text as candidate c1
    files.write_text("prompt.md", "changed")
    model, calls = counting_model()
    plan = by_stage()
    assert (plan[7]["live_calls"], plan[7]["cached_calls"]) == (2, 0)
    assert (plan[8]["live_calls"], plan[8]["cached_calls"]) == (1, 1)
    await real_run(7, model)
    assert len(calls) == 2
    calls.clear()
    await real_run(8, model)
    assert len(calls) == 1


async def test_search_stage_counts_one_embedding_per_seed():
    complete_project()
    files.write_text("seeds.csv", "seed\nx\ny\nz\n")
    cost.cache_put(
        cost.cache_key("e1", "embed_query", "x"),
        [1.0, 0.0],
        RequestUsage(input_tokens=3),
    )
    row = by_stage()[2]
    assert (row["status"], row["reason"]) == ("stale", "seeds changed")
    assert (row["live_calls"], row["cached_calls"]) == (2, 1)
    embedder = CountingEmbedder()
    await candidates.embed_seeds(candidates.read_seeds(), embedder)
    assert len(embedder.calls) == 2


def test_embedding_model_change_is_all_live():
    complete_project()
    files.write_config(
        Config(assistant_model="am", classifier_model="m1", embedding_model="e2")
    )
    row = by_stage()[2]
    assert row["reason"] == "embedding model changed"
    assert (row["live_calls"], row["cached_calls"]) == (1, 0)


def test_dollars_use_the_average_recorded_call():
    complete_project()
    files.write_text("prompt.md", "changed")
    cost.record("m1", RunUsage(input_tokens=1, output_tokens=1), 0.5)
    cost.record("m1", RunUsage(input_tokens=1, output_tokens=1), 1.5)
    plan = by_stage()
    assert plan[5]["dollars"] == 3.0  # 3 live calls at an average of $1
    assert plan[5]["price_unknown"] is False
    assert plan[8]["dollars"] == 2.0  # 2 live calls


def test_unknown_price_is_never_zero():
    complete_project()
    files.write_text("prompt.md", "changed")
    cost.record("m1", RunUsage(input_tokens=1, output_tokens=1), None)
    row = by_stage()[5]
    assert row["dollars"] is None and row["price_unknown"] is True


def test_no_sample_usage_is_unknown_not_zero():
    complete_project()
    files.write_text("prompt.md", "changed")
    row = by_stage()[5]
    assert row["dollars"] is None and row["price_unknown"] is True


async def test_nothing_live_costs_zero_even_if_the_price_is_unknown():
    complete_project()
    files.write_text("prompt.md", "changed")
    cost.record("m1", RunUsage(input_tokens=1, output_tokens=1), None)
    model, _ = counting_model()
    await real_run(5, model)
    row = by_stage()[5]
    assert (row["live_calls"], row["dollars"], row["price_unknown"]) == (0, 0.0, False)
