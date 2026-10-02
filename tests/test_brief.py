from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from textual.widgets import DataTable, Input, RichLog

from hunches import candidates, files
from hunches.app import HunchesApp, StatusHeader
from hunches.screens.brief import BriefScreen


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


def setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.write_config(files.Config(corpus_dir="c", embedding_model="m"))


async def test_chat_proposes_seeds_and_edits_persist(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        table = screen.query_one("#seeds", DataTable)
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
        assert table.row_count == 2
        assert files.load_chat("brief")

        table.focus()
        await pilot.press("d")  # delete first row
        await pilot.pause()
        assert candidates.read_seeds() == ["Describes burnout"]
        await pilot.press("a")
        await pilot.press(*"New, seed", "enter")
        await pilot.pause()
        assert candidates.read_seeds() == ["Describes burnout", "New, seed"]
        await pilot.press("e")
        screen.query_one("#seed-input", Input).value = "Edited"
        await pilot.press("enter")
        await pilot.pause()
        assert candidates.read_seeds() == ["Edited", "New, seed"]


async def test_approve_requires_seeds_then_sets_flag(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert not files.read_state().seeds_approved
        assert type(app.screen).__name__ == "BriefScreen"
        assert isinstance(app.screen, BriefScreen)
        app.screen.add_seeds(["A seed"])
        await pilot.press("f2")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert files.read_state().seeds_approved
        assert app.stage == 2


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
        assert app.screen.query_one("#seeds", DataTable).row_count == 2
        log = app.screen.query_one("#log", RichLog)
        assert any("hello" in str(line.text) for line in log.lines)
        assert app.screen.query_one(StatusHeader)
