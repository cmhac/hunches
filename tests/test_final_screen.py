import asyncio
import json

import pytest
from conftest import panel_title
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.widgets import Button, DataTable, Static

from hunches import files, history
from hunches.app import HunchesApp
from hunches.screens import final
from hunches.screens.final import FinalScreen
from hunches.screens.gold import GoldScreen
from hunches.screens.progress import RunIndicator

pytestmark = pytest.mark.usefixtures("system_ready")


def classifier(messages, info: AgentInfo):
    """Answers "b" for item 0 and "a" for the rest, whatever the prompt says."""
    request = messages[0]
    assert isinstance(request, ModelRequest)
    text = str(next(p.content for p in request.parts if p.part_kind == "user-prompt"))
    answer = ["b"] if text == "item 0" else ["a"]
    return ModelResponse(
        parts=[
            ToolCallPart(
                info.output_tools[0].name, {"reasoning": "r", "labels": answer}
            )
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
        files.State(seeds_approved=True, taxonomy_approved=True, dev_done=True)
    )
    files.write_taxonomy(
        files.Taxonomy(
            mode="single", labels=[files.Label(name="a"), files.Label(name="b")]
        )
    )
    files.write_text("prompt.md", "Classify.")
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": str(i), "text": f"item {i}", "max_similarity": 0.7, "best_seed": "x"}
            for i in range(120)
        ],
    )


def gold_rows(n_dev=50, n_test=0, labelled=True):
    dev = [
        files.GoldRow(id=str(i), text=f"item {i}", labels=["a"], split="dev")
        for i in range(n_dev)
    ]
    test = [
        files.GoldRow(
            id=str(i), text=f"item {i}", labels=["a"] if labelled else [], split="test"
        )
        for i in range(50, 50 + n_test)
    ]
    return dev + test


def test_draw_is_disjoint_from_dev():
    from hunches.screens import gold

    files.write_gold(gold_rows())
    new = gold.draw("test", 50)
    assert len(new) == 50 and {r.id for r in new}.isdisjoint(str(i) for i in range(50))
    assert len({r.id for r in files.read_gold()}) == 100


async def test_unlabelled_test_set_shows_labelling_screen():
    files.write_gold(gold_rows())
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 6 and isinstance(app.screen, GoldScreen)
        assert app.screen.split == "test"
        assert len([r for r in files.read_gold() if r.split == "test"]) == 50


async def test_run_metrics_staleness_and_accept():
    # test items are item 50..59; item 0 is not among them, so the model says "a" everywhere,
    # except gold for item 50 is "b" -> 1 disagreement in 10
    rows = gold_rows(n_test=10)
    rows[50].labels = ["b"]
    files.write_gold(rows)
    assert files.first_incomplete_stage() == 6
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FinalScreen)
        screen.model = FunctionModel(classifier)  # ty: ignore[invalid-assignment]
        screen.action_rerun()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        saved = json.loads(files.read_text("test_result.json") or "")
        # hand-computed: exact match 9/10; a: tp9 fp1 fn0 -> P .9 R 1 F1 18/19; b: F1 0; macro = 9/19
        assert saved["metrics"]["exact_match"] == pytest.approx(0.9)
        assert saved["metrics"]["macro_f1"] == pytest.approx(9 / 19)
        assert saved["metrics"]["micro_f1"] == pytest.approx(0.9)
        assert saved["prompt_hash"]
        assert screen.query_one("#dis", DataTable).row_count == 1
        assert not screen.stale()
        files.write_text("prompt.md", "Classify differently.")
        assert screen.stale()
        screen.show()
        assert "STALE" in str(screen.query_one("#banner", Static).render())
        await pilot.press("f2")  # stale: refused
        await pilot.pause()
        assert not files.read_state().test_done
        screen.action_rerun()
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert not screen.stale()
        files.write_config(
            files.Config(
                assistant_model="anthropic:claude-sonnet-5-5",
                corpus_dir="c",
                embedding_model="m",
                classifier_model="other",
            )
        )
        assert screen.stale()  # a classifier change alone marks the result STALE
        screen.show()
        assert str(screen.query_one("#banner", Static).render()).startswith(
            "STALE: prompt.md or classifier model changed"
        )
        files.write_config(
            files.Config(
                assistant_model="anthropic:claude-sonnet-5-5",
                corpus_dir="c",
                embedding_model="m",
                classifier_model="test",
            )
        )
        assert not screen.stale()
        await pilot.press("f2")
        await pilot.pause()
        assert files.read_state().test_done
        (entry,) = [e for e in history.entries() if e["kind"] == "approval"]
        assert (entry["stage"], entry["flag"], entry["summary"]) == (
            6,
            "test_done",
            "Approved: Gold test (test accuracy 0.900)",
        )
        assert app.stage == 7


