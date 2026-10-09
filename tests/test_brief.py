import json

import pytest
from conftest import panel_title
from pydantic_ai.messages import ModelRequest
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from textual.widgets import Button, Input, Static

from hunches import candidates, files, history
from hunches.app import ChatPanel, HunchesApp, StatusHeader
from hunches.screens.brief import BriefScreen, SeedInput

pytestmark = pytest.mark.usefixtures("system_ready")


async def stream(messages, info: AgentInfo):
    if any(p.part_kind == "tool-return" for p in messages[-1].parts):
        yield "Done."
    else:
        yield {
            0: DeltaToolCall(
                name="propose_seeds",
                json_args='{"seeds": ["Mentions a layoff", "Describes burnout"]}',
            )
        }


def setup(tmp_path, monkeypatch, seeds=None):
    monkeypatch.chdir(tmp_path)
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir="c",
            embedding_model="m",
        )
    )
    if seeds:
        from hunches.screens.brief import write_seeds

        write_seeds(seeds)


def rows(screen) -> list[str]:
    """Plain text of each seed row's phrase (the input's value on an editor row)."""
    out = []
    for row in screen.query("SeedRow"):
        box = row.query(Input)
        out.append(
            box.first().value if box else str(row.query(".text").first().render())
        )
    return out


def edits(n: int | None = None):
    return [
        m
        for m in files.load_chat("brief")
        if isinstance(m, ModelRequest) and (m.metadata or {}).get("hunches") == "edit"
    ]


