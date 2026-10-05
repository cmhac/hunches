import asyncio
import hashlib
import json

import pytest
from conftest import panel_title
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RunUsage
from textual.widgets import Static

from hunches import cost, files
from hunches.app import HunchesApp
from hunches.classifier import Prediction
from hunches.screens import run
from hunches.screens.run import RunScreen

pytestmark = pytest.mark.usefixtures("system_ready")

PROMPT = "Classify."


def classifier(messages, info: AgentInfo):
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, {"response": ["a"]})]
    )


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            corpus_dir="c",
            embedding_model="m",
            classifier_model="test",
        )
    )
    files.write_text("seeds.csv", "seed\nx\n")
    files.write_state(
        files.State(
            seeds_approved=True,
            taxonomy_approved=True,
            dev_done=True,
            test_done=True,
            threshold_chosen=True,
        )
    )
    files.write_taxonomy(files.Taxonomy(mode="single", labels=[files.Label(name="a")]))
    files.write_text("prompt.md", PROMPT)
    files.write_text("threshold.json", json.dumps({"threshold": 0.65}))
    files.write_text(
        "test_result.json",
        json.dumps(
            {
                "prompt_hash": hashlib.sha256(
                    json.dumps([PROMPT, "test"]).encode()  # prompt, classifier_model
                ).hexdigest()
            }
        ),
    )
    # items 0-5 are at or above the threshold, 6-7 below it
    files.write_jsonl(
        "candidates.jsonl",
        [
            {
                "id": str(i),
                "text": f"item {i}",
                "max_similarity": 0.7 if i < 6 else 0.62,
                "best_seed": "x",
            }
            for i in range(8)
        ],
    )
    files.write_gold(
        [
            files.GoldRow(id=f"g{i}", text="t", labels=["a"], split=s)
            for s in ("dev", "test")
            for i in range(50)
        ]
    )


REAL = run.classify_many


def use_function_model(monkeypatch):
    real = REAL
    monkeypatch.setattr(
        run,
        "classify_many",
        lambda texts, prompt, taxonomy, model: real(
            texts, prompt, taxonomy, FunctionModel(classifier)
        ),
    )


def ids(rows):
    return sorted(r["id"] for r in rows)


def test_pending_skips_done_and_retries_errors():
    files.append_jsonl("results.jsonl", {"id": "0", "labels": ["a"]})
    files.append_jsonl("results.jsonl", {"id": "1", "labels": [], "error": "boom"})
    assert [c["id"] for c in run.pending()] == ["1", "2", "3", "4", "5"]


def test_estimates_from_fixture_timings(monkeypatch):
    cost.record_timing("classify", 10, 5.0)  # 2 items/s
    cost.record("test", RunUsage(input_tokens=1, output_tokens=1), 0.5)
    cost.record("test", RunUsage(input_tokens=1, output_tokens=1), 1.5)
    text = run.estimate(20, "test")
    assert "20 items" in text and "10s at 2.00 items/s" in text and "~$20.0000" in text


def test_estimates_unknown_price_and_no_samples():
    assert "no timing samples" in run.estimate(5, "test")
    assert "no sample usage" in run.estimate(5, "test")
    cost.record("test", RunUsage(input_tokens=1, output_tokens=1), None)
    text = run.estimate(5, "test")
    assert "cost ?" in text and "$" not in text


async def test_full_run_resumes_and_skips_done(monkeypatch):
    use_function_model(monkeypatch)
    files.append_jsonl(
        "results.jsonl",
        {"id": "0", "text": "item 0", "labels": ["a"], "max_similarity": 0.7},
    )
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 8 and isinstance(app.screen, RunScreen)
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
    rows = files.read_jsonl("results.jsonl")
    assert ids(rows) == [
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
    ]  # 6 and 7 are below the threshold
    assert files.first_incomplete_stage() == 9


