import asyncio

import pytest
from conftest import panel_title
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.containers import VerticalScroll
from textual.widgets import Button, DataTable, Select, Static, TextArea

from hunches import files
from hunches.app import HunchesApp
from hunches.screens import tune
from hunches.screens.progress import RunIndicator
from hunches.screens.tune import PromptEditScreen, TuneScreen

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
        parts=[
            ToolCallPart(
                info.output_tools[0].name, {"reasoning": "r", "labels": answer}
            )
        ]
    )


def proposer(messages, info: AgentInfo):
    return ModelResponse(parts=[TextPart("Classify. BETTER")])


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls.clear()
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="none:unset",  # fails at once on mount
            corpus_dir="c",
            embedding_model="m",
        )
    )
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
    return "\n".join(
        str(screen.query_one(i, Static).render()) for i in ("#summary", "#trend")
    )


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
        assert [str(table.get_row_at(i)[0]) for i in range(4)] == [
            f"item {i}" for i in (1, 3, 5, 7)
        ]
        assert "accuracy 0.500" in metrics_text(screen) and "FAIL" in metrics_text(
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
        assert "accuracy 1.000" in metrics_text(screen) and "PASS" in metrics_text(
            screen
        )
        assert "trend 0.500 → 0.500 → 1.000" in metrics_text(screen)

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


async def test_redesigned_panels_summary_and_tables():
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.goto_stage(5)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TuneScreen)
        screen.model = FunctionModel(classifier)  # ty: ignore[invalid-assignment]
        screen.rerun()
        await settle(app, pilot)
        panel = screen.query_one("#metrics-panel")
        assert panel_title(panel)[0] == "dev set"
        assert panel_title(panel)[1] == "target accuracy ≥ 0.90"
        # the metric equal to the target (exact-match) is left out
        summary = " ".join(metrics_text(screen).split())
        assert summary.startswith(
            "accuracy 0.500 FAIL n=8 macro-F1 0.333 micro-F1 0.500"
        )
        assert "exact-match" not in summary and "trend" not in summary
        per_label = screen.query_one("#per-label", DataTable)
        assert [str(c) for c in per_label.get_row(per_label.ordered_rows[0].key)] == [
            "■ a",
            "0.50",
            "1.00",
            "0.67",
            "4",
        ]
        assert panel_title(screen.query_one("#dis-panel"))[0] == "disagreements · 4"
        assert (
            panel_title(screen.query_one("#text-panel"))[0]
            == "text · classifier reasoning"
        )
        dis = screen.query_one("#dis", DataTable)
        assert [str(c) for c in dis.get_row_at(0)] == ["item 1", "■ b", "■ a"]
        assert "item 1" in str(screen.query_one("#detail", Static).render())
        note = screen.query_one("#note")
        assert str(note.render()) == "" and not note.display
        # another target metric: its own value leads and exact-match comes back
        await pilot.press("m")
        summary = " ".join(metrics_text(screen).split())
        assert summary.startswith(
            "macro_f1 0.333 FAIL n=8 exact-match 0.500 micro-F1 0.500"
        )


async def test_failed_item_detail_and_note_tones():
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.goto_stage(5)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TuneScreen)
        screen.model = FunctionModel(classifier)  # ty: ignore[invalid-assignment]
        screen.rerun()
        await settle(app, pilot)
        screen.errors = {1: "boom"}
        screen.show()
        assert "Model failed: boom" in str(screen.query_one("#detail", Static).render())
        assert str(screen.query_one("#dis", DataTable).get_row_at(0)[2]) == "failed"
        for note, tone in [
            ("Dev run failed: x", "error"),
            ("Proposal failed: x", "error"),
            ("Proposing a prompt edit...", "note"),
            ("No disagreements to learn from.", "warn"),
        ]:
            screen.note = note
            screen.show()
            assert screen.query_one("#note").has_class(tone), note


async def test_not_ready_notice():
    files.write_text("taxonomy.yaml", "")  # exists; remove prompt instead
    (files.root() / "prompt.md").unlink()
    (files.root() / "taxonomy.yaml").unlink()
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(5)
        await pilot.pause()
        notice = app.screen.query_one("#not-ready")
        assert str(notice.render()) == "Finish stage 3 (taxonomy and prompt) first."
        assert notice.has_class("not-ready")


async def test_proposal_modal_layout_and_diff_lines():
    from hunches.screens.tune import ProposalScreen

    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.push_screen(ProposalScreen("one\ntwo", "one\nthree"))
        await pilot.pause()
        modal = app.screen
        box = modal.query_one("Vertical")
        assert panel_title(box)[0] == "Proposed prompt change"
        assert box.outer_size.width == 96 and box.outer_size.height == 28
        assert (
            panel_title(modal.query_one("#diff-panel"))[0]
            == "diff · current → proposed"
        )
        assert (
            panel_title(modal.query_one("#proposal-panel"))[0] == "proposal (editable)"
        )
        assert [b.id for b in modal.query("Button")] == ["reject", "accept"]
        assert app.focused is not None and app.focused.id == "accept"
        diff = str(modal.query_one("#diff", Static).render())
        assert "-two" in diff and "+three" in diff and "@@" in diff


