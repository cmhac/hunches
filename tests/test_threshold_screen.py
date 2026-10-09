import asyncio
import json

import pytest
from conftest import panel_title
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.widgets import Button, DataTable, Static

from hunches import files, history
from hunches.app import HunchesApp
from hunches.screens import threshold
from hunches.screens.progress import RunIndicator
from hunches.screens.threshold import ThresholdScreen

pytestmark = pytest.mark.usefixtures("system_ready")


def classifier(messages, info: AgentInfo):
    """off_topic for even item numbers, "a" for odd ones."""
    request = messages[0]
    assert isinstance(request, ModelRequest)
    text = str(next(p.content for p in request.parts if p.part_kind == "user-prompt"))
    answer = ["off_topic"] if int(text.split()[-1]) % 2 == 0 else ["a"]
    return ModelResponse(
        parts=[
            ToolCallPart(
                info.output_tools[0].name, {"reasoning": "r", "labels": answer}
            )
        ]
    )


async def wait_for(pilot, test):
    for _ in range(300):
        if test():
            return
        await pilot.pause(0.02)
    raise AssertionError("timed out")


# band 0 (0.60): 40 items, band 1 (0.625): 0 items, band 6 (0.75+): 10 items
SIMS = [0.61] * 40 + [0.80] * 10


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
        )
    )
    files.write_taxonomy(files.Taxonomy(mode="single", labels=[files.Label(name="a")]))
    files.write_text("prompt.md", "Classify.")
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": str(i), "text": f"item {i}", "max_similarity": s, "best_seed": "x"}
            for i, s in enumerate(SIMS)
        ],
    )
    gold = [
        files.GoldRow(id=f"g{i}", text="t", labels=["a"], split=s)
        for s in ("dev", "test")
        for i in range(50)
    ]
    files.write_gold(gold)


def test_band_sampling_counts_and_persistence():
    cands = files.read_jsonl("candidates.jsonl")
    ids = threshold.sample_bands(cands)
    assert [len(x) for x in ids] == [30, 0, 0, 0, 0, 0, 10]
    assert threshold.sample_bands([]) == ids  # reopening reads the saved sample


def test_rate_calculation_and_empty_band():
    ids = [["1", "2", "3", "4"], [], [], [], [], [], []]
    preds = {"1": ["off_topic"], "2": ["a"], "3": ["off_topic"], "4": None}
    cands = [{"id": str(i), "max_similarity": 0.61} for i in range(1, 5)]
    rows = threshold.band_rows(cands, ids, preds)
    assert (rows[0]["sampled"], rows[0]["off_topic"], rows[0]["cumulative"]) == (
        3,
        2,
        4,
    )
    assert threshold.rate_text(rows[0]) == "67% (n=3)"
    assert threshold.rate_text(rows[1]) == "-" and rows[1]["candidates"] == 0


def stub_classifier(monkeypatch, counter=None):
    real = threshold.classify_many

    def fake(texts, prompt, taxonomy, model):
        if counter is not None:
            counter.append(len(texts))
        return real(texts, prompt, taxonomy, FunctionModel(classifier))

    monkeypatch.setattr(threshold, "classify_many", fake)


