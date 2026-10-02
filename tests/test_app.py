import json

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage
from textual.widgets import Button, Input

from hunches import cost, files
from hunches.app import ChatPanel, HunchesApp, StatusHeader, confirm_approve


def make_project(tmp_path, monkeypatch, **state):
    monkeypatch.chdir(tmp_path)
    files.write_config(files.Config(corpus_dir="c", embedding_model="m"))
    files.write_text("seeds.csv", "seed\nfoo\n")
    files.write_state(files.State(**state))


def header_text(app) -> str:
    return str(app.screen.query_one(StatusHeader).render())


async def test_first_run_setup_then_stage_1(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = HunchesApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        assert app.stage == 0
        await pilot.click("#save")  # empty form is rejected
        await pilot.pause()
        assert not (tmp_path / ".hunches" / "config.toml").exists()
        app.screen.query_one("#corpus_dir", Input).value = "corpus"
        app.screen.query_one("#embedding_model", Input).value = "openai:x"
        app.screen.query_one("#save", Button).press()
        await pilot.pause()
        assert app.stage == 1
    config = files.read_config()
    assert config.corpus_dir == "corpus" and config.embedding_model == "openai:x"


async def test_starts_at_first_incomplete_stage(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.stage == 1
    make_project(tmp_path, monkeypatch, seeds_approved=True)
    files.write_text("candidates.jsonl", json.dumps({"id": "1"}) + "\n")
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.stage == 3
        await pilot.press("n")
        await pilot.pause()
        assert app.stage == 4
        await pilot.press("p", "p", "p", "p")
        await pilot.pause()
        assert app.stage == 1  # clamped; backwards navigation always allowed


async def test_header_shows_unknown_cost_and_updates(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "$0.0000" in header_text(app)
        cost.record("mystery", RunUsage(input_tokens=1, output_tokens=1), None)
        await pilot.pause(0.6)
        text = header_text(app)
        assert "cost ?" in text and "unknown for mystery" in text
        assert "$" not in text


async def test_header_known_cost(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        cost.record("m", RunUsage(input_tokens=1, output_tokens=1), 1.5)
        await pilot.pause(0.6)
        assert "$1.5000" in header_text(app)


async def test_chat_panel_streams_and_persists(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    agent = Agent(TestModel(custom_output_text="hello there"))
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = ChatPanel("brief", agent)
        await app.screen.mount(panel)
        panel.query_one("#chat-input", Input).focus()
        await pilot.press("h", "i", "enter")
        await pilot.pause(0.5)
        assert len(files.load_chat("brief")) == 2
        assert len(panel.history) == 2
        assert cost.breakdown()["test"]["calls"] == 1


async def test_confirm_approve_sets_flag(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        confirm_approve(app.screen, "seeds_approved", "Approve seeds?")
        await pilot.pause()
        assert not files.read_state().seeds_approved
        await pilot.click(Button)  # first button is Approve
        await pilot.pause()
        assert files.read_state().seeds_approved


async def test_quit(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
    assert app.return_code == 0
