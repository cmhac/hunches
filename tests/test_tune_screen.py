import asyncio
import json
from types import SimpleNamespace

import pytest
from conftest import panel_title
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from textual.containers import VerticalScroll
from textual.widgets import Button, DataTable, Select, Static, TextArea

from hunches import files, history, metrics
from hunches.app import ChatLine, ChatPanel, ConfirmScreen, FoldLine, HunchesApp
from hunches.screens import tune
from hunches.screens.progress import RunIndicator
from hunches.screens.tune import (
    PromptEditScreen,
    ProposalCard,
    ProposalScreen,
    TuneScreen,
)

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


CANNED = "Propose a prompt edit based on the current disagreements."


async def canned_reply(messages, info: AgentInfo):
    yield "Noted."


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


async def test_disagreements_listed_then_accepted_prompt_improves_and_cache_holds():
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

        screen.accepted("Classify. BETTER!")
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
        (entry,) = [e for e in history.entries() if e["kind"] == "approval"]
        assert (entry["stage"], entry["flag"], entry["summary"]) == (
            5,
            "dev_done",
            "Approved: Tuning loop (dev accuracy 1.000)",
        )
        assert app.stage == 6


async def test_target_metric_flips_pass_fail():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(5)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TuneScreen)
        screen.model = FunctionModel(classifier)  # ty: ignore[invalid-assignment]
        screen.rerun()
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
        (entry,) = [e for e in history.entries() if e["kind"] == "approval"]
        assert (
            entry["summary"]
            == "Approved: Tuning loop (dev micro_f1 0.500, below target)"
        )


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
        await pilot.pause(0.3)  # a Button ignores clicks while -active (0.2 s)
        await pilot.click("#score-up")
        await pilot.pause(0.3)
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

        screen.agent.model = FunctionModel(stream_function=canned_reply)
        await pilot.click("#propose")
        await settle(app, pilot)
        assert app.screen is screen  # no modal: the button talks to the assistant
        assert CANNED in [ln.text for ln in screen.query(ChatLine)]


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


# ---- the assistant chat (task 16) ---------------------------------------------------


@pytest.fixture
def assistant(monkeypatch):
    """Every TuneScreen gets FunctionModels for the assistant and the classifier: no real call.

    `log.prompts` holds each user prompt the assistant received, `log.instructions` the per-run
    instructions. A user prompt that is a key of `log.tools` makes the assistant call that tool.
    """
    log = SimpleNamespace(
        prompts=[], instructions=[], returns=[], tools={}, fail=False, gate=None
    )

    async def stream(messages, info: AgentInfo):
        log.instructions.append(info.instructions)
        parts = messages[-1].parts
        returns = [p for p in parts if p.part_kind == "tool-return"]
        if returns:
            log.returns.append(str(returns[0].content))
            yield "Done."
            return
        prompt = [str(p.content) for p in parts if p.part_kind == "user-prompt"][-1]
        log.prompts.append(prompt)
        if log.gate:
            await log.gate.wait()
        if log.fail:
            raise RuntimeError("boom")
        if prompt in log.tools:
            name, args = log.tools[prompt]
            yield {0: DeltaToolCall(name=name, json_args=json.dumps(args))}
        else:
            yield "Reply."

    original = TuneScreen.__init__

    def init(self):
        original(self)
        self.agent.model = FunctionModel(stream_function=stream)
        self.model = FunctionModel(classifier)

    monkeypatch.setattr(TuneScreen, "__init__", init)
    return log


async def quiesce(app, pilot):
    """Wait until no worker is left, including the ones a finished worker started."""
    for _ in range(4):
        await pilot.pause()
        await app.workers.wait_for_complete()
    await pilot.pause()


def history_requests(kind):
    return [
        m
        for m in files.load_chat("tuning")
        if isinstance(m, ModelRequest) and (m.metadata or {}).get("hunches") == kind
    ]


def tool_returns(name):
    return [
        str(p.content)
        for m in files.load_chat("tuning")
        if isinstance(m, ModelRequest)
        for p in m.parts
        if p.part_kind == "tool-return" and p.tool_name == name
    ]