async def settle(app, pilot):
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_screen_classifies_and_saves_chosen_band(monkeypatch):
    stub_classifier(monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 7 and isinstance(app.screen, ThresholdScreen)
        await settle(app, pilot)
        table = app.screen.query_one("#bands", DataTable)
        assert [str(c) for c in table.get_row_at(0)[:3]] == ["  0.600", "40", "30"]
        assert str(table.get_row_at(1)[3]) == "-"
        save = app.screen.query_one("#save", Button)
        line = app.screen.query_one("#cutoff-line", Static)
        assert save.disabled and str(line.render()) == "No cutoff chosen"
        app.screen.action_save()  # nothing chosen: silent no-op
        await pilot.pause()
        assert files.read_text("threshold.json") is None and app.stage == 7
        table.focus()
        await pilot.press("down", "down", "enter")  # band 2 = 0.650
        await pilot.pause()
        assert str(table.get_row_at(2)[0]) == "● 0.650"
        assert str(table.get_row_at(0)[0]) == "  0.600"
        assert str(line.render()) == "Cutoff 0.650" and not save.disabled
        await pilot.press("down", "enter")  # choosing another moves the mark
        await pilot.pause()
        assert str(table.get_row_at(2)[0]) == "  0.650"
        assert str(table.get_row_at(3)[0]) == "● 0.675"
        await pilot.press("up", "enter")
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
    data = json.loads(files.read_text("threshold.json") or "")
    # items at 0.80 are the only ones at or above 0.650
    assert data["threshold"] == 0.65 and data["n_candidates"] == 10
    assert len(data["bands"]) == 7
    assert files.read_state().threshold_chosen
    (entry,) = [e for e in history.entries() if e["kind"] == "approval"]
    assert (entry["stage"], entry["flag"], entry["summary"]) == (
        7,
        "threshold_chosen",
        "Approved: Cutoff 0.650 (10 candidates)",
    )
    assert files.first_incomplete_stage() == 8


async def test_preselect_on_edge_and_saved_off_edge(monkeypatch):
    stub_classifier(monkeypatch)
    files.write_text("threshold.json", json.dumps({"threshold": 0.7}))
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await settle(app, pilot)
        table = app.screen.query_one("#bands", DataTable)
        assert str(table.get_row_at(4)[0]) == "● 0.700"
        assert str(app.screen.query_one("#cutoff-line", Static).render()) == (
            "Cutoff 0.700"
        )
        assert not app.screen.query_one("#save", Button).disabled
    files.write_text("threshold.json", json.dumps({"threshold": 0.652}))
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await settle(app, pilot)
        table = app.screen.query_one("#bands", DataTable)
        assert all(not str(table.get_row_at(i)[0]).startswith("●") for i in range(7))
        line = app.screen.query_one("#cutoff-line", Static)
        assert str(line.render()) == "Saved cutoff 0.652"
        assert app.screen.query_one("#save", Button).disabled


async def test_sampling_shows_indicator_stop_and_resume(monkeypatch):
    calls = []
    real = threshold.classify_many
    gate = asyncio.Event()

    async def slow(texts, prompt, taxonomy, model):
        calls.append(len(texts))
        n = 0
        async for i, p in real(texts, prompt, taxonomy, FunctionModel(classifier)):
            yield i, p
            n += 1
            if n == 5 and len(calls) == 1:
                await gate.wait()  # parked until the user stops

    monkeypatch.setattr(threshold, "classify_many", slow)
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThresholdScreen)
        await wait_for(pilot, lambda: len(screen.predictions) >= 5)
        ind = screen.query_one(RunIndicator)
        assert ind.display and not screen.query_one("#bands-panel").display
        assert str(ind.query_one("#run-title", Static).content) == (
            "Sampling each similarity band"
        )
        counts = str(ind.query_one("#run-counts", Static).content)
        assert counts.startswith("5 of 40") and counts.endswith("30 items per band")
        assert str(ind.query_one("#run-button", Button).label) == "Stop  x"
        await pilot.press("x")
        await wait_for(pilot, lambda: screen.stopped)
        saved = json.loads(files.read_text(threshold.SAMPLE) or "")
        assert len(saved["predictions"]) == 5  # finished items kept
        assert ind.display and not screen.query_one("#bands-panel").display
        assert str(ind.query_one("#run-button", Button).label) == "Resume  s"
        await pilot.press("s")
        await wait_for(pilot, lambda: not screen.running and not screen.stopped)
        assert calls == [40, 35]  # only the remainder is classified
        assert not ind.display and screen.query_one("#bands-panel").display
        assert len(screen.predictions) == 40


async def test_failure_shows_panel_and_note(monkeypatch):
    async def boom(texts, prompt, taxonomy, model):
        raise RuntimeError("429")
        yield  # pragma: no cover

    monkeypatch.setattr(threshold, "classify_many", boom)
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await settle(app, pilot)
        screen = app.screen
        assert screen.query_one("#bands-panel").display
        assert not screen.query_one(RunIndicator).display
        note = screen.query_one("#note", Static)
        assert str(note.render()) == "Sampling failed: 429"
        assert note.has_class("error")


async def test_redesigned_panel_notes_and_not_ready(monkeypatch):
    stub_classifier(monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThresholdScreen)
        await settle(app, pilot)
        panel = screen.query_one("#bands-panel")
        assert panel_title(panel)[0] == "off-topic rate by band · test"
        assert panel_title(panel)[1] == ""
        table = screen.query_one("#bands", DataTable)
        assert [str(c.label) for c in table.columns.values()] == [
            "Band",
            "Candidates",
            "Sampled",
            "Off-topic rate",
            "Cumulative ≥ lower",
        ]
        assert [str(c) for c in table.get_row_at(6)] == [
            "  0.750+",
            "10",
            "10",
            "50% (n=10)",
            "10",
        ]
        note = screen.query_one("#note", Static)
        assert str(note.render()).startswith("Sampled 40 items in ")
        assert note.has_class("note")
        explain = str(screen.query_one("#explain").render())
        assert explain.endswith("Enter on a row chooses its lower bound as the cutoff.")
        assert not screen.query("#cutoff")


@pytest.mark.usefixtures("stub_taxonomy_assistant")
async def test_not_ready_notice():
    (files.root() / "taxonomy.yaml").unlink()
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(7)
        await pilot.pause()
        notice = app.screen.query_one("#not-ready")
        assert str(notice.render()) == "Finish stage 3 (taxonomy and prompt) first."
        assert notice.has_class("not-ready")
