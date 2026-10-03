import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.widgets import DataTable, Static

from hunches import files
from hunches.app import HunchesApp
from hunches.classifier import Prediction
from hunches.screens.gold import GoldScreen, draw


def project(mode="single", n=60, gold=()):
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir="c",
            embedding_model="m",
        )
    )
    files.write_text("seeds.csv", "seed\nx\n")
    files.write_state(files.State(seeds_approved=True, taxonomy_approved=True))
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": str(i), "text": f"item {i}", "max_similarity": 0.7, "best_seed": "x"}
            for i in range(n)
        ],
    )
    files.write_taxonomy(
        files.Taxonomy(mode=mode, labels=[files.Label(name="a"), files.Label(name="b")])
    )
    files.write_text("prompt.md", "Classify.")
    files.write_gold(list(gold))


@pytest.fixture(autouse=True)
def cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def model_answering(labels):
    def fn(messages, info: AgentInfo):
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool.name, {"response": labels})])

    return FunctionModel(fn)


def counts(screen):
    table = screen.query_one("#counts", DataTable)
    return {str(k.value): str(table.get_row(k)[1]) for k in table.rows}


def test_draw_size_exclusion_and_reproducible():
    project(n=60)
    first = draw("dev", 50)
    assert len(first) == 50 and len({r.id for r in first}) == 50
    assert all(r.labels == [] and r.split == "dev" for r in first)
    assert len(files.read_gold()) == 50  # persisted immediately
    test = draw("test", 50)
    assert len(test) == 10  # only 10 candidates left
    assert not {r.id for r in first} & {r.id for r in test}
    # same project state, same draw
    files.write_gold([])
    assert [r.id for r in draw("dev", 50)] == [r.id for r in first]


async def test_single_mode_labels_persist_and_prediction_shown_after():
    project("single")
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GoldScreen)
        screen.model = model_answering(["a"])
        assert len(files.read_gold()) == 50
        assert str(screen.query_one("#prediction", Static).render()) == ""
        await pilot.press("1")
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.press("0", "2")  # off_topic, then b
        await pilot.pause()
        await app.workers.wait_for_complete()
        gold = files.read_gold()
        assert [r.labels for r in gold[:3]] == [["a"], ["off_topic"], ["b"]]
        assert counts(screen)["a"] == "1" and counts(screen)["off_topic"] == "1"
        assert screen.index == 3
        await pilot.press("left")  # back to item 3 (b): model said a
        await pilot.pause()
        assert "DIFFERS" in str(screen.query_one("#prediction", Static).render())
        assert files.first_incomplete_stage() == 4  # not complete until 50 labelled


async def test_multi_mode_toggle_and_invalid_refused():
    project("multi")
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GoldScreen)
        screen.model = model_answering(["a", "b"])
        await pilot.press("enter")  # nothing chosen
        await pilot.pause()
        assert files.read_gold()[0].labels == []
        assert "Not saved" in screen.note
        await pilot.press("1", "2", "0")  # off_topic clears a and b
        assert screen.pending == ["off_topic"]
        await pilot.press("1")  # a clears off_topic
        assert screen.pending == ["a"]
        await pilot.press("2", "1")  # add b, remove a
        assert screen.pending == ["b"]
        await pilot.press("1", "enter")
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert files.read_gold()[0].labels == ["b", "a"]
        assert screen.index == 1


async def test_resume_skip_draw_more_and_finish():
    gold = [
        files.GoldRow(id=str(i), text=f"item {i}", labels=["a"], split="dev")
        for i in range(5)
    ] + [
        files.GoldRow(id=str(i), text=f"item {i}", labels=[], split="dev")
        for i in range(5, 50)
    ]
    project("single", n=100, gold=gold)
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GoldScreen)
        assert screen.index == 5 and len(screen.rows) == 50  # resumed, same items
        await pilot.press("right")
        assert screen.index == 6 and files.read_gold()[5].labels == []
        await pilot.press("f2")  # unlabelled items remain
        await pilot.pause()
        assert screen.is_current and "unlabelled" in screen.note
        await pilot.press("d")
        assert len(screen.rows) == 60 and len(files.read_gold()) == 60
        await pilot.press("left" * 1)
        for row in screen.rows:
            row.labels = ["b"]
        files.write_gold(screen.all)
        assert files.first_incomplete_stage() == 5
        await pilot.press("f2")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert app.stage == 5