def proposals():
    return json.loads(files.read_text("chat/tuning.proposals.json") or "[]")


def ask_for_proposal(assistant, prompt="Classify. BETTER"):
    assistant.tools[CANNED] = (
        "propose_prompt",
        {"prompt": prompt, "rationale": "because"},
    )


async def open_proposal(app, pilot):
    await pilot.click("#propose")
    await wait_for(pilot, lambda: isinstance(app.screen, ProposalScreen))
    return app.screen


async def test_first_run_sends_one_tagged_context_then_nothing_until_something_changed(
    assistant,
):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        assert len(assistant.prompts) == 1  # the user typed nothing
        text = assistant.prompts[0]
        for needle in (
            "# Dev set",
            "accuracy 0.500 (target 0.90)",
            "macro-F1 0.333",
            "micro-F1 0.500",
            "n=8",
            "# Per label",
            "P 0.50  R 1.00  F1 0.67  gold 4",
            "# Disagreements (4)",
            "gold b → a  item 1",
            "reasoning: r",
            "# Current prompt\nClassify.",
            "# Taxonomy",
            "# Instructions",
            "Reply in two or three sentences",
            "Call propose_prompt only when the user asks or agrees",
        ):
            assert needle in text, needle
        history = files.load_chat("tuning")
        assert isinstance(history[0], ModelRequest)
        assert history[0].metadata["hunches"] == "context"  # ty: ignore[not-subscriptable]
        assert "7 disagreements" not in history[0].metadata["summary"]  # ty: ignore[not-subscriptable]
        assert "4 disagreements" in history[0].metadata["summary"]  # ty: ignore[not-subscriptable]
        folds = list(screen.query_one(ChatPanel).query(FoldLine))
        assert [f.kind for f in folds] == ["context"]
        assert "Reply." in [ln.text for ln in screen.query(ChatLine)]
        digest = json.loads(files.read_text("chat/tuning.meta.json") or "")[
            "context_digest"
        ]

        screen.rerun()  # nothing changed: all cache hits, same digest
        await quiesce(app, pilot)
        assert len(assistant.prompts) == 1

        screen.prompt = "Classify. BETTER"
        screen.rerun()
        await quiesce(app, pilot)
        assert len(assistant.prompts) == 2
        update = assistant.prompts[1]
        assert "# Dev set (prompt version 3)" in update
        assert (
            "accuracy 1.000 (target 0.90)" in update and "# Disagreements (0)" in update
        )
        assert "what changed since the last run" in update
        assert [m.metadata["hunches"] for m in history_requests("update")] == ["update"]
        new = json.loads(files.read_text("chat/tuning.meta.json") or "")
        assert new["context_digest"] != digest


async def test_a_failed_context_turn_leaves_no_meta(assistant):
    assistant.fail = True
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        assert files.read_text("chat/tuning.meta.json") is None
        errors = [ln.text for ln in screen.query(ChatLine) if ln.kind == "error"]
        assert errors == ["Error: boom"]


async def test_get_disagreements_filters_by_gold_and_predicted_label_with_reasoning(
    assistant,
):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        gold = [{"a"}, {"b"}, {"c"}]
        predicted = [{"b"}, {"b"}, {"a"}]
        screen.rows = [
            files.GoldRow(id=str(i), text=f"item{i}", labels=sorted(g), split="dev")
            for i, g in enumerate(gold)
        ]
        screen.predicted, screen.errors = predicted, {}
        screen.reasoning = {0: "why0", 2: "why2"}
        screen.metrics = metrics.compute_metrics(gold, predicted, ["a", "b", "c"])
        assert screen.metrics.disagreements == [0, 2]
        tool = screen.agent._function_toolset.tools["get_disagreements"].function

        only_predicted = await tool(label="b")  # item0 was predicted b; item1 agrees
        assert "1. gold a → b  item0" in only_predicted
        assert "reasoning: why0" in only_predicted and "item2" not in only_predicted
        only_gold = await tool(label="c")  # item2 has gold c
        assert "gold c → a  item2" in only_gold and "reasoning: why2" in only_gold
        assert "item0" not in only_gold
        both = await tool(label="a")  # gold of item0, predicted of item2
        assert "item0" in both and "item2" in both
        assert "item2" not in await tool(limit=1) and "1 of 2" in await tool(limit=1)
        assert (await tool(label="zz")) == "No disagreements for label zz."


