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
        assert panel.border_title == "dev set"
        assert panel.border_subtitle == "target accuracy ≥ 0.90 · m metric · +/- score"
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
        assert screen.query_one("#dis-panel").border_title == "disagreements · 4"
        assert screen.query_one("#text-panel").border_title == "text"
        dis = screen.query_one("#dis", DataTable)
        assert [str(c) for c in dis.get_row_at(0)] == ["item 1", "■ b", "■ a"]
        assert "item 1" in str(screen.query_one("#detail", Static).render())
        note = screen.query_one("#note")
        assert str(note.render()).startswith("Dev run finished, cost")
        assert note.has_class("note")
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
            ("Asking the assistant...", "warn"),
            ("No disagreements to learn from.", "warn"),
        ]:
            screen.run_note, screen.note = "", note
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
        assert notice.has_class("warn")


async def test_proposal_modal_layout_and_diff_lines():
    from hunches.screens.tune import ProposalScreen

    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.push_screen(ProposalScreen("one\ntwo", "one\nthree"))
        await pilot.pause()
        modal = app.screen
        box = modal.query_one("Vertical")
        assert box.border_title == "Proposed prompt change"
        assert box.outer_size.width == 96 and box.outer_size.height == 28
        assert (
            modal.query_one("#diff-panel").border_title == "diff · current → proposed"
        )
        assert modal.query_one("#proposal-panel").border_title == "proposal (editable)"
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