async def test_disagreement_columns_fit_without_horizontal_scroll():
    files.write_gold(
        [
            files.GoldRow(
                id=str(i),
                text=f"item {i} " + "long text " * 20,
                labels=["b" if i % 2 else "a"],
                split="dev",
            )
            for i in range(8)
        ]
    )
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(5)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TuneScreen)
        screen.model = FunctionModel(classifier)  # ty: ignore[invalid-assignment]
        screen.rerun()
        await settle(app, pilot)
        await pilot.pause()
        dis = screen.query_one("#dis", DataTable)
        assert dis.row_count == 4
        assert (
            dis.virtual_size.width <= dis.size.width
        )  # Gold and Predicted are visible


async def start(app, pilot):
    await pilot.pause()
    app.goto_stage(5)
    await pilot.pause()
    screen = app.screen
    assert isinstance(screen, TuneScreen)
    screen.model = FunctionModel(classifier)
    return screen


async def wait_for(pilot, condition):
    for _ in range(200):
        await pilot.pause()
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


async def test_controls_mirror_actions_and_enabled_states():
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await start(app, pilot)
        screen.agent.model = FunctionModel(proposer)
        await settle(app, pilot)  # the mount run failed: no result yet
        assert screen.metrics is None
        for id_ in ("propose", "edit-prompt", "done"):
            assert screen.query_one(f"#{id_}", Button).disabled, id_
        labels = {
            b.id: str(b.label) for b in screen.query("#controls Button").results(Button)
        }
        assert labels == {
            "score-down": "−",
            "score-up": "+",
            "propose": "Propose edit  e",
            "edit-prompt": "Edit prompt  o",
            "done": "Done  F2",
        }
        assert str(screen.query_one("#score", Static).render()) == "0.90"

        screen.rerun()
        await settle(app, pilot)
        assert not screen.query_one("#propose", Button).disabled
        assert not screen.query_one("#edit-prompt", Button).disabled
        done = screen.query_one("#done", Button)
        assert not done.disabled and done.variant == "default"  # 0.5 < 0.9

        await pilot.click("#score-down")
        await pilot.pause()
        assert files.read_config().target_score == 0.89
        assert str(screen.query_one("#score", Static).render()) == "0.89"
        await pilot.click("#score-up")
        await pilot.pause()
        await pilot.click("#score-up")
        await pilot.pause()
        assert files.read_config().target_score == 0.91
        screen.config.target_score = 1.0
        screen.show()
        await pilot.pause()
        await pilot.click("#score-up")
        await pilot.pause()
        assert files.read_config().target_score == 1.0
        screen.config.target_score = 0.0
        screen.show()
        await pilot.pause()
        await pilot.click("#score-down")
        await pilot.pause()
        assert files.read_config().target_score == 0.0

        screen.config.target_score = 0.5  # accuracy 0.5 meets it
        screen.show()
        assert screen.query_one("#done", Button).variant == "success"

        screen.query_one("#target", Select).value = "macro_f1"
        await pilot.pause()
        assert files.read_config().target_metric == "macro_f1"
        await pilot.press("m")
        assert files.read_config().target_metric == "micro_f1"
        assert screen.query_one("#target", Select).value == "micro_f1"

        await pilot.click("#propose")
        await settle(app, pilot)
        assert isinstance(app.screen, tune.ProposalScreen)


async def test_propose_disabled_without_disagreements():
    files.write_gold(
        [
            files.GoldRow(id=str(i), text=f"item {i}", labels=["a"], split="dev")
            for i in range(8)
        ]
    )
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await start(app, pilot)
        screen.rerun()
        await settle(app, pilot)
        assert screen.metrics is not None and not screen.metrics.disagreements
        assert screen.query_one("#propose", Button).disabled
        assert not screen.query_one("#done", Button).disabled


async def test_edit_prompt_saves_and_reruns_only_when_changed():
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await start(app, pilot)
        await settle(app, pilot)
        await pilot.press("o")  # no result yet: nothing opens
        await pilot.pause()
        assert app.screen is screen
        screen.rerun()
        await settle(app, pilot)
        assert len(calls) == 8

        await pilot.press("o")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, PromptEditScreen)
        assert modal.query_one("#prompt", TextArea).text == "Classify."
        save = modal.query_one("#save", Button)
        assert str(save.label) == "Save and re-run  F2" and save.disabled
        assert str(modal.query_one("#cancel", Button).label) == "Cancel  Esc"
        assert modal.query_one("#prompt", TextArea).show_line_numbers
        modal.query_one("#prompt", TextArea).text = "Classify. BETTER"
        await pilot.pause()
        assert not save.disabled
        modal.query_one("#prompt", TextArea).text = "Classify."
        await pilot.pause()
        assert save.disabled  # back to the file's text
        await pilot.press("escape")
        await settle(app, pilot)
        assert app.screen is screen
        assert files.read_text("prompt.md") == "Classify." and len(calls) == 8

        await pilot.click("#edit-prompt")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, PromptEditScreen)
        modal.query_one("#prompt", TextArea).text = "Classify. BETTER"
        await pilot.pause()
        await pilot.click("#save")
        await settle(app, pilot)
        assert files.read_text("prompt.md") == "Classify. BETTER"
        assert screen.prompt == "Classify. BETTER"
        assert len(calls) == 16  # the dev set classified again
        assert screen.query_one("#dis", DataTable).row_count == 0
        assert screen.history == [0.5, 1.0]