async def test_both_tools_are_not_available_while_the_dev_set_runs(assistant):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        tools = screen.agent._function_toolset.tools
        for flag in ("running", "stopped"):
            setattr(screen, flag, True)
            got = await tools["get_disagreements"].function()
            assert got == "Not available while the dev set is running."
            got = await tools["propose_prompt"].function(
                SimpleNamespace(tool_call_id="t"), "p", "r"
            )
            assert got == "Not available while the dev set is running."
            setattr(screen, flag, False)
        assert app.screen is screen and not proposals()


async def test_propose_button_sends_the_canned_message_and_accept_reruns(assistant):
    ask_for_proposal(assistant)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        modal = await open_proposal(app, pilot)
        assert CANNED in [ln.text for ln in screen.query(ChatLine)]
        card = screen.query_one(ProposalCard)  # pending while the modal is open
        assert "Proposed prompt change" in card.text and "+1 −1" in card.text
        assert [b.id for b in card.query("Button")] == ["review", "reject-card"]
        assert "+Classify. BETTER" in str(modal.query_one("#diff", Static).render())
        await pilot.click("#accept")
        await quiesce(app, pilot)
        assert tool_returns("propose_prompt") == ["Accepted"]
        assert files.read_text("prompt.md") == "Classify. BETTER"
        assert len(calls) == 16  # the dev set classified again
        assert [e["status"] for e in proposals()] == ["accepted"]
        assert (proposals()[0]["plus"], proposals()[0]["minus"]) == (1, 1)
        assert "Accepted" in card.text and "edited" not in card.text
        assert not card.query("Button")
        assert len(assistant.prompts) == 3  # context, the question, the UPDATED turn
        assert len(history_requests("update")) == 1 and not history_requests("edit")
        assert "Proposed prompt change" not in str(screen.query_one("#note").render())


async def test_accept_with_edits_returns_the_diff_and_records_one_edit_line(assistant):
    ask_for_proposal(assistant)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        modal = await open_proposal(app, pilot)
        modal.query_one("#proposal", TextArea).text = "Classify. BETTER!"
        await pilot.pause()
        await pilot.click("#accept")
        await quiesce(app, pilot)
        (result,) = tool_returns("propose_prompt")
        assert result.startswith("Accepted with edits: ")
        assert "-Classify. BETTER\n+Classify. BETTER!" in result.replace("\r", "")
        assert files.read_text("prompt.md") == "Classify. BETTER!"
        (edit,) = history_requests("edit")
        assert edit.metadata["summary"] == "Prompt: proposal accepted with edits"
        body = str(edit.parts[0].content)
        assert "You accepted the proposal and edited it" in body
        assert (
            "+Classify. BETTER!" in body
            and "# Current prompt\nClassify. BETTER!" in body
        )
        assert "edited" in screen.query_one(ProposalCard).text
        assert len(assistant.prompts) == 3  # the edit line cost no model call


async def test_reject_returns_rejected_and_leaves_the_prompt(assistant):
    ask_for_proposal(assistant)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        await open_proposal(app, pilot)
        await pilot.click("#reject")
        await quiesce(app, pilot)
        assert tool_returns("propose_prompt") == ["Rejected"]
        assert files.read_text("prompt.md") == "Classify." and len(calls) == 8
        assert [e["status"] for e in proposals()] == ["rejected"]
        card = screen.query_one(ProposalCard)
        assert "Rejected. The assistant keeps the current prompt." in card.text
        assert len(assistant.prompts) == 2 and not history_requests("edit")