async def test_chat_proposes_seeds_and_brief_md_is_written(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.agent.model = FunctionModel(stream_function=stream)
        box = screen.query_one("#chat-input", Input)
        box.focus()
        box.value = "Find posts about job loss"
        await pilot.press("enter")
        await pilot.pause(0.5)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert files.read_text("brief.md") == "Find posts about job loss\n"
        assert candidates.read_seeds() == ["Mentions a layoff", "Describes burnout"]
        assert rows(screen) == ["Mentions a layoff", "Describes burnout"]
        assert files.load_chat("brief")
        # the agent's own tool call is in history and is not repeated as an edit line
        assert edits() == []


async def test_edit_flow_save_and_discard(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["alpha", "beta"])
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.query_one("#seed-list").focus()
        await pilot.press("down")  # cursor on seed 2
        await pilot.press("e")
        await pilot.pause()
        box = screen.query_one(SeedInput)
        assert box.value == "beta" and box.has_focus
        assert str(screen.query_one("#editor-title").render()) == "Editing seed 2"
        assert "was: beta" in str(screen.query_one("#was").render())
        assert not screen.query_one("#unsaved").display
        assert screen.query_one("#save", Button).disabled  # unchanged
        assert not screen.query_one("#seed-buttons").display  # Approve etc. hidden
        # other rows are dimmed
        assert screen.query("SeedRow").first().has_class("-dim")

        await pilot.press("x")
        await pilot.pause()
        assert screen.query_one("#unsaved").display
        assert "UNSAVED" in str(screen.query_one("#unsaved").render())
        assert not screen.query_one("#save", Button).disabled
        assert candidates.read_seeds() == ["alpha", "beta"]  # nothing written yet

        box.value = ""
        await pilot.pause()
        assert screen.query_one("#save", Button).disabled  # empty

        # Esc discards: nothing written, nothing recorded
        box.value = "betax"
        await pilot.press("escape")
        await pilot.pause()
        assert candidates.read_seeds() == ["alpha", "beta"]
        assert rows(screen) == ["alpha", "beta"]
        assert not screen.query(SeedInput)
        assert screen.query_one("#seed-buttons").display
        assert edits() == []

        # edit again and save with Enter
        await pilot.press("e")
        await pilot.pause()
        screen.query_one(SeedInput).value = "beta two"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert candidates.read_seeds() == ["alpha", "beta two"]
        assert rows(screen) == ["alpha", "beta two"]
        saved = edits()
        assert len(saved) == 1
        assert saved[0].metadata["summary"] == "Seed 2 edited"
        text = str(saved[0].parts[0].content)
        assert "was: beta" in text and "now: beta two" in text
        assert "# Current seeds\n1. alpha\n2. beta two" in text


async def test_add_flow(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["alpha"])
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.query_one("#seed-list").focus()
        await pilot.press("a")
        await pilot.pause()
        assert rows(screen) == ["alpha", ""]
        assert screen.query_one(SeedInput).has_focus
        assert str(screen.query_one("#editor-title").render()) == "New seed"
        assert "Add" in str(screen.query_one("#save", Button).label)
        assert screen.query_one("#save", Button).disabled
        await pilot.press("e", "w")  # typed into the input, not bindings
        await pilot.pause()
        assert not screen.query_one("#save", Button).disabled
        assert candidates.read_seeds() == ["alpha"]

        await pilot.press("escape")  # Discard removes the row
        await pilot.pause()
        assert rows(screen) == ["alpha"]
        assert candidates.read_seeds() == ["alpha"]
        assert edits() == []

        await pilot.press("a")
        await pilot.pause()
        await pilot.press(*"New, seed", "enter")
        await pilot.pause()
        assert candidates.read_seeds() == ["alpha", "New, seed"]
        assert rows(screen) == ["alpha", "New, seed"]
        saved = edits()
        assert len(saved) == 1
        assert saved[0].metadata["summary"] == "Seed added"
        text = str(saved[0].parts[0].content)
        assert "+ 2  New, seed" in text
        assert "# Current seeds\n1. alpha\n2. New, seed" in text


async def test_delete_records_edit_with_no_model_call(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["alpha", "beta", "gamma"])
    calls = []

    async def counting(messages, info):
        calls.append(1)
        yield "x"

    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.agent.model = FunctionModel(stream_function=counting)
        screen.query_one("#seed-list").focus()
        await pilot.press("down", "d")
        await pilot.pause()
        assert candidates.read_seeds() == ["alpha", "gamma"]
        assert rows(screen) == ["alpha", "gamma"]
        saved = edits()
        assert len(saved) == 1 and calls == []
        assert saved[0].metadata["summary"] == "Seed 2 deleted"
        text = str(saved[0].parts[0].content)
        assert "- 2  beta" in text and "# Current seeds\n1. alpha\n2. gamma" in text
        # Delete button works too
        await pilot.click("#delete")
        await pilot.pause()
        assert len(candidates.read_seeds()) == 1


async def test_buttons_follow_seeds_and_approve_confirm_text(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        assert not screen.query_one("#add", Button).disabled
        for bid in ("#edit", "#delete", "#approve"):
            assert screen.query_one(bid, Button).disabled
        labels = [
            str(screen.query_one(b, Button).label)
            for b in ("#add", "#edit", "#delete", "#approve")
        ]
        assert labels == ["Add seed  a", "Edit  e", "Delete  d", "Approve seeds  F2"]
        # the guard stays: F2 with no seeds does nothing, silently
        await pilot.press("f2")
        await pilot.pause()
        assert not files.read_state().seeds_approved
        assert type(app.screen).__name__ == "BriefScreen"
        assert not screen.query("#status")

        screen.add_seeds(["A seed", "B seed"])
        await pilot.pause()
        for bid in ("#edit", "#delete", "#approve"):
            assert not screen.query_one(bid, Button).disabled
        await pilot.click("#approve")
        await pilot.pause()
        question = str(app.screen.query_one("ConfirmScreen Label").render())
        assert question == "Approve 2 seeds and start searching?"
        await pilot.click("#yes")
        await pilot.pause()
        assert files.read_state().seeds_approved
        (entry,) = [e for e in history.entries() if e["kind"] == "approval"]
        assert (entry["stage"], entry["flag"], entry["summary"]) == (
            1,
            "seeds_approved",
            "Approved: 2 seeds",
        )
        assert app.stage == 2


async def test_f2_while_editing_does_nothing(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["alpha"])
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.query_one("#seed-list").focus()
        await pilot.press("e")
        await pilot.pause()
        screen.action_approve()
        await pilot.pause()
        assert type(app.screen).__name__ == "BriefScreen"
        assert not files.read_state().seeds_approved


async def test_agent_append_mid_edit_keeps_draft_and_index(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["alpha", "beta"])
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.query_one("#seed-list").focus()
        await pilot.press("e")
        await pilot.pause()
        screen.query_one(SeedInput).value = "alpha draft"
        await pilot.pause()
        screen.add_seeds(["gamma"])  # what propose_seeds does
        await pilot.pause()
        assert candidates.read_seeds() == ["alpha", "beta", "gamma"]
        box = screen.query_one(SeedInput)
        assert box.value == "alpha draft" and box.seed_index == 0
        assert rows(screen) == ["alpha draft", "beta", "gamma"]
        assert box.has_focus
        assert edits() == []  # appended silently
        await pilot.press("enter")
        await pilot.pause()
        assert candidates.read_seeds() == ["alpha draft", "beta", "gamma"]


async def test_dynamic_instructions_carry_current_seeds(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["alpha", "beta"])
    seen: list[str | None] = []

    async def spy(messages, info: AgentInfo):
        seen.append(info.instructions)
        yield "ok"

    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.agent.model = FunctionModel(stream_function=spy)
        # a change made in the screen, not yet in a message the model has seen
        screen.seeds.append("gamma")
        box = screen.query_one("#chat-input", Input)
        box.focus()
        box.value = "hi"
        await pilot.press("enter")
        await pilot.pause(0.5)
        await app.workers.wait_for_complete()
        assert len(seen) == 1 and seen[0]
        assert "1. alpha\n2. beta\n3. gamma" in seen[0]
        assert "propose_seeds" in seen[0]  # the static text is still there


async def test_resume_restores_chat_and_seeds(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.agent.model = FunctionModel(stream_function=stream)
        box = screen.query_one("#chat-input", Input)
        box.focus()
        box.value = "hello"
        await pilot.press("enter")
        await pilot.pause(0.5)
        await app.workers.wait_for_complete()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert rows(app.screen) == ["Mentions a layoff", "Describes burnout"]
        panel = app.screen.query_one(ChatPanel)
        assert [(line.kind, line.text) for line in panel.lines] == [
            ("user", "hello"),
            ("tool", "propose_seeds Added 2 seeds."),
            ("assistant", "Done."),
        ]
        assert app.screen.query_one(StatusHeader)


@pytest.mark.parametrize("size", [(80, 24), (100, 30), (120, 36)])
async def test_layout_titles_empty_states_and_buttons_fit(tmp_path, monkeypatch, size):
    setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        pane = screen.query_one("#seeds-pane")
        assert panel_title(pane) == ("Seeds", "0 seeds")
        assert panel_title(screen.query_one("ChatPanel"))[0] == "chat · brief"
        chat_empty = screen.query_one("ChatPanel #empty")
        assert str(chat_empty.render()) == (
            "Describe what concepts you want to search for and the assistant "
            "will help you generate seed phrases"
        )
        empty = screen.query_one("#empty-seeds")
        assert empty.display
        assert "No seeds yet. Describe what to find in the chat" in str(empty.render())
        assert not screen.query_one("#seed-list").display

        screen.add_seeds(["A"])
        await pilot.pause()
        assert panel_title(pane)[1] == "1 seed"
        screen.add_seeds(["B"])
        await pilot.pause()
        assert panel_title(pane)[1] == "2 seeds"
        assert not empty.display and screen.query_one("#seed-list").display
        # every button sits inside the seeds panel
        for bid in ("#add", "#edit", "#delete", "#approve"):
            button = screen.query_one(bid, Button)
            assert pane.region.contains_region(button.region), (bid, size)
        screen.query_one("#seed-list").focus()
        await pilot.pause()
        assert pane.has_pseudo_class("focus-within")

        # editor box fits too
        await pilot.press("e")
        await pilot.pause()
        for bid in ("#save", "#discard"):
            assert pane.region.contains_region(screen.query_one(bid).region), size
        assert pane.region.contains_region(screen.query_one("#was").region)


async def test_removed_pieces_are_gone(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, ["alpha"])
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert not screen.query("#seed-input")
        assert not screen.query("#status")
        assert not any("seeds.csv" in str(s.render()) for s in screen.query(Static))


async def test_seed_edits_are_saved_through_history(tmp_path, monkeypatch):
    from hunches import history

    setup(tmp_path, monkeypatch, ["alpha"])
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.query_one("#seed-list").focus()
        await pilot.press("a")
        await pilot.pause()
        screen.query_one(SeedInput).value = "beta"
        await pilot.press("enter")
        await pilot.pause()
        last = history.entries("seeds")[-1]
        assert (last["source"], last["summary"]) == ("user", "Seed added")
        assert history.text(last["after"]) == "seed\nalpha\nbeta\n"
        assert history.can_undo("seeds")


async def test_proposed_seeds_are_one_assistant_group(tmp_path, monkeypatch):
    from hunches import history

    setup(tmp_path, monkeypatch, ["alpha"])
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.add_seeds(["gamma", "delta"], source="assistant", group="turn-1")
        last = history.entries("seeds")[-1]
        assert (last["source"], last["group"]) == ("assistant", "turn-1")
        assert candidates.read_seeds() == ["alpha", "gamma", "delta"]
        assert history.undo("seeds") is not None
        assert candidates.read_seeds() == ["alpha"]


async def test_instructions_carry_status_and_gold_coverage_and_the_embedding_change(
    tmp_path, monkeypatch
):
    setup(tmp_path, monkeypatch, ["alpha"])
    files.write_jsonl(
        "candidates.jsonl",
        [{"id": "c", "text": "t", "max_similarity": 0.7, "best_seed": "alpha"}],
    )
    files.write_text(
        "candidates.meta.json",
        json.dumps(
            {
                "seeds_digest": candidates.seeds_digest(["alpha"]),
                "embedding_model": "old-model",
            }
        ),
    )
    files.write_gold(
        [files.GoldRow(id="gone", text="lost row", labels=["a"], split="dev")]
    )
    seen: list[str | None] = []

    async def spy(messages, info: AgentInfo):
        seen.append(info.instructions)
        yield "ok"

    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.agent.model = FunctionModel(stream_function=spy)
        box = screen.query_one("#chat-input", Input)
        box.focus()
        box.value = "hi"
        await pilot.press("enter")
        await pilot.pause(0.5)
        await app.workers.wait_for_complete()
    text = seen[0] or ""
    assert "# Pipeline status\n1 Brief and seeds:" in text
    assert "2 Search: STALE: embedding model changed (the project now uses" in text
    assert "the candidates were built with old-model)" in text
    assert "# Gold coverage\ndev: 1 rows, 1 labelled, 1 orphaned" in text
    assert '- gone "lost row" [a]' in text
