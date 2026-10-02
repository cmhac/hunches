import json

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.widgets import DataTable, Input

from hunches import files
from hunches.app import HunchesApp
from hunches.screens import threshold
from hunches.screens.threshold import ThresholdScreen


def classifier(messages, info: AgentInfo):
    """off_topic for even item numbers, "a" for odd ones."""
    request = messages[0]
    assert isinstance(request, ModelRequest)
    text = str(next(p.content for p in request.parts if p.part_kind == "user-prompt"))
    answer = ["off_topic"] if int(text.split()[-1]) % 2 == 0 else ["a"]
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, {"response": answer})]
    )


# band 0 (0.60): 40 items, band 1 (0.625): 0 items, band 6 (0.75+): 10 items
SIMS = [0.61] * 40 + [0.80] * 10


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.write_config(
        files.Config(corpus_dir="c", embedding_model="m", cheap_model="test")
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
        assert table.get_row_at(0)[:3] == ["0.600", "40", "30"]
        assert table.get_row_at(1)[3] == "-"
        app.screen.query_one("#cutoff", Input).value = "0.7"
        app.screen.action_save()
        await pilot.pause()
    data = json.loads(files.read_text("threshold.json") or "")
    assert data["threshold"] == 0.7 and data["n_candidates"] == 10
    assert len(data["bands"]) == 7
    assert files.read_state().threshold_chosen
    assert files.first_incomplete_stage() == 8
