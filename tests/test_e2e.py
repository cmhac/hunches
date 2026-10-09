"""One scripted run through all nine stages, offline, restarting the app at every boundary."""

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest
from conftest import panel_title
from pydantic_ai import Agent, Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.usage import RequestUsage
from textual.widgets import DataTable, Input

from hunches import classifier, cost, files, system
from hunches.app import ConfirmScreen, HunchesApp
from hunches.screens.brief import BriefScreen
from hunches.screens.gold import GoldScreen
from hunches.screens.new_project import NewProjectScreen
from hunches.screens.projects import ProjectsScreen
from hunches.screens.search import SearchScreen
from hunches.screens.taxonomy import TaxonomyScreen, VersionsScreen

# 120 items: 40 at 0.61 (band 0), 40 at 0.70, 30 at 0.80, 10 at 0.30 (below the 0.60 floor).
# The seed "alpha" embeds to [1, 0], so cosine similarity is the first coordinate.
SIMS = [0.61] * 40 + [0.70] * 40 + [0.80] * 30 + [0.30] * 10
CUTOFF = 0.65


class StubEmbedder(Embedder):
    def __init__(self):
        super().__init__(TestEmbeddingModel("m"))

    async def embed_query(self, query, *, settings=None):
        return EmbeddingResult(
            [[1.0, 0.0]],
            inputs=[query],
            input_type="query",
            model_name="m",
            provider_name="test",
            usage=RequestUsage(input_tokens=3),
        )


async def brief_stream(messages, info: AgentInfo):
    if any(p.part_kind == "tool-return" for p in messages[-1].parts):
        yield "Done."
    else:
        yield {0: DeltaToolCall(name="propose_seeds", json_args='{"seeds": ["alpha"]}')}


async def taxonomy_stream(messages, info: AgentInfo):
    returns = [p for p in messages[-1].parts if p.part_kind == "tool-return"]
    if not returns:
        args = {"mode": "single", "labels": [{"name": "a", "description": "even"}]}
        yield {0: DeltaToolCall(name="write_taxonomy", json_args=json.dumps(args))}
    elif "Taxonomy written" in str(returns[0].content):
        yield {
            0: DeltaToolCall(
                name="write_prompt", json_args='{"prompt": "Label the item."}'
            )
        }
    else:
        yield "Done."


CALLS: list[
    str
] = []  # one entry per classifier model call: proves "no model call" while labelling


def classify_fn(messages, info: AgentInfo):
    """Even item numbers are "a", odd ones off_topic; the same rule the test uses as gold."""
    CALLS.append("classify")
    request = messages[0]
    assert isinstance(request, ModelRequest)
    text = str(next(p.content for p in request.parts if p.part_kind == "user-prompt"))
    answer = ["a"] if int(text.split()[-1]) % 2 == 0 else ["off_topic"]
    return ModelResponse(
        parts=[
            ToolCallPart(
                info.output_tools[0].name, {"reasoning": "r", "labels": answer}
            )
        ]
    )


def write_corpus(corpus: Path, sims: list[float]) -> None:
    corpus.mkdir(exist_ok=True)
    vectors = [[s, math.sqrt(1 - s * s)] for s in sims]
    np.save(corpus / "vectors.npy", np.array(vectors, np.float32))
    items = [{"id": f"i{n}", "text": f"item {n}"} for n in range(len(sims))]
    (corpus / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in items))
    (corpus / "meta.json").write_text(json.dumps({"embedding_model": "m"}))


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    CALLS.clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")  # never used: models are stubbed
    system.write_system(
        system.System(
            provider="anthropic",
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            recommendation_seen=system.RECOMMENDED_REVISION,
        )
    )
    write_corpus(tmp_path / "corpus", SIMS)
    # the taxonomy screen opens with a context turn: it must not reach a real model either
    original = TaxonomyScreen.__init__

    async def ready(messages, info: AgentInfo):
        yield "Ready."

    def init(self):
        original(self)
        self.agent.model = FunctionModel(stream_function=ready)

    monkeypatch.setattr(TaxonomyScreen, "__init__", init)
    # every classifier call, in every stage, goes to the FunctionModel
    monkeypatch.setattr(
        classifier, "Agent", lambda model, **kw: Agent(FunctionModel(classify_fn), **kw)
    )


async def chat(app, pilot, stream, message):
    app.screen.agent.model = FunctionModel(stream_function=stream)
    box = app.screen.query_one("#chat-input", Input)
    box.focus()
    box.value = message
    await pilot.press("enter")
    await pilot.pause(0.5)
    await app.workers.wait_for_complete()
    await pilot.pause()


