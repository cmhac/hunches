import json

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage
from textual.containers import Vertical
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
    files.write_text(
        "candidates.jsonl",
        json.dumps({"id": "1", "text": "t", "max_similarity": 0.7, "best_seed": "s"})
        + "\n",
    )
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
        assert "cost ? · no price for mystery" in text
        assert "$" not in text
        assert app.screen.query_one(StatusHeader).has_class("-cost-unknown")


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
        await pilot.click("#yes")
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


async def test_header_stepper_and_stage_name(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch, seeds_approved=True)
    files.write_text(
        "candidates.jsonl",
        json.dumps({"id": "1", "text": "t", "max_similarity": 0.7, "best_seed": "s"})
        + "\n",
    )
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        text = header_text(app)
        assert text.startswith("hunches")
        assert tmp_path.name[:15] + "…" in text
        assert "●●◉○○○○○○" in text  # stage 3 of 9
        assert "3/9 Taxonomy and prompt" in text
        assert text.rstrip().endswith("cost $0.0000")


async def test_header_truncates_long_project_name(tmp_path, monkeypatch):
    long = tmp_path / "a-very-long-project-directory-name"
    long.mkdir()
    make_project(long, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "a-very-long-pro…" in header_text(app)
        assert "a-very-long-project" not in header_text(app)


async def test_confirm_modal_layout_and_focus(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        confirm_approve(app.screen, "seeds_approved", "Approve seeds?")
        await pilot.pause()
        modal = app.screen
        assert [b.id for b in modal.query(Button)] == ["no", "yes"]  # Cancel, Approve
        assert app.focused.id == "yes"
        box = modal.query_one(Vertical)
        assert box.border_title == "Confirm" and box.outer_size.width == 58
        await pilot.press("enter")  # Approve is focused by default
        await pilot.pause()
        assert files.read_state().seeds_approved


async def test_setup_screen_fits_80x24_in_a_config_panel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        panel = screen.query_one("#config")
        assert panel.border_title == "config.toml"
        for id_ in ("corpus_dir", "s3_bucket", "s3_index", "embedding_model"):
            widget = screen.query_one(f"#{id_}")
            assert widget.size.height == 1  # compact
            assert widget.region.bottom <= 23
        assert screen.query_one("#save").region.bottom <= 23
        await pilot.click("#save")
        await pilot.pause()
        error = screen.query_one("#error")
        assert str(error.render()) == "Required: corpus_dir, embedding_model"
        assert error.has_class("error")


def log_lines(panel) -> list[str]:
    return [strip.text.rstrip() for strip in panel.query_one("#log").lines]


async def test_chat_panel_gutters_title_and_blank_rows(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    agent = Agent(TestModel(custom_output_text="hello there"))
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = ChatPanel("brief", agent)
        await app.screen.mount(panel)
        assert panel.border_title == "chat · brief"
        assert panel.border_subtitle == "test"  # the model name
        panel.query_one("#chat-input", Input).focus()
        await pilot.press("h", "i", "enter", "y", "o", "enter")
        await pilot.pause(0.5)
        lines = log_lines(panel)
        assert lines[:3] == ["› hi", "", "│ hello there"]
        assert lines[3:6] == ["", "› yo", ""]  # one blank row between turns


async def test_chat_panel_restores_history_with_tool_calls(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    files.save_chat(
        "brief",
        [
            ModelRequest(parts=[UserPromptPart(content="find layoffs")]),
            ModelResponse(
                parts=[ToolCallPart(tool_name="propose_seeds", args={"seeds": ["a"]})]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="propose_seeds",
                        content="Added 6 seeds.",
                        tool_call_id="1",
                    )
                ]
            ),
            ModelResponse(parts=[TextPart(content="Done.")]),
        ],
    )
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = ChatPanel("brief", Agent(TestModel()))
        await app.screen.mount(panel)
        await pilot.pause()
        assert log_lines(panel) == [
            "› find layoffs",
            "",
            "↳ propose_seeds · Added 6 seeds.",
            "",
            "│ Done.",
        ]


async def test_chat_panel_error_line(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    agent = Agent(TestModel())

    def boom(*a, **k):
        raise RuntimeError("no key")

    agent.run_stream = boom  # ty: ignore[invalid-assignment]
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = ChatPanel("brief", agent)
        await app.screen.mount(panel)
        panel.query_one("#chat-input", Input).focus()
        await pilot.press("h", "enter")
        await pilot.pause(0.3)
        assert log_lines(panel)[-1] == "Error: no key"