def test_gold_file_is_jsonl():
    project()
    draw("dev", 2)
    lines = (files.root() / "gold.jsonl").read_text().splitlines()
    assert json.loads(lines[0])["labels"] == []


def text(screen, id_):
    return str(screen.query_one(id_, Static).render())


def squashed(screen, id_):
    return " ".join(text(screen, id_).split())


async def test_redesigned_layout_80x24_single():
    project("single")
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GoldScreen)
        assert text(screen, "#progress") == "dev set  item 1/50, 0 labelled"
        item = screen.query_one("#item")
        first = screen.rows[0]
        assert item.border_title == f"item {first.id}"
        assert "item" in text(screen, "#text")
        labels = screen.query_one("#labels-panel")
        assert labels.border_title == "labels · single"
        assert labels.border_subtitle == "press a key to label"
        counts_panel = screen.query_one("#counts-panel")
        assert counts_panel.border_title == "counts"
        assert counts_panel.border_subtitle == "0 of 50"
        assert counts_panel.outer_size.width <= 30
        rows = text(screen, "#labels").splitlines()
        assert [r.split()[0] for r in rows] == ["1", "2", "0"]  # off_topic is last
        assert all("○" in r for r in rows)
        for widget in screen.query("#item, #labels-panel, #counts-panel"):
            assert widget.region.bottom <= 23


async def test_label_rows_marks_and_counts_subtitle():
    project("single")
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GoldScreen)
        screen.model = model_answering(["a"])
        await pilot.press("1")
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.press("left")
        rows = text(screen, "#labels").splitlines()
        assert "●" in rows[0] and "○" in rows[1]  # the saved label is filled
        assert screen.query_one("#counts-panel").border_subtitle == "1 of 50"
        assert text(screen, "#progress") == "dev set  item 1/50, 1 labelled"


async def test_multi_mode_uses_square_marks_and_hint():
    project("multi")
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#labels-panel").border_title == "labels · multi"
        assert (
            screen.query_one("#labels-panel").border_subtitle
            == "keys toggle, enter confirms"
        )
        await pilot.press("2")
        rows = text(screen, "#labels").splitlines()
        assert "□" in rows[0] and "■" in rows[1] and "□" in rows[2]


async def test_prediction_line_variants():
    project("single")
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GoldScreen)
        screen.rows[0].labels = ["a"]
        screen.show()
        assert text(screen, "#prediction") == "Model: (not classified)"
        screen.predictions[screen.rows[0].id] = None
        screen.show()
        assert text(screen, "#prediction") == "Model: classifying..."
        screen.predictions[screen.rows[0].id] = Prediction(None, error="boom")
        screen.show()
        assert text(screen, "#prediction") == "Model: failed (boom)"
        assert screen.query_one("#prediction").has_class("error")
        screen.predictions[screen.rows[0].id] = Prediction(["a"])
        screen.show()
        assert text(screen, "#prediction") == "Model: ■ a ✓ agrees"
        screen.predictions[screen.rows[0].id] = Prediction(["b"])
        screen.show()
        assert squashed(screen, "#prediction") == "Model: ■ b DIFFERS"


async def test_not_ready_notice():
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir="c",
            embedding_model="m",
        )
    )
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(4)
        await pilot.pause()
        notice = app.screen.query_one("#not-ready")
        assert str(notice.render()) == "Finish stage 3 (taxonomy and prompt) first."
        assert notice.has_class("warn")