async def approve(pilot, button=None):
    """Approve through the F2 key, or by clicking `button` (a screen's Approve button)."""
    if button:
        await pilot.click(button)
    else:
        await pilot.press("f2")
    await pilot.pause()
    await pilot.click("#yes")
    await pilot.pause()


async def label_all(app, pilot, count):
    """Label `count` unlabelled items like a perfect user: key 1 for "a", key 0 for off_topic."""
    screen = app.screen
    assert isinstance(screen, GoldScreen)
    for _ in range(count):
        row = screen.rows[screen.index]
        await pilot.press("1" if int(row.text.split()[-1]) % 2 == 0 else "0")
        await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_all_nine_stages_with_resume():
    await run_all_stages()


async def run_all_stages():
    # setup, then stage 1: brief and seeds
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 0 and isinstance(app.screen, ProjectsScreen)
        await pilot.press("n")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, NewProjectScreen)
        screen.query_one("#corpus", Input).value = "corpus"  # location: this folder
        await pilot.pause()
        await pilot.click("#create")
        await pilot.pause()
        assert app.stage == 1 and isinstance(app.screen, BriefScreen)
        await chat(app, pilot, brief_stream, "Find even items")
        assert files.read_text("brief.md") == "Find even items\n"
        await approve(pilot, "#approve")
        assert app.stage == 2
        assert files.read_text("seeds.csv") == "seed\nalpha\n"

    # resume at 2 (seeds approved, no candidates); stage 2: search
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 2 and isinstance(app.screen, SearchScreen)
        app.screen.embedder = StubEmbedder()
        await pilot.press("r")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # the 10 low items are below the floor
        assert panel_title(app.screen.query_one("#bands-panel"))[1] == "110 candidates"

    # resume at 3; stage 3: taxonomy and prompt
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 3 and isinstance(app.screen, TaxonomyScreen)
        await chat(app, pilot, taxonomy_stream, "one label, single")
        await approve(pilot)
        assert app.stage == 4
        assert files.read_config().target_metric == "accuracy"

    # resume at 4 with part of the dev set labelled; stage 4: gold dev set
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 4 and isinstance(app.screen, GoldScreen)
        await label_all(app, pilot, 20)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 4
        assert app.screen.index == 20  # type: ignore[unresolved-attribute]  # first unlabelled item
        await label_all(app, pilot, 30)
        assert CALLS == []  # labelling never calls the classifier
        await approve(pilot)
        assert app.stage == 5
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert len(CALLS) == 50  # the first Tuning run classifies the whole dev set

    # resume at 5; stage 5: tuning (everything agrees, so the target is met)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 5
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert app.stage == 6 and files.read_state().dev_done

    # resume at 6; stage 6: test set labelling, then the single held-out run
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 6 and isinstance(app.screen, GoldScreen)
        await label_all(app, pilot, 50)
        await approve(pilot)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.stage == 6 and not isinstance(app.screen, GoldScreen)
        await pilot.press("f2")
        await pilot.pause()
        assert app.stage == 7 and files.read_state().test_done
    gold = files.read_gold()
    assert [sum(r.split == s for r in gold) for s in ("dev", "test")] == [50, 50]
    assert not {r.id for r in gold if r.split == "dev"} & {
        r.id for r in gold if r.split == "test"
    }

    # resume at 7; stage 7: threshold
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 7
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.screen.query_one("#bands", DataTable).focus()
        await pilot.press("down", "down", "enter")  # band 2 = 0.650
        await pilot.press("f2")
        await pilot.pause()
        assert app.stage == 8
    data = json.loads(files.read_text("threshold.json") or "")
    assert data["threshold"] == CUTOFF and data["n_candidates"] == 70

    # resume at 8; stage 8: full run
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 8
        await pilot.click("#run-button")  # Start
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
    results = files.read_jsonl("results.jsonl")
    assert len(results) == 70 and len({r["id"] for r in results}) == 70
    for r in results:
        assert r["max_similarity"] >= CUTOFF and "error" not in r
        want = ["a"] if int(r["text"].split()[-1]) % 2 == 0 else ["off_topic"]
        assert r["labels"] == want

    # resume at 9; stage 9: browse shows every result
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 9
        assert app.screen.query_one("#table", DataTable).row_count == 70

    # the stand-in model has no known price, so cost is unknown, never $0
    assert cost.total()[1]


def stage_counts(screen) -> dict[int, tuple[int, int]]:
    """(live, cached) per stage from the Redo plan table."""
    out = {}
    for key in screen.query_one("#plan", DataTable).rows:
        row = [str(c) for c in screen.query_one("#plan", DataTable).get_row(key)]
        stage = row[0].split()[1] if row[0][0] in "▸↻◐✓" else None
        if stage:
            out[int(stage)] = (int(row[2]), int(row[3]))
    return out


