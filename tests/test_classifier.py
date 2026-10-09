import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RequestUsage

from hunches import cost
from hunches.classifier import classify, classify_many, is_cached, system_prompt
from hunches.files import Label, Taxonomy


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def taxonomy(mode="multi"):
    return Taxonomy(mode=mode, labels=[Label(name="a"), Label(name="b")])


def out(labels, reasoning="because"):
    return {"reasoning": reasoning, "labels": labels}


def scripted(*outputs):
    """FunctionModel that answers each request with the next scripted label list."""
    calls = []

    def fn(messages, info: AgentInfo):
        calls.append(messages)
        tool = info.output_tools[0]
        return ModelResponse(
            parts=[ToolCallPart(tool.name, out(outputs[len(calls) - 1]))]
        )

    return FunctionModel(fn), calls


async def test_valid_output():
    model, _ = scripted(["a", "b"])
    p = await classify("text", "prompt", taxonomy(), model)
    assert p.labels == ["a", "b"] and p.error is None and not p.cached


async def test_off_topic_with_other_label_is_retried():
    model, calls = scripted(["a", "off_topic"], ["off_topic"])
    p = await classify("text", "prompt", taxonomy(), model)
    assert p.labels == ["off_topic"]
    assert len(calls) == 2


async def test_single_mode_two_labels_rejected_and_retried():
    model, calls = scripted(["a", "b"], ["b"])
    p = await classify("text", "prompt", taxonomy("single"), model)
    assert p.labels == ["b"]
    assert len(calls) == 2


async def test_unknown_label_is_retried():
    model, calls = scripted(["zzz"], ["a"])
    p = await classify("text", "prompt", taxonomy(), model)
    assert p.labels == ["a"] and len(calls) == 2


async def test_gives_up_with_recorded_error_not_crash():
    model = FunctionModel(
        lambda m, info: ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, out([]))]
        )
    )
    p = await classify("text", "prompt", taxonomy(), model)
    assert p.labels is None and p.error
    assert not list((cost.root() / "cache").glob("*.json"))


async def test_second_identical_call_is_cache_hit_with_no_added_cost():
    model, calls = scripted(["a"])
    first = await classify("text", "prompt", taxonomy(), model)
    snapshot = (cost.breakdown(), cost.items_per_second())
    second = await classify("text", "prompt", taxonomy(), model)
    assert second.labels == first.labels == ["a"]
    assert second.cached and not first.cached
    assert len(calls) == 1
    assert (cost.breakdown(), cost.items_per_second()) == snapshot
    assert next(iter(cost.breakdown().values()))["calls"] == 1


async def test_prompt_change_misses_cache():
    model, _ = scripted(["a"], ["b"])
    await classify("text", "prompt one", taxonomy(), model)
    p = await classify("text", "prompt two", taxonomy(), model)
    assert p.labels == ["b"] and not p.cached


async def test_classifier_model_change_misses_cache():
    def named(name, label):
        calls = []

        def fn(messages, info: AgentInfo):
            calls.append(1)
            part = ToolCallPart(info.output_tools[0].name, out([label]))
            return ModelResponse(parts=[part])

        return FunctionModel(fn, model_name=name), calls

    old, old_calls = named("old-model", "a")
    new, new_calls = named("new-model", "b")
    await classify("text", "prompt", taxonomy(), old)
    p = await classify("text", "prompt", taxonomy(), new)
    assert p.labels == ["b"] and not p.cached  # never the old model's cached answer
    assert len(old_calls) == 1 and len(new_calls) == 1


async def test_classify_many_yields_all_and_records_one_timing():
    model = TestModel(custom_output_args=out(["a"]))
    texts = ["t0", "t1", "t2", "t3"]
    got = {
        i: p
        async for i, p in classify_many(
            texts, "prompt", taxonomy(), model, concurrency=2
        )
    }
    assert sorted(got) == [0, 1, 2, 3]
    assert all(p.labels == ["a"] for p in got.values())
    assert cost.items_per_second("classify") is not None
    # second pass is all cache hits: no further timing rows
    rows = len(cost._read()["timings"])
    again = [i async for i, _ in classify_many(texts, "prompt", taxonomy(), model)]
    assert sorted(again) == [0, 1, 2, 3]
    assert len(cost._read()["timings"]) == rows


async def test_reasoning_returned_live_and_on_cache_hit():
    calls = []

    def fn(messages, info: AgentInfo):
        calls.append(1)
        part = ToolCallPart(info.output_tools[0].name, out(["a"], "quotes the word a"))
        return ModelResponse(parts=[part])

    model = FunctionModel(fn)
    first = await classify("text", "prompt", taxonomy(), model)
    second = await classify("text", "prompt", taxonomy(), model)
    assert first.reasoning == second.reasoning == "quotes the word a"
    assert second.cached and not first.cached
    assert len(calls) == 1


async def test_old_shape_cache_entry_is_a_miss_and_replaced():
    tax = taxonomy()
    model, calls = scripted(["a"])
    key = cost.cache_key(model.model_name, system_prompt("prompt", tax), "text")
    usage = RequestUsage(input_tokens=1, output_tokens=1)
    cost.cache_put(key, ["b"], usage)
    p = await classify("text", "prompt", tax, model)
    assert p.labels == ["a"] and not p.cached and len(calls) == 1
    hit = cost.cache_get(key)
    assert hit is not None
    assert hit["output"] == {"labels": ["a"], "reasoning": "because"}


async def test_failed_call_has_no_reasoning():
    model = FunctionModel(
        lambda m, info: ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, out([]))]
        )
    )
    p = await classify("text", "prompt", taxonomy(), model)
    assert p.error and p.reasoning is None


def test_system_prompt_asks_for_reasoning_first():
    assert (
        "First give a short reasoning (one to three sentences) that names the "
        "evidence in the text, then the labels."
    ) in system_prompt("prompt", taxonomy())


async def test_is_cached_follows_classify_and_calls_nothing():
    tax = taxonomy()
    model, calls = scripted(["a"])
    assert not is_cached("t", "p", tax, "fn")
    await classify("t", "p", tax, model)
    assert is_cached("t", "p", tax, model.model_name)
    assert len(calls) == 1  # is_cached made no call
    # a different text, prompt, taxonomy or model is a different key
    assert not is_cached("other", "p", tax, model.model_name)
    assert not is_cached("t", "p2", tax, model.model_name)
    assert not is_cached("t", "p", taxonomy("single"), model.model_name)
    assert not is_cached("t", "p", tax, "another-model")


def test_is_cached_old_list_shape_is_a_miss():
    tax = taxonomy()
    cost.cache_put(
        cost.cache_key("m", system_prompt("p", tax), "t"),
        ["a"],
        RequestUsage(input_tokens=1, output_tokens=1),
    )
    assert not is_cached("t", "p", tax, "m")
