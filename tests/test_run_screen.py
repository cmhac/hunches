import asyncio
import hashlib
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RunUsage
from textual.widgets import Button, Static
from textual.widgets._footer import FooterKey

from hunches import cost, files
from hunches.app import HunchesApp
from hunches.classifier import Prediction
from hunches.screens import run
from hunches.screens.progress import RunIndicator
from hunches.screens.run import RunScreen

pytestmark = pytest.mark.usefixtures("system_ready")

PROMPT = "Classify."


def classifier(messages, info: AgentInfo):
    return ModelResponse(
        parts=[
            ToolCallPart(info.output_tools[0].name, {"reasoning": "r", "labels": ["a"]})
        ]
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
    assert files.first_incomplete_stage() == 8
    assert [c["id"] for c in run.pending()] == ["2"]
    # the failure stays in results.jsonl as an error row, exactly as before
    assert [r["error"] for r in files.read_jsonl("results.jsonl") if "error" in r] == [
        "bad"
    ]

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


def footer_keys(app) -> set[str]:
    return {k.key for k in app.screen.query(FooterKey)}


def block(screen) -> tuple[str, str, str, str]:
    """(title, counts, status, button label or '') as the user sees them."""
    ind = screen.query_one(RunIndicator)
    status = ind.query_one("#run-status", Static)
    button = ind.query_one("#run-button", Button)
    return (
        str(ind.query_one("#run-title", Static).render()),
        str(ind.query_one("#run-counts", Static).render()),
        str(status.render()) if status.display else "",
        str(button.label) if button.display else "",
    )


async def test_untested_prompt_is_a_hard_block(monkeypatch):
    use_function_model(monkeypatch)
    files.write_text("prompt.md", "Changed.")
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunScreen)
        assert not screen.query_one(RunIndicator).display
        banner = screen.query_one("#blocked-text", Static)
        assert str(banner.render()) == (
            "Cannot start: prompt.md differs from the tested prompt (or was never tested). "
            "Run the dev set in the Tuning loop with this prompt first."
        )
        assert banner.has_class("banner", "-stale")
        assert not screen.query("#warn")
        assert footer_keys(app).isdisjoint({"s", "x"})
        await pilot.press("s")
        screen.action_start()  # called directly: the guard stays in the method
        await pilot.pause()
        assert screen.worker is None and not screen.running
        assert files.read_jsonl("results.jsonl") == []
        assert not (files.root() / "results.jsonl").exists()
        await pilot.click("#go-tuning")
        await pilot.pause()
        assert app.stage == 5


async def test_never_tested_prompt_is_blocked():
    (files.root() / "test_result.json").unlink()
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunScreen)
        assert screen.query_one("#blocked").display
        screen.action_start()
        await pilot.pause()
        assert screen.worker is None


async def test_state_table(monkeypatch):
    async def stalls(texts, prompt, taxonomy, model):
        for i in range(2):
            yield i, Prediction(["a"])
        await asyncio.sleep(3600)

    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunScreen)
        # not started
        assert block(screen) == (
            "Ready to classify",
            "0 of 6",
            (
                "6 items to classify; time no timing samples yet, so no time estimate; "
                "cost no sample usage yet, so no cost estimate"
            ),
            "Start  s",
        )
        assert not screen.query_one("#blocked").display
        assert {"s"} <= footer_keys(app) and "x" not in footer_keys(app)
        # running
        monkeypatch.setattr(run, "classify_many", stalls)
        await pilot.press("s")
        await pilot.pause(0.2)
        assert block(screen) == ("Classifying candidates", "2 of 6", "", "Stop  x")
        assert "x" in footer_keys(app) and "s" not in footer_keys(app)
        await pilot.press("x")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # stopped, no failures
        assert block(screen) == ("Stopped", "2 of 6", "", "Resume  s")
        assert "s" in footer_keys(app)
        # complete
        use_function_model(monkeypatch)
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert block(screen) == (
            "Complete",
            "6 of 6",
            "Nothing to classify; every candidate at or above the threshold is done.",
            "",
        )
        assert footer_keys(app).isdisjoint({"s", "x"})
        screen.action_start()
        await pilot.pause()
        assert screen.worker is not None and not screen.running


async def test_stopped_with_failures_and_run_failed(monkeypatch):
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
        assert block(screen) == (
            "Stopped",
            "5 of 6",
            "1 items failed and are retried on the next run",
            "Resume  s",
        )
        assert screen.query_one("#run-status").has_class("warn")

    async def boom(texts, prompt, taxonomy, model):
        raise RuntimeError("no key")
        yield  # pragma: no cover

    files.write_jsonl("results.jsonl", [])
    monkeypatch.setattr(run, "classify_many", boom)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert block(screen) == (
            "Run failed",
            "0 of 6",
            "Run failed: no key",
            "Resume  s",
        )
        assert screen.query_one("#run-status").has_class("error")


async def test_button_starts_and_stops(monkeypatch):
    async def stalls(texts, prompt, taxonomy, model):
        yield 0, Prediction(["a"])
        await asyncio.sleep(3600)

    monkeypatch.setattr(run, "classify_many", stalls)
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        await pilot.click("#run-button")
        await pilot.pause(0.2)
        assert block(screen)[0] == "Classifying candidates"
        await pilot.click("#run-button")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert block(screen) == ("Stopped", "1 of 6", "", "Resume  s")


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