async def test_prompt_edit_after_a_full_run_plan_matches_the_rerun_and_undo_restores_current():
    from hunches import history
    from hunches.screens.redo_plan import RedoPlanScreen

    await run_all_stages()
    assert all(kind == "current" for kind, _ in files.stage_status().values())
    old_prompt = files.read_text("prompt.md")
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 9
        CALLS.clear()

        # a new prompt: stages 5-8 are stale, 1-4 stay current, nothing was called or removed
        history.save("prompt", "Label the item, carefully.", "user", "Prompt: edited")
        status = files.stage_status()
        assert [status[n][0] for n in range(1, 5)] == ["current"] * 4
        assert [status[n] for n in range(5, 9)] == [("stale", "prompt changed")] * 4
        assert len(files.read_jsonl("results.jsonl")) == 70  # stays until overwritten

        # undo puts the old prompt back and everything is current again, with no model call;
        # redo makes it stale again
        history.undo("prompt")
        assert files.read_text("prompt.md") == old_prompt
        assert all(k == "current" for k, _ in files.stage_status().values())
        history.redo("prompt")
        assert files.stage_status()[5] == ("stale", "prompt changed")
        assert CALLS == []

        # the plan: every item text is new, except those that several stages share (the cache key is
        # the text), which the later stage finds already cached
        dev = {r.text for r in files.read_gold() if r.split == "dev"}
        test = {r.text for r in files.read_gold() if r.split == "test"}
        by_id = {c["id"]: c["text"] for c in files.read_jsonl("candidates.jsonl")}
        sample = {
            by_id[i]
            for band in json.loads(files.read_text("threshold_sample.json") or "")[
                "ids"
            ]
            for i in band
        }
        full = {
            c["text"]
            for c in files.read_jsonl("candidates.jsonl")
            if c["max_similarity"] >= CUTOFF
        }
        assert (len(dev), len(test), len(full)) == (50, 50, 70)
        live7 = len(sample - dev - test)
        live8 = len(full - dev - test - sample)
        want = {
            5: (50, 0),
            6: (50, 0),
            7: (live7, len(sample) - live7),
            8: (live8, 70 - live8),
        }
        await pilot.press("f9")
        await pilot.pause()
        assert isinstance(app.screen, RedoPlanScreen)
        assert stage_counts(app.screen) == want
        assert CALLS == []  # the plan classifies nothing
        await pilot.press("escape")
        await pilot.pause()

        # redoing each stage calls the model exactly as often as the plan said
        got = {}
        app.goto_stage(5)
        await app.workers.wait_for_complete()
        await pilot.pause()
        got[5] = len(CALLS)
        assert files.stage_status()[5][0] == "stale"  # recomputed, not yet approved
        await pilot.press("f2")
        await pilot.pause()
        assert app.stage == 6 and files.stage_status()[5][0] == "current"
        CALLS.clear()
        assert app.stage == 6
        await pilot.press("r")  # the stale result is only re-run on request
        await app.workers.wait_for_complete()
        await pilot.pause()
        got[6] = len(CALLS)
        CALLS.clear()
        await pilot.press("f2")
        await pilot.pause()
        app.goto_stage(7)
        await app.workers.wait_for_complete()
        await pilot.pause()
        got[7] = len(CALLS)
        CALLS.clear()
        app.screen.query_one("#bands", DataTable).focus()
        await pilot.press("down", "down", "enter", "f2")
        await pilot.pause()
        assert app.stage == 8
        await pilot.click("#run-button")
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        got[8] = len(CALLS)
        assert got == {n: want[n][0] for n in want}
        assert all(kind == "current" for kind, _ in files.stage_status().values())
        results = files.read_jsonl("results.jsonl")
        assert len(results) == 70

        # the re-run was cache-correct: nothing is left to redo, and a second pass calls nothing
        assert classifier.redo_plan() == []

        # going back to the old prompt marks 5-8 stale again, but every call is a cache hit
        CALLS.clear()
        history.undo("prompt")
        assert files.read_text("prompt.md") == old_prompt
        plan = classifier.redo_plan()
        assert [r["stage"] for r in plan] == [5, 6, 7, 8]
        assert [r["live_calls"] for r in plan] == [0, 0, 0, 0]
        assert [r["cached_calls"] for r in plan] == [50, 50, len(sample), 70]
        assert CALLS == []


