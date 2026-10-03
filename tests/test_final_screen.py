import json

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.widgets import DataTable, Static

from hunches import files
from hunches.app import HunchesApp
from hunches.screens.final import FinalScreen
from hunches.screens.gold import GoldScreen

pytestmark = pytest.mark.usefixtures("system_ready")


def classifier(messages, info: AgentInfo):
    """Answers "b" for item 0 and "a" for the rest, whatever the prompt says."""
    request = messages[0]
    assert isinstance(request, ModelRequest)
    text = str(next(p.content for p in request.parts if p.part_kind == "user-prompt"))
    answer = ["b"] if text == "item 0" else ["a"]
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, {"response": answer})]
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
        assert panel.border_title == f"test set · held out · {stamp}"
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
        assert screen.query_one("#dis-panel").border_title == "disagreements · 1"
        assert screen.query_one("#text-panel").border_title == "text"

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