async def test_back_to_tuning():
    files.write_gold(gold_rows(n_test=10))
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FinalScreen)
        screen.model = FunctionModel(classifier)  # ty: ignore[invalid-assignment]
        await pilot.press("t")
        await pilot.pause()
        assert app.stage == 5


async def test_redesigned_panels_banner_and_tables():
    rows = gold_rows(n_test=10)
    rows[50].labels = ["b"]
    files.write_gold(rows)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FinalScreen)
        screen.model = FunctionModel(classifier)  # ty: ignore[invalid-assignment]
        assert not screen.query_one("#banner").display
        screen.action_rerun()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        stamp = json.loads(files.read_text("test_result.json") or "")["timestamp"]
        panel = screen.query_one("#metrics-panel")
        assert panel_title(panel)[0] == f"test set · held out · {stamp}"
        assert str(screen.query_one("#warning", Static).render()) == (
            "Tuning against test disagreements weakens this held-out result."
        )
        summary = " ".join(str(screen.query_one("#summary", Static).render()).split())
        assert summary == "accuracy 0.900 PASS n=10 macro-F1 0.474 micro-F1 0.900"
        per_label = screen.query_one("#per-label", DataTable)
        assert [str(c) for c in per_label.get_row(per_label.ordered_rows[0].key)] == [
            "■ a",
            "0.90",
            "1.00",
            "0.95",
            "9",
        ]
        dis = screen.query_one("#dis", DataTable)
        assert [str(c) for c in dis.get_row_at(0)] == ["item 50", "■ b", "■ a"]
        assert panel_title(screen.query_one("#dis-panel"))[0] == "disagreements · 1"
        assert panel_title(screen.query_one("#text-panel"))[0] == (
            "text · classifier reasoning"
        )

        files.write_text("prompt.md", "Classify differently.")
        screen.show()
        banner = screen.query_one("#banner", Static)
        assert banner.display and banner.has_class("banner", "-stale")
        assert str(banner.render()) == (
            "STALE: prompt.md or classifier model changed since this result was computed. Press r to re-run."
        )
        await pilot.press("f2")
        note = screen.query_one("#note")
        assert str(note.render()) == "The result is stale: re-run (r) before accepting."
        assert note.has_class("warn")
        screen.note = "Test run failed: x"
        screen.show()
        assert note.has_class("error")


def write_result(reasoning=None, **extra):
    """A result for the prompt as it is now: one disagreement on "item 50"."""
    d = {"text": "item 50", "gold": ["b"], "predicted": ["a"]}
    if reasoning is not None:
        d["reasoning"] = reasoning
    m = {
        "n": 10,
        "exact_match": 0.9,
        "macro_f1": 0.5,
        "micro_f1": 0.9,
        "per_label": {
            k: {
                "precision": 0.5,
                "recall": 0.5,
                "f1": 0.5,
                "tp": 1,
                "fp": 1,
                "fn": 1,
                "gold_count": 2,
                "predicted_count": 2,
            }
            for k in ("a", "b")
        },
        "disagreements": [0],
    }
    files.write_text(
        "test_result.json",
        json.dumps(
            {
                "prompt_hash": final.prompt_hash(),
                "timestamp": "2026-10-02T20:41:07+00:00",
                "metrics": m,
                "disagreements": [d],
                **extra,
            }
        ),
    )


async def wait_for(pilot, cond):
    for _ in range(200):
        await pilot.pause(0.02)
        if cond():
            return
    raise AssertionError("condition not reached")


async def test_accept_disabled_unless_fresh_result(monkeypatch):
    gate = asyncio.Event()

    async def slow(texts, prompt, taxonomy, model):
        await gate.wait()
        return
        yield  # pragma: no cover

    monkeypatch.setattr(final, "classify_many", slow)
    files.write_gold(gold_rows(n_test=10))
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FinalScreen)
        accept = screen.query_one("#accept", Button)
        assert screen.running and accept.disabled  # first run in progress
        assert str(accept.label) == "Accept  F2"
        assert str(screen.query_one("#rerun", Button).label) == "Re-run  r"
        assert str(screen.query_one("#tune", Button).label) == "Back to tuning  t"
        gate.set()
        await wait_for(pilot, lambda: not screen.running)
        assert not accept.disabled  # empty run: result exists and is fresh
        files.write_text("prompt.md", "Changed.")
        screen.show()
        assert accept.disabled  # stale
        screen.result = None
        screen.show()
        assert accept.disabled  # missing