async def test_first_run_new_project_then_open_another_from_projects(
    tmp_path, monkeypatch
):
    import os

    from textual.widgets import Button

    from hunches.screens.system import SystemSettingsScreen

    system._path().unlink()  # undo the fixture: a true first run
    other = tmp_path / "other"
    shutil.copytree(tmp_path / "corpus", other / "corpus")
    (other / ".hunches").mkdir()
    files.write_config(
        files.Config(
            assistant_model="a",
            classifier_model="c",
            corpus_dir="corpus",
            embedding_model="m",
        ),
        other,
    )
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SystemSettingsScreen)
        app.screen.query_one("#save", Button).press()
        await pilot.pause()
        assert app.stage == 0 and isinstance(app.screen, ProjectsScreen)
        await pilot.press("n")
        await pilot.pause()
        app.screen.query_one("#corpus", Input).value = "corpus"
        await pilot.pause()
        await pilot.click("#create")
        await pilot.pause()
        assert app.stage == 1 and Path.cwd() == tmp_path
        system.add_project(other)
        await pilot.press("f4")
        await pilot.pause()
        table = app.screen.query_one(DataTable)
        table.move_cursor(row=[r.value for r in table.rows].index(str(other)))
        await pilot.press("enter")
        await pilot.pause()
        assert app.stage == 1 and isinstance(app.screen, BriefScreen)
        assert os.getcwd() == str(other)


async def reach_stage_4(app, pilot):
    """New project, brief, seeds, search, taxonomy and prompt, in one session: ends on the dev gold screen."""
    await pilot.pause()
    await pilot.press("n")
    await pilot.pause()
    app.screen.query_one("#corpus", Input).value = "corpus"
    await pilot.pause()
    await pilot.click("#create")
    await pilot.pause()
    await chat(app, pilot, brief_stream, "Find even items")
    await approve(pilot, "#approve")
    app.screen.embedder = StubEmbedder()
    await pilot.click("#run")  # the first search asks nothing
    await app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.press("n")
    await pilot.pause()
    assert isinstance(app.screen, TaxonomyScreen)
    await chat(app, pilot, taxonomy_stream, "one label, single")
    await approve(pilot, "#approve")
    assert app.stage == 4 and isinstance(app.screen, GoldScreen)


async def test_pool_short_blocks_labelling_until_seeds_are_added():
    write_corpus(
        Path("corpus"), [0.7] * 30 + [0.3] * 10
    )  # 30 candidates, the dev set needs 50
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await reach_stage_4(app, pilot)
        screen = app.screen
        assert isinstance(screen, GoldScreen) and screen.pool_short
        assert (
            screen.pool_short["found"] == 30 and not screen.query_one("#main").display
        )
        await pilot.press("1", "enter")
        await pilot.pause()
        assert all(not r.labels for r in files.read_gold())  # nothing can be labelled
        assert CALLS == []
        await pilot.click("#add-seeds")  # the way out: more seeds
        await pilot.pause()
        assert app.stage == 1 and isinstance(app.screen, BriefScreen)


async def test_taxonomy_version_round_trip():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await reach_stage_4(app, pilot)
        await label_all(app, pilot, 12)
        dev = {r.id for r in files.read_gold()}
        assert sum(bool(r.labels) for r in files.read_gold()) == 12

        # change the label names after gold rows exist: confirm, and the labelling restarts
        await pilot.press("p")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TaxonomyScreen)
        await pilot.click("#edit-labels", offset=(2, 0))
        await pilot.pause()
        screen.query(".label-name").first(Input).value = "z"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.click("#yes")
        await pilot.pause()
        assert [v["version"] for v in files.list_versions()] == [1]
        assert [lb.name for lb in files.read_taxonomy().labels] == ["z"]
        gold = files.read_gold()
        assert {r.id for r in gold} == dev and all(not r.labels for r in gold)
        archived = files.root() / "versions" / "1"
        assert "name: a" in (archived / "taxonomy.yaml").read_text()
        assert (
            sum(
                bool(json.loads(x)["labels"])
                for x in (archived / "gold.jsonl").read_text().splitlines()
            )
            == 12
        )

        # relabel the same items under the new labels
        await approve(pilot)
        assert app.stage == 4 and isinstance(app.screen, GoldScreen)
        await label_all(app, pilot, 50)
        assert all(r.labels for r in files.read_gold())
        assert CALLS == []

        # restore the earlier version: the current state is archived first
        await pilot.press("p")
        await pilot.pause()
        await pilot.click("#versions", offset=(2, 0))
        await pilot.pause()
        assert isinstance(app.screen, VersionsScreen)
        await pilot.click("#restore-1")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.click("#yes")
        await pilot.pause()
        assert [lb.name for lb in files.read_taxonomy().labels] == ["a"]
        assert [v["version"] for v in files.list_versions()] == [1, 2]
        assert (
            "name: z" in (files.root() / "versions" / "2" / "taxonomy.yaml").read_text()
        )
        assert sum(bool(r.labels) for r in files.read_gold()) == 12