async def test_escape_keeps_a_pending_card_whose_review_reopens_the_modal(assistant):
    ask_for_proposal(assistant)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        await open_proposal(app, pilot)
        await pilot.press("escape")
        await quiesce(app, pilot)
        assert tool_returns("propose_prompt") == [
            "Pending: the user has not decided yet"
        ]
        assert app.screen is screen and files.read_text("prompt.md") == "Classify."
        assert [e["status"] for e in proposals()] == ["pending"]
        # the chat panel gains its focus border one column wide when the button is focused: click inside
        await pilot.click("#review", offset=(2, 0))
        await wait_for(pilot, lambda: isinstance(app.screen, ProposalScreen))
        assert app.screen.query_one("#proposal", TextArea).text == "Classify. BETTER"
        await pilot.click("#accept")
        await quiesce(app, pilot)
        assert files.read_text("prompt.md") == "Classify. BETTER"
        assert [e["status"] for e in proposals()] == ["accepted"]
        assert len(calls) == 16
        assert (
            len(assistant.prompts) == 3
        )  # context, question, UPDATED: Review costs nothing


async def test_pending_card_survives_a_resume_and_a_manual_edit_supersedes_it(
    assistant,
):
    ask_for_proposal(assistant)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await start(app, pilot)
        await quiesce(app, pilot)
        await open_proposal(app, pilot)
        await pilot.press("escape")
        await quiesce(app, pilot)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        (card,) = screen.query(ProposalCard)
        assert card.query("#review") and "Proposed prompt change" in card.text
        assert len(assistant.prompts) == 2  # nothing changed: no new context turn
        await pilot.press("o")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, PromptEditScreen)
        modal.query_one("#prompt", TextArea).text = "Classify. MINE"
        await pilot.pause()
        await pilot.click("#save")
        await quiesce(app, pilot)
        assert [e["status"] for e in proposals()] == ["superseded"]
        assert "Superseded" in card.text and not card.query("Button")
        assert files.read_text("prompt.md") == "Classify. MINE"


async def test_target_changes_and_manual_edits_append_one_edit_line_each_without_a_model_call(
    assistant,
):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        before = len(assistant.prompts)
        await pilot.press("m")
        await pilot.pause()
        await pilot.click("#score-down")
        await quiesce(app, pilot)
        edits = [e.metadata["summary"] for e in history_requests("edit")]
        assert edits == ["Target: macro_f1 ≥ 0.90", "Target: macro_f1 ≥ 0.89"]
        bodies = [str(e.parts[0].content) for e in history_requests("edit")]
        assert "target metric: accuracy → macro_f1" in bodies[0]
        assert "target score: 0.90 → 0.89" in bodies[1]
        assert len(assistant.prompts) == before  # zero model calls
        assert [f.kind for f in screen.query(FoldLine)].count("edit") == 2

        screen.query_one("#target", Select).value = "micro_f1"
        await quiesce(app, pilot)
        assert len(history_requests("edit")) == 3 and len(assistant.prompts) == before

        await pilot.press("o")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, PromptEditScreen)
        modal.query_one("#prompt", TextArea).text = "Classify. BETTER"
        await pilot.pause()
        await pilot.click("#save")
        await quiesce(app, pilot)
        edit = history_requests("edit")[-1]
        assert edit.metadata["summary"] == "Prompt: edited by the user"
        body = str(edit.parts[0].content)
        assert "You edited the prompt yourself" in body
        assert "-Classify.\n+Classify. BETTER" in body
        assert "# Current prompt\nClassify. BETTER" in body
        assert len(history_requests("edit")) == 4
        assert (
            len(assistant.prompts) == before + 1
        )  # only the UPDATED turn after the re-run
        assert len(history_requests("update")) == 1


async def test_instructions_carry_the_current_prompt_taxonomy_and_target(assistant):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        first = assistant.instructions[0] or ""
        assert "Each disagreement includes the classifier's own reasoning." in first
        assert "# Current prompt\nClassify." in first and "BETTER" not in first
        assert "mode: single" in first and "accuracy" in first and "0.90" in first
        screen.accepted("Classify. BETTER")
        await quiesce(app, pilot)
        assert "# Current prompt\nClassify. BETTER" in (
            assistant.instructions[-1] or ""
        )