async def test_stop_mid_run_leaves_valid_file_then_next_run_finishes(monkeypatch):
    async def stalls(texts, prompt, taxonomy, model):
        for i in range(2):
            yield i, Prediction(["a"])
        await asyncio.sleep(3600)

    monkeypatch.setattr(run, "classify_many", stalls)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause(0.2)
        await pilot.press("x")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not app.screen.running  # ty: ignore[unresolved-attribute]
    assert len(files.read_jsonl("results.jsonl")) == 2  # every line parses
    assert files.first_incomplete_stage() == 8

    use_function_model(monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
    assert ids(files.read_jsonl("results.jsonl")) == ["0", "1", "2", "3", "4", "5"]


async def test_error_rows_listed_then_retried(monkeypatch):
    async def fails_item_2(texts, prompt, taxonomy, model):
        for i, t in enumerate(texts):
            yield (
                i,
                Prediction(None, error="bad") if t == "item 2" else Prediction(["a"]),
            )

    monkeypatch.setattr(run, "classify_many", fails_item_2)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "2: bad" in str(app.screen.query_one("#errors", Static).render())
    assert files.first_incomplete_stage() == 8
    assert [c["id"] for c in run.pending()] == ["2"]

    use_function_model(monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
    rows = files.read_jsonl("results.jsonl")
    assert ids(rows) == ["0", "1", "2", "3", "4", "5"]  # the error row was replaced
    assert not any("error" in r for r in rows)


async def test_prompt_change_warns_before_starting(monkeypatch):
    use_function_model(monkeypatch)
    files.write_text("prompt.md", "Changed.")
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert "differs" in str(app.screen.query_one("#warn", Static).render())
        assert files.read_jsonl("results.jsonl") == []
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
    assert len(files.read_jsonl("results.jsonl")) == 6


async def test_redesigned_panels_subtitles_and_banner(monkeypatch):
    async def stalls(texts, prompt, taxonomy, model):
        for i in range(2):
            yield i, Prediction(["a"])
        await asyncio.sleep(3600)

    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunScreen)
        run_panel = screen.query_one("#run-panel")
        assert panel_title(screen.query_one("#estimate-panel"))[0] == "estimate"
        assert panel_title(run_panel)[0] == "run · results.jsonl"
        assert panel_title(run_panel)[1] == "not started"
        assert run_panel.has_class("-focused")
        assert not screen.query_one("#warn").display

        monkeypatch.setattr(run, "classify_many", stalls)
        files.write_text("prompt.md", "Changed.")
        await pilot.press("s")
        warn = screen.query_one("#warn", Static)
        assert warn.display and warn.has_class("banner", "-warning")
        assert str(warn.render()).startswith(
            "WARNING: prompt.md or classifier model differs"
        )
        await pilot.press("s")
        await pilot.pause(0.2)
        assert panel_title(run_panel)[1] == "running"
        live = str(screen.query_one("#live", Static).render())
        assert live.startswith("2/6 | cost ")
        await pilot.press("x")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert panel_title(run_panel)[1] == "stopped · resumable"

        use_function_model(monkeypatch)
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert panel_title(run_panel)[1] == "complete"


async def test_failures_list_and_run_failed_error_class(monkeypatch):
    async def fails_item_2(texts, prompt, taxonomy, model):
        for i, t in enumerate(texts):
            yield (
                i,
                Prediction(None, error="bad") if t == "item 2" else Prediction(["a"]),
            )

    monkeypatch.setattr(run, "classify_many", fails_item_2)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
        errors = screen.query_one("#errors", Static)
        assert str(errors.render()).splitlines() == [
            "",
            "Failed (retried next run):",
            "2: bad",
        ]

    async def boom(texts, prompt, taxonomy, model):
        raise RuntimeError("no key")
        yield  # pragma: no cover

    monkeypatch.setattr(run, "classify_many", boom)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
        live = screen.query_one("#live", Static)
        assert str(live.render()) == "Run failed: no key"
        assert live.has_class("error")


async def test_not_ready_notice():
    (files.root() / "threshold.json").unlink()
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(8)
        await pilot.pause()
        notice = app.screen.query_one("#not-ready")
        assert str(notice.render()) == "Finish stages 3 and 7 first."
        assert notice.has_class("not-ready")
