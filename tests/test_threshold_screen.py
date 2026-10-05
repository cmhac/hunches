import json

import pytest
from conftest import panel_title
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.widgets import DataTable, Input, Static

from hunches import files
from hunches.app import HunchesApp
from hunches.screens import threshold
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


async def test_screen_classifies_and_saves_threshold(monkeypatch):
    real = threshold.classify_many
    monkeypatch.setattr(
        threshold,
        "classify_many",
        lambda texts, prompt, taxonomy, model: real(
            texts, prompt, taxonomy, FunctionModel(classifier)
        ),
    )
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 7 and isinstance(app.screen, ThresholdScreen)
        await app.workers.wait_for_complete()
        await pilot.pause()
        table = app.screen.query_one("#bands", DataTable)
        assert [str(c) for c in table.get_row_at(0)[:3]] == ["0.600", "40", "30"]
        assert str(table.get_row_at(1)[3]) == "-"
        app.screen.query_one("#cutoff", Input).value = "0.7"
        app.screen.action_save()
        await pilot.pause()
    data = json.loads(files.read_text("threshold.json") or "")
    assert data["threshold"] == 0.7 and data["n_candidates"] == 10
    assert len(data["bands"]) == 7
    assert files.read_state().threshold_chosen
    assert files.first_incomplete_stage() == 8


async def test_redesigned_panel_notes_and_not_ready(monkeypatch):
    real = threshold.classify_many
    monkeypatch.setattr(
        threshold,
        "classify_many",
        lambda texts, prompt, taxonomy, model: real(
            texts, prompt, taxonomy, FunctionModel(classifier)
        ),
    )
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThresholdScreen)
        await app.workers.wait_for_complete()
        await pilot.pause()
        panel = screen.query_one("#bands-panel")
        assert panel_title(panel)[0] == "off-topic rate by band · test"
        assert panel_title(panel)[1] == ""  # not sampling any more
        table = screen.query_one("#bands", DataTable)
        assert [str(c.label) for c in table.columns.values()] == [
            "Band",
            "Candidates",
            "Sampled",
            "Off-topic rate",
            "Cumulative ≥ lower",
        ]
        assert [str(c) for c in table.get_row_at(6)] == [
            "0.750+",
            "10",
            "10",
            "50% (n=10)",
            "10",
        ]
        note = screen.query_one("#note", Static)
        assert str(note.render()).startswith("Sampled 40 items in ")
        assert note.has_class("note")
        screen.progress = (112, 210)
        screen.show()
        assert panel_title(panel)[1] == "sampling 112/210"
        assert "Small samples are noisy" in str(screen.query_one("#explain").render())

        screen.query_one("#cutoff", Input).value = "abc"
        screen.action_save()
        assert str(note.render()) == "Enter a number or pick a band with Enter."
        assert note.has_class("warn")
        screen.note = "Sampling failed: x"
        screen.show()
        assert note.has_class("error")

        table.focus()
        await pilot.press("enter")  # picks the band's lower bound
        await pilot.pause()
        assert screen.query_one("#cutoff", Input).value == "0.6"


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
