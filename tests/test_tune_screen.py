import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.widgets import DataTable, Static, TextArea

from hunches import files
from hunches.app import HunchesApp
from hunches.screens.tune import TuneScreen

calls: list[str] = []


def classifier(messages, info: AgentInfo):
    """Says "a" always; says the right label (text "item N", N odd = b) once the prompt contains BETTER."""
    request = messages[0]
    assert isinstance(request, ModelRequest)
    text = next(p.content for p in request.parts if p.part_kind == "user-prompt")
    calls.append(str(text))
    better = any(
        "BETTER" in str(p.content)
        for p in request.parts
        if p.part_kind == "system-prompt"
    )
    answer = ["b"] if better and int(str(text).split()[1]) % 2 else ["a"]
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, {"response": answer})]
    )


def proposer(messages, info: AgentInfo):
    return ModelResponse(parts=[TextPart("Classify. BETTER")])


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls.clear()
    files.write_config(files.Config(corpus_dir="c", embedding_model="m"))
    files.write_text("seeds.csv", "seed\nx\n")
    files.write_state(files.State(seeds_approved=True, taxonomy_approved=True))
    files.write_taxonomy(
        files.Taxonomy(
            mode="single", labels=[files.Label(name="a"), files.Label(name="b")]
        )
    )
    files.write_text("prompt.md", "Classify.")
    # 8 items: even -> gold a, odd -> gold b
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": str(i), "text": f"item {i}", "max_similarity": 0.7, "best_seed": "x"}
            for i in range(8)
        ],
    )
    files.write_gold(
        [
            files.GoldRow(
                id=str(i), text=f"item {i}", labels=["b" if i % 2 else "a"], split="dev"
            )
            for i in range(8)
        ]
    )


def metrics_text(screen):
    return str(screen.query_one("#metrics", Static).render())


async def settle(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_disagreements_listed_then_proposal_improves_and_cache_holds():
    files.write_state(files.State(seeds_approved=True, taxonomy_approved=True))
    # 50 labelled dev rows are needed to land on stage 5 by resume, so go straight to the screen
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(5)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TuneScreen)
        screen.model = FunctionModel(classifier)  # ty: ignore[invalid-assignment]
        screen.agent.model = FunctionModel(proposer)
        screen.rerun()
        await settle(app, pilot)
        table = screen.query_one("#dis", DataTable)
        assert table.row_count == 4  # the four odd items are wrong
        assert [table.get_row_at(i)[0] for i in range(4)] == [
            f"item {i}" for i in (1, 3, 5, 7)
        ]
        assert "accuracy = 0.500" in metrics_text(screen) and "FAIL" in metrics_text(
            screen
        )
        assert len(calls) == 8

        screen.rerun()  # unchanged prompt: all cache hits
        await settle(app, pilot)
        assert len(calls) == 8

        await pilot.press("e")
        await settle(app, pilot)
        assert "+Classify. BETTER" in str(
            screen.app.screen.query_one("#diff", Static).render()
        )
        screen.app.screen.query_one("#proposal", TextArea).text = "Classify. BETTER!"
        await pilot.pause()
        await pilot.click("#accept")
        await settle(app, pilot)
        assert files.read_text("prompt.md") == "Classify. BETTER!"
        assert len(calls) == 16  # new prompt: every item re-run
        assert screen.query_one("#dis", DataTable).row_count == 0
        assert "accuracy = 1.000" in metrics_text(screen) and "PASS" in metrics_text(
            screen
        )
        assert "0.500 -> 0.500 -> 1.000" in metrics_text(screen)

        await pilot.press("f2")
        await pilot.pause()
        assert files.read_state().dev_done
        assert app.stage == 6


async def test_rejected_proposal_changes_nothing_and_target_metric_flips_pass_fail():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(5)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TuneScreen)
        screen.model = FunctionModel(classifier)  # ty: ignore[invalid-assignment]
        screen.agent.model = FunctionModel(proposer)
        screen.rerun()
        await settle(app, pilot)
        await pilot.press("e")
        await settle(app, pilot)
        await pilot.click("#reject")
        await settle(app, pilot)
        assert files.read_text("prompt.md") == "Classify."
        assert len(calls) == 8

        # all predictions "a": accuracy 0.5, but micro-F1 is also 0.5 and macro-F1 is 0.333
        screen.config.target_score = 0.4
        await pilot.press("m")  # accuracy -> macro_f1
        assert files.read_config().target_metric == "macro_f1"
        assert "FAIL" in metrics_text(screen)  # 0.333 < 0.4
        await pilot.press("m")  # micro_f1 = 0.5
        assert "PASS" in metrics_text(screen)
        await pilot.press("minus")
        assert files.read_config().target_score == 0.39

        screen.config.target_score = 0.9  # unmet: Done asks first
        await pilot.press("f2")
        await pilot.pause()
        assert not files.read_state().dev_done
        await pilot.click("#yes")
        await pilot.pause()
        assert files.read_state().dev_done and app.stage == 6