async def test_instructions_carry_status_and_gold_coverage_and_the_embedding_change(
    assistant,
):
    files.write_text(
        "candidates.meta.json", json.dumps({"embedding_model": "old-model"})
    )
    files.write_gold(
        files.read_gold()
        + [files.GoldRow(id="gone", text="lost row", labels=["a"], split="dev")]
    )
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await start(app, pilot)
        await quiesce(app, pilot)
    text = assistant.instructions[0] or ""
    assert "# Pipeline status\n1 Brief and seeds:" in text
    assert "2 Search: STALE: embedding model changed (the project now uses m;" in text
    assert "the candidates were built with old-model)" in text
    assert "# Gold coverage\ndev: 9 rows, 9 labelled, 1 orphaned" in text
    assert '- gone "lost row" [a]' in text


async def test_propose_is_disabled_while_a_reply_streams(assistant):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        propose = screen.query_one("#propose", Button)
        assert not propose.disabled
        assistant.gate = asyncio.Event()
        screen.query_one(ChatPanel).send("hello")
        await wait_for(pilot, lambda: screen.query_one(ChatPanel).running)
        assert propose.disabled
        await pilot.press("e")  # the key does nothing either
        assert assistant.prompts[-1] == "hello"
        assistant.gate.set()
        await quiesce(app, pilot)
        assert not propose.disabled and assistant.prompts.count(CANNED) == 0


async def test_a_failed_assistant_call_is_an_error_line_not_a_note(assistant):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        assistant.fail = True
        await pilot.click("#propose")
        await quiesce(app, pilot)
        assert [ln.text for ln in screen.query(ChatLine) if ln.kind == "error"] == [
            "Error: boom"
        ]
        assert "Proposal failed" not in str(screen.query_one("#note").render())


async def test_wide_layout_is_chat_left_42_wide_with_results_beside_it(assistant):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        chat, results = screen.query_one(ChatPanel), screen.query_one("#results")
        assert (
            chat.display and results.display and not screen.query_one("#tabs").display
        )
        assert chat.outer_size.width == 42
        assert chat.region.right <= results.region.x
        assert results.region.width > 42
        keys = screen.active_bindings
        assert "c" not in keys or not keys["c"].enabled
        assert keys["e"].binding.description == "Propose edit"
        assert keys["o"].binding.description == "Edit prompt"
        assert keys["m"].binding.description == "Target metric"


