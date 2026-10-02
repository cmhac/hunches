"""One scripted run through all nine stages, offline, restarting the app at every boundary."""

import json
import math

import numpy as np
import pytest
from pydantic_ai import Agent, Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.usage import RequestUsage
from textual.widgets import DataTable, Input

from hunches import classifier, cost, files
from hunches.app import HunchesApp
from hunches.screens.brief import BriefScreen
from hunches.screens.gold import GoldScreen
from hunches.screens.search import SearchScreen
from hunches.screens.taxonomy import TaxonomyScreen

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


def classify_fn(messages, info: AgentInfo):
    """Even item numbers are "a", odd ones off_topic; the same rule the test uses as gold."""
    request = messages[0]
    assert isinstance(request, ModelRequest)
    text = str(next(p.content for p in request.parts if p.part_kind == "user-prompt"))
    answer = ["a"] if int(text.split()[-1]) % 2 == 0 else ["off_topic"]
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, {"response": answer})]
    )


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    vectors = [[s, math.sqrt(1 - s * s)] for s in SIMS]
    np.save(corpus / "vectors.npy", np.array(vectors, np.float32))
    items = [{"id": f"i{n}", "text": f"item {n}"} for n in range(len(SIMS))]
    (corpus / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in items))
    (corpus / "meta.json").write_text(json.dumps({"embedding_model": "m"}))
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


async def approve(pilot, key="f2"):
    await pilot.press(key)
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
    # setup, then stage 1: brief and seeds
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 0
        screen = app.screen
        screen.query_one("#corpus_dir", Input).value = "corpus"
        screen.query_one("#embedding_model", Input).value = "m"
        await pilot.click("#save")
        await pilot.pause()
        assert app.stage == 1 and isinstance(app.screen, BriefScreen)
        await chat(app, pilot, brief_stream, "Find even items")
        assert files.read_text("brief.md") == "Find even items\n"
        await approve(pilot)
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
        total = app.screen.query_one("#bands", DataTable).get_row_at(7)
        assert [str(c) for c in total] == [
            "Total",
            "110",
            "",
        ]  # the 10 low items are below the floor

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
        await approve(pilot)
        assert app.stage == 5

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
        app.screen.query_one("#cutoff", Input).value = str(CUTOFF)
        app.screen.action_save()  # type: ignore[unresolved-attribute]
        await pilot.pause()
        assert app.stage == 8
    data = json.loads(files.read_text("threshold.json") or "")
    assert data["threshold"] == CUTOFF and data["n_candidates"] == 70

    # resume at 8; stage 8: full run
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 8
        await pilot.press("s")
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