async def test_edit_prompt_cancel_button_writes_nothing():
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await start(app, pilot)
        screen.rerun()
        await settle(app, pilot)
        await pilot.press("o")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, PromptEditScreen)
        modal.query_one("#prompt", TextArea).text = "other"
        await pilot.pause()
        await pilot.click("#cancel")
        await settle(app, pilot)
        assert files.read_text("prompt.md") == "Classify." and len(calls) == 8


async def test_run_indicator_hides_panels_stop_resume(monkeypatch):
    real = tune.classify_many
    gate = asyncio.Event()
    batches = []

    async def slow(texts, prompt, taxonomy, model):
        batches.append(len(texts))
        n = 0
        async for i, p in real(texts, prompt, taxonomy, FunctionModel(classifier)):
            yield i, p
            n += 1
            if n == 4 and len(batches) == 1:
                await gate.wait()

    monkeypatch.setattr(tune, "classify_many", slow)
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(5)
        screen = app.screen
        assert isinstance(screen, TuneScreen)
        await wait_for(pilot, lambda: len(calls) >= 4)
        ind = screen.query_one(RunIndicator)
        assert ind.display and screen.running
        for id_ in ("metrics-panel", "body", "controls"):
            assert not screen.query_one(f"#{id_}").display, id_
        assert str(ind.query_one("#run-title", Static).content) == "Running the dev set"
        counts = str(ind.query_one("#run-counts", Static).content)
        assert counts.startswith("4 of 8") and "left" in counts
        assert counts.endswith("classifier none:unset")
        assert str(ind.query_one("#run-button", Button).label) == "Stop  x"
        await pilot.press("x")
        await wait_for(pilot, lambda: screen.stopped)
        assert ind.display and not screen.query_one("#body").display
        assert str(ind.query_one("#run-button", Button).label) == "Resume  s"
        await pilot.click("#run-button")
        await wait_for(pilot, lambda: not screen.running and not screen.stopped)
        assert batches == [8, 8]
        assert not ind.display
        for id_ in ("metrics-panel", "body", "controls"):
            assert screen.query_one(f"#{id_}").display, id_
        assert screen.metrics is not None


async def test_failed_run_shows_panels_and_note():
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.goto_stage(5)
        await settle(app, pilot)
        screen = app.screen
        assert screen.query_one("#body").display
        assert not screen.query_one(RunIndicator).display
        note = screen.query_one("#note", Static)
        assert note.display and str(note.render()).startswith("Dev run failed:")
        assert note.has_class("error")


async def test_reasoning_in_detail_panel_and_hidden_for_failed_item():
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await start(app, pilot)
        screen.rerun()
        await settle(app, pilot)
        assert screen.reasoning[1] == "r"
        assert isinstance(screen.query_one("#detail-scroll"), VerticalScroll)
        head = screen.query_one("#reasoning-head", Static)
        assert head.display and str(head.render()) == "classifier reasoning"
        assert str(screen.query_one("#reasoning", Static).render()) == "r"
        assert "item 1" in str(screen.query_one("#detail", Static).render())
        screen.errors = {1: "boom"}
        screen.show()
        assert not head.display and not screen.query_one("#reasoning").display
        assert "Model failed: boom" in str(screen.query_one("#detail", Static).render())
        screen.errors, screen.reasoning = {}, {}  # an old result: no reasoning
        screen.show()
        assert not head.display


@pytest.mark.parametrize(("width", "stacked"), [(119, False), (120, True)])
async def test_layout_side_by_side_under_120_stacked_from_120(width, stacked):
    app = HunchesApp()
    async with app.run_test(size=(width, 40)) as pilot:
        screen = await start(app, pilot)
        screen.rerun()
        await settle(app, pilot)
        await pilot.pause()
        dis, text = screen.query_one("#dis-panel"), screen.query_one("#text-panel")
        assert screen.query_one("#body").has_class("-stacked") is stacked
        if stacked:
            assert text.region.y >= dis.region.y + dis.region.height
            assert dis.region.height > text.region.height  # 5:4
        else:
            assert text.region.y == dis.region.y
            assert text.region.x >= dis.region.x + dis.region.width