async def test_narrow_layout_has_chat_and_results_tabs_and_c_switches(assistant):
    app = HunchesApp()
    async with app.run_test(size=(119, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        tabs = screen.query_one("#tabs")
        chat, results = screen.query_one(ChatPanel), screen.query_one("#results")
        assert tabs.display
        labels = [str(t.render()) for t in tabs.query(".tab")]
        assert labels == ["Chat ●", "Results"]  # a reply arrived while on Results
        assert results.display and not chat.display
        keys = screen.active_bindings
        assert keys["c"].binding.description == "Chat" and keys["c"].enabled
        assert keys["e"].binding.description == "Propose"
        assert keys["o"].binding.description == "Prompt"
        assert keys["m"].binding.description == "Metric"
        await pilot.press("c")
        await pilot.pause()
        assert chat.display and not results.display
        assert [str(t.render()) for t in tabs.query(".tab")] == ["Chat", "Results"]
        assert chat.outer_size.width >= 119 - 26 or chat.outer_size.width >= 90
        await pilot.press(
            "c"
        )  # typing in the input would eat the key; focus is elsewhere
        await pilot.pause()
        assert results.display and not chat.display
        await pilot.click("#tab-chat")
        await pilot.pause()
        assert chat.display and not results.display


async def test_chat_and_tabs_are_hidden_during_a_run_and_come_back(
    assistant, monkeypatch
):
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

    app = HunchesApp()
    async with app.run_test(size=(119, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        monkeypatch.setattr(tune, "classify_many", slow)
        await pilot.press("c")
        screen.prompt = "Classify. BETTER"  # a new prompt: nothing comes from the cache
        screen.rerun()
        await wait_for(pilot, lambda: screen.running and len(calls) >= 12)
        assert not screen.query_one(ChatPanel).display
        assert not screen.query_one("#tabs").display
        assert screen.query_one(RunIndicator).display
        gate.set()
        await quiesce(app, pilot)
        assert screen.query_one("#tabs").display
        assert screen.query_one(ChatPanel).display  # the tab the user was on


async def test_accepted_prompt_is_saved_through_history():
    from hunches import history

    files.write_state(files.State(seeds_approved=True, taxonomy_approved=True))
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(5)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TuneScreen)
        screen.model = FunctionModel(classifier)  # ty: ignore[invalid-assignment]
        screen.accepted("Classify. BETTER!")
        await settle(app, pilot)
        last = history.entries("prompt")[-1]
        assert last["source"] == "user"
        assert history.text(last["after"]) == "Classify. BETTER!"


# ---- spec 004 task 07: status, gold coverage and the gold tools


def meta_now() -> dict:
    return json.loads(files.read_text("chat/tuning.meta.json") or "{}")


async def say(app, pilot, screen, text):
    box = screen.query_one("#chat-input")
    box.focus()
    box.value = text
    await pilot.press("enter")
    await quiesce(app, pilot)


async def test_context_turn_carries_both_sections_and_records_what_was_told(assistant):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await start(app, pilot)
        await quiesce(app, pilot)
    assert "# Pipeline status\n1 Brief and seeds:" in assistant.prompts[0]
    assert (
        "# Gold coverage\ndev: 8 rows, 8 labelled, 0 orphaned" in assistant.prompts[0]
    )
    assert meta_now()["status_digest"]
    assert meta_now()["context_digest"]  # the dev-run digest is kept beside it


async def test_updated_message_is_added_once_per_change_and_never_repeated(assistant):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        assert len(assistant.prompts) == 1
        await screen.sync_status()  # nothing changed
        await quiesce(app, pilot)
        assert len(assistant.prompts) == 1

        files.write_gold(
            files.read_gold()
            + [files.GoldRow(id="gone", text="lost row", labels=["a"], split="dev")]
        )
        await screen.sync_status()
        await quiesce(app, pilot)
        assert len(assistant.prompts) == 2
        update = assistant.prompts[1]
        assert "# Pipeline status" in update
        assert "dev: 9 rows, 9 labelled, 1 orphaned" in update
        assert '- gone "lost row" [a]' in update
        assert "# Instructions" in update
        assert len(history_requests("update")) == 1

        await screen.sync_status()  # same state: not again
        await quiesce(app, pilot)
        assert len(assistant.prompts) == 2

        files.write_text(
            "candidates.meta.json", json.dumps({"embedding_model": "old-model"})
        )
        await screen.sync_status()  # the stale set changed
        await quiesce(app, pilot)
        assert len(assistant.prompts) == 3
        assert "STALE: embedding model changed" in assistant.prompts[2]
        assert len(history_requests("update")) == 2
        assert meta_now()["context_digest"]  # the context digest survives the merge


async def test_failed_status_turn_is_not_recorded_as_sent(assistant):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        told = meta_now()["status_digest"]
        files.write_gold(
            files.read_gold()
            + [files.GoldRow(id="gone", text="lost row", labels=["a"], split="dev")]
        )
        assistant.fail = True
        await screen.sync_status()
        await quiesce(app, pilot)
        assert meta_now()["status_digest"] == told
        assistant.fail = False
        await screen.sync_status()  # so the next try sends it
        await quiesce(app, pilot)
        assert meta_now()["status_digest"] != told


async def test_get_gold_coverage_tool_returns_the_section_for_a_split(assistant):
    files.write_gold(
        files.read_gold()
        + [
            files.GoldRow(id="gone", text="lost row", labels=["a"], split="dev"),
            files.GoldRow(id="t", text="test row", labels=["b"], split="test"),
        ]
    )
    assistant.tools["coverage"] = ("get_gold_coverage", {"split": "dev"})
    assistant.tools["all"] = ("get_gold_coverage", {})
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        await say(app, pilot, screen, "coverage")
        await say(app, pilot, screen, "all")
    dev_only, both = tool_returns("get_gold_coverage")
    assert dev_only == files.gold_coverage_text("dev")
    assert "dev: 9 rows" in dev_only and "test:" not in dev_only
    assert both == files.gold_coverage_text()
    assert "test: 1 rows, 1 labelled, 1 orphaned" in both


def question(app) -> str:
    screen = app.screen
    assert isinstance(screen, ConfirmScreen)
    return screen.question


def removal_args(*ids):
    return ("remove_gold", {"ids": list(ids), "reason": "seeds changed"})


async def test_remove_gold_writes_nothing_until_confirmed_and_returns_the_answer(
    assistant,
):
    assistant.tools["remove"] = removal_args("0", "1")
    before = files.read_text("gold.jsonl")
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        box = screen.query_one("#chat-input")
        box.focus()
        box.value = "remove"
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        assert "2 dev rows" in question(app)
        assert files.read_text("gold.jsonl") == before  # still nothing written
        assert files.read_text("gold_removed.jsonl") is None
        await pilot.click("#no")
        await quiesce(app, pilot)
        assert tool_returns("remove_gold") == ["The user rejected the removal."]
        assert files.read_text("gold.jsonl") == before
        assert files.read_text("gold_removed.jsonl") is None

        box.focus()
        box.value = "remove"
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.click("#yes")
        await quiesce(app, pilot)
    assert tool_returns("remove_gold")[-1] == "Removed 2 rows."
    assert [r.id for r in files.read_gold()] == ["2", "3", "4", "5", "6", "7"]
    removed = files.read_jsonl("gold_removed.jsonl")
    assert [(r["id"], r["reason"], r["labels"]) for r in removed] == [
        ("0", "seeds changed", ["a"]),
        ("1", "seeds changed", ["b"]),
    ]


async def test_remove_gold_names_the_split_in_the_question(assistant):
    files.write_gold(
        files.read_gold()
        + [files.GoldRow(id="t", text="test row", labels=["b"], split="test")]
    )
    assistant.tools["remove"] = removal_args("t")
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        box = screen.query_one("#chat-input")
        box.focus()
        box.value = "remove"
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        assert "1 test row" in question(app)
        assert "held out" in question(app)
        await pilot.click("#no")
        await quiesce(app, pilot)


async def test_remove_gold_with_unknown_ids_asks_nothing(assistant):
    assistant.tools["remove"] = removal_args("nope")
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        await say(app, pilot, screen, "remove")
    assert tool_returns("remove_gold") == [
        "No gold row has those ids. Nothing removed."
    ]


async def test_draw_gold_adds_unlabelled_rows_and_the_user_labels_them(assistant):
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": str(i), "text": f"item {i}", "max_similarity": 0.7, "best_seed": "x"}
            for i in range(12)
        ],
    )
    assistant.tools["draw"] = ("draw_gold", {"split": "dev", "n": 3})
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        await quiesce(app, pilot)
        await say(app, pilot, screen, "draw")
    (result,) = tool_returns("draw_gold")
    new = [r for r in files.read_gold() if r.id not in {str(i) for i in range(8)}]
    assert len(new) == 3 and all(r.labels == [] and r.split == "dev" for r in new)
    assert result.startswith("Drew 3 unlabelled dev rows")
    assert "the user labels them" in result


async def test_no_assistant_tool_sets_a_gold_label(assistant):
    names = set()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        names = set(screen.agent._function_toolset.tools)
    assert names == {
        "get_disagreements",
        "propose_prompt",
        "get_gold_coverage",
        "remove_gold",
        "draw_gold",
    }
    import inspect

    for name in ("remove_gold", "draw_gold", "get_gold_coverage"):
        params = inspect.signature(
            screen.agent._function_toolset.tools[name].function
        ).parameters
        assert "labels" not in params and "label" not in params
