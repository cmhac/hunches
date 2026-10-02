import json

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RequestUsage

from hunches import cost


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_cache_key_changes_with_each_part():
    base = cost.cache_key("m", "p", "t")
    assert base == cost.cache_key("m", "p", "t")
    assert (
        len({base, cost.cache_key("m2", "p", "t"), cost.cache_key("m", "p2", "t")}) == 3
    )
    assert base != cost.cache_key("m", "p", "t2")
    assert cost.cache_key("ab", "c", "") != cost.cache_key("a", "bc", "")


def test_cache_round_trip_and_hit_changes_no_totals():
    key = cost.cache_key("m", "p", "t")
    assert cost.cache_get(key) is None
    usage = RequestUsage(input_tokens=10, output_tokens=2)
    cost.record("m", usage, 0.5)
    cost.cache_put(key, ["a"], usage)
    before = (cost.total(), json.loads((cost.root() / "cost.json").read_text()))
    hit = cost.cache_get(key)
    assert hit == {"output": ["a"], "usage": {"input_tokens": 10, "output_tokens": 2}}
    after = (cost.total(), json.loads((cost.root() / "cost.json").read_text()))
    assert before == after


def test_record_known_price_and_persistence():
    cost.record("m", RequestUsage(input_tokens=100, output_tokens=10), 0.25)
    cost.record("m", RequestUsage(input_tokens=50, output_tokens=5), 0.25)
    assert cost.total() == (0.5, False)
    # a fresh read from disk sees the same data
    assert cost.breakdown()["m"] == {
        "input_tokens": 150,
        "output_tokens": 15,
        "calls": 2,
        "dollars": 0.5,
    }


def test_unknown_price_is_null_and_flagged():
    cost.record("known", RequestUsage(input_tokens=1, output_tokens=1), 1.0)
    cost.record("mystery", RequestUsage(input_tokens=1, output_tokens=1), None)
    cost.record("mystery", RequestUsage(input_tokens=1, output_tokens=1), 2.0)
    assert cost.breakdown()["mystery"]["dollars"] is None
    assert (
        json.loads((cost.root() / "cost.json").read_text())["models"]["mystery"][
            "dollars"
        ]
        is None
    )
    assert cost.total() == (1.0, True)


def test_testmodel_price_is_unknown():
    result = Agent(TestModel()).run_sync("hi")
    dollars = cost.messages_dollars(result.new_messages())
    assert dollars is None
    cost.record("test", result.usage, dollars)
    assert cost.total() == (0.0, True)
    assert cost.breakdown()["test"]["input_tokens"] > 0


def test_known_price_from_genai_prices():
    # claude-haiku-4-5 is known to genai-prices; assert only that it is a positive number
    from pydantic_ai.messages import ModelResponse, TextPart

    response = ModelResponse(
        parts=[TextPart("x")],
        usage=RequestUsage(input_tokens=1000, output_tokens=100),
        model_name="claude-haiku-4-5",
        provider_name="anthropic",
    )
    dollars = cost.messages_dollars([response])
    assert dollars is not None and dollars > 0


def test_timing():
    assert cost.items_per_second() is None
    cost.record_timing("dev", 10, 2.0)
    cost.record_timing("dev", 10, 3.0)
    cost.record_timing("band", 5, 5.0)
    assert cost.items_per_second("dev") == 4.0
    assert cost.items_per_second() == 25 / 10
    assert cost.total() == (0.0, False)  # timings never touch dollars