async def test_buttons_trigger_the_actions(monkeypatch):
    files.write_gold(gold_rows(n_test=10))
    write_result()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FinalScreen)
        assert not screen.query_one("#accept", Button).disabled
        await pilot.click("#accept")
        await pilot.pause()
        assert files.read_state().test_done and app.stage == 7
        app.goto_stage(6)
        await pilot.pause()
        await pilot.click("#tune")
        await pilot.pause()
        assert app.stage == 5
        app.goto_stage(6)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FinalScreen)
        screen.model = FunctionModel(classifier)
        await pilot.click("#rerun")
        await pilot.pause()
        assert screen.running or screen.worker is not None
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert str(screen.query_one("#note", Static).render()).startswith(
            "Test run finished"
        )


async def test_old_result_has_no_reasoning_new_one_shows_it():
    files.write_gold(gold_rows(n_test=10))
    write_result()  # old format: no "reasoning" key
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FinalScreen)
        assert not screen.stale()
        assert str(screen.query_one("#detail", Static).render()) == "item 50"
        assert not screen.query_one("#reasoning-head").display
        assert not screen.query_one("#reasoning").display
    write_result(reasoning="Looks like b.")
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#reasoning-head").display
        assert str(screen.query_one("#reasoning-head", Static).render()) == (
            "classifier reasoning"
        )
        assert str(screen.query_one("#reasoning", Static).render()) == "Looks like b."
    write_result(reasoning="ignored")
    data = json.loads(files.read_text("test_result.json") or "")
    data["disagreements"][0]["predicted"] = "failed"
    files.write_text("test_result.json", json.dumps(data))
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await pilot.pause()
        assert not app.screen.query_one("#reasoning-head").display


async def test_run_saves_reasoning_and_layout_follows_width(monkeypatch):
    real = final.classify_many

    def stub(texts, prompt, taxonomy, model):
        return real(texts, prompt, taxonomy, FunctionModel(classifier))

    monkeypatch.setattr(final, "classify_many", stub)
    files.write_gold(gold_rows(n_test=10))
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FinalScreen)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not screen.query_one("#body").has_class("-stacked")
    rows = gold_rows(n_test=10)
    rows[50].labels = ["b"]
    files.write_gold(rows)
    (files.root() / "test_result.json").unlink()
    app = HunchesApp()
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await pilot.pause()
        screen = app.screen
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert screen.query_one("#body").has_class("-stacked")
        saved = json.loads(files.read_text("test_result.json") or "")
        assert [d["reasoning"] for d in saved["disagreements"]] == ["r"]
        assert str(screen.query_one("#reasoning", Static).render()) == "r"


async def test_run_indicator_stop_resume_and_failure(monkeypatch):
    real = final.classify_many
    gate = asyncio.Event()
    calls = []

    async def slow(texts, prompt, taxonomy, model):
        calls.append(len(texts))
        n = 0
        async for i, p in real(texts, prompt, taxonomy, FunctionModel(classifier)):
            yield i, p
            n += 1
            if n == 4 and len(calls) == 1:
                await gate.wait()

    monkeypatch.setattr(final, "classify_many", slow)
    files.write_gold(gold_rows(n_test=10))
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FinalScreen)
        ind = screen.query_one(RunIndicator)
        await wait_for(
            pilot,
            lambda: str(ind.query_one("#run-counts", Static).content)[:4] == "4 of",
        )
        assert ind.display
        assert not screen.query_one("#metrics-panel").display
        assert not screen.query_one("#body").display
        assert str(ind.query_one("#run-title", Static).content) == (
            "Running the held-out test set"
        )
        assert str(ind.query_one("#run-counts", Static).content).endswith(
            "classifier test"
        )
        assert str(ind.query_one("#run-button", Button).label) == "Stop  x"
        await pilot.press("x")
        await wait_for(pilot, lambda: screen.stopped)
        assert ind.display and not screen.query_one("#body").display
        assert str(ind.query_one("#run-button", Button).label) == "Resume  s"
        assert screen.query_one("#accept", Button).disabled
        await pilot.press("s")
        await wait_for(pilot, lambda: not screen.running and not screen.stopped)
        assert calls == [10, 10]
        assert not ind.display and screen.query_one("#metrics-panel").display
        assert str(screen.query_one("#note", Static).render()).startswith(
            "Test run finished"
        )

        # a re-run after a result names the reason, and a failure brings the panels back
        async def boom(texts, prompt, taxonomy, model):
            raise RuntimeError("401")
            yield  # pragma: no cover

        monkeypatch.setattr(final, "classify_many", boom)
        screen.action_rerun()
        await wait_for(pilot, lambda: not screen.running)
        note = screen.query_one("#note", Static)
        assert str(note.render()) == "Test run failed: 401"
        assert note.has_class("error")
        assert not ind.display and screen.query_one("#body").display
