import json

import pytest
from conftest import panel_title
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage
from textual.containers import Vertical
from textual.widgets import Button, Input

from hunches import cost, files
from hunches.app import ChatPanel, HunchesApp, StatusHeader, confirm_approve


def make_project(tmp_path, monkeypatch, first_run=False, **state):
    """A healthy project in cwd; system.json exists unless `first_run`."""
    from hunches import system

    monkeypatch.chdir(tmp_path)
    if not first_run:
        system.write_system(
            system.System(
                provider="anthropic",
                assistant_model="a",
                classifier_model="c",
                recommendation_seen=system.RECOMMENDED_REVISION,
            )
        )
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="test",
            corpus_dir="c",
            embedding_model="m",
        )
    )
    (tmp_path / "c").mkdir(exist_ok=True)
    for name in ("vectors.npy", "items.jsonl", "meta.json"):
        (tmp_path / "c" / name).write_text(
            "x"
        )  # healthy as far as project_status looks
    files.write_text("seeds.csv", "seed\nfoo\n")
    files.write_state(files.State(**state))


def header_text(app) -> str:
    return str(app.screen.query_one(StatusHeader).render())


async def test_not_in_a_project_shows_projects_or_first_run_setup(
    tmp_path, monkeypatch
):
    from hunches import system
    from hunches.screens.projects import ProjectsScreen
    from hunches.screens.system import SystemSettingsScreen

    monkeypatch.chdir(tmp_path)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SystemSettingsScreen)  # no system.json yet
    system.write_system(
        system.System(
            provider="anthropic",
            assistant_model="a",
            classifier_model="c",
            recommendation_seen=system.RECOMMENDED_REVISION,
        )
    )
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ProjectsScreen) and app.stage == 0


async def test_first_run_in_a_project_shows_system_setup_then_opens_it(
    tmp_path, monkeypatch
):
    from hunches import system
    from hunches.screens.system import SystemSettingsScreen

    make_project(tmp_path, monkeypatch, first_run=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SystemSettingsScreen) and app.stage == 0
        app.screen.query_one("#save", Button).press()
        await pilot.pause()
        assert app.stage == 1
        saved = system.read_system()
        assert saved is not None
        assert [p.path for p in saved.projects] == [str(tmp_path)]


async def test_project_that_cannot_open_falls_back_to_projects(tmp_path, monkeypatch):
    from hunches.screens.projects import ProjectsScreen

    make_project(tmp_path, monkeypatch)
    (tmp_path / "c" / "meta.json").unlink()  # MISSING CORPUS: open_project refuses
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ProjectsScreen) and app.stage == 0


async def test_cwd_project_is_registered_and_opened(tmp_path, monkeypatch):
    from hunches import system

    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.stage == 1
    saved = system.read_system()
    assert saved is not None
    assert [p.path for p in saved.projects] == [str(tmp_path)]


async def test_changed_recommendation_asks_first_then_continues(tmp_path, monkeypatch):
    from hunches import system
    from hunches.screens.system import RecommendationModal

    make_project(tmp_path, monkeypatch)
    stale = system.read_system()
    assert stale is not None
    stale.recommendation_seen = system.RECOMMENDED_REVISION - 1  # models "a"/"c" differ
    system.write_system(stale)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, RecommendationModal) and app.stage == 0
        await pilot.click("#keep-mine")
        await pilot.pause()
        assert app.stage == 1
    kept = system.read_system()
    assert kept is not None
    assert (kept.assistant_model, kept.recommendation_seen) == (
        "a",
        system.RECOMMENDED_REVISION,
    )


async def test_matching_recommendation_is_bumped_silently(tmp_path, monkeypatch):
    from hunches import system

    make_project(tmp_path, monkeypatch)
    rec = system.RECOMMENDED["anthropic"]
    stale = system.System(
        provider="anthropic",
        assistant_model=str(rec["assistant"]),
        assistant_thinking=rec["thinking"],
        classifier_model=str(rec["classifier"]),
        recommendation_seen=system.RECOMMENDED_REVISION - 1,
    )
    system.write_system(stale)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.stage == 1  # no modal
    seen = system.read_system()
    assert seen is not None and seen.recommendation_seen == system.RECOMMENDED_REVISION


@pytest.mark.usefixtures("stub_taxonomy_assistant")
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


@pytest.mark.usefixtures("stub_taxonomy_assistant")
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
        assert app.focused is not None and app.focused.id == "yes"
        box = modal.query_one(Vertical)
        assert panel_title(box)[0] == "Confirm" and box.outer_size.width == 58
        await pilot.press("enter")  # Approve is focused by default
        await pilot.pause()
        assert files.read_state().seeds_approved


def turns(panel) -> list[tuple[str, str]]:
    return [(line.kind, line.text) for line in panel.lines]


async def test_chat_panel_gutters_title_and_blank_rows(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    agent = Agent(TestModel(custom_output_text="hello there"))
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = ChatPanel("brief", agent)
        await app.screen.mount(panel)
        assert panel_title(panel)[0] == "chat · brief"
        assert panel_title(panel)[1] == "test"  # the model name
        panel.query_one("#chat-input", Input).focus()
        await pilot.press("h", "i", "enter", "y", "o", "enter")
        await pilot.pause(0.5)
        assert turns(panel) == [
            ("user", "hi"),
            ("assistant", "hello there"),
            ("user", "yo"),
            ("assistant", "hello there"),
        ]
        a, b, c, _ = panel.lines
        assert (b.region.y - a.region.bottom, c.region.y - b.region.bottom) == (1, 1)


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
                parts=[
                    ToolCallPart(
                        tool_name="propose_seeds",
                        args={"seeds": ["a"]},
                        tool_call_id="1",
                    )
                ]
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
        assert turns(panel) == [
            ("user", "find layoffs"),
            ("tool", "propose_seeds Added 6 seeds."),
            ("assistant", "Done."),
        ]
        user, tool, done = panel.lines
        assert tool.region.y == user.region.bottom  # no blank row before a tool line
        assert done.region.y - tool.region.bottom == 1


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
        assert turns(panel)[-1] == ("error", "Error: no key")


async def test_header_keeps_cost_warning_visible_at_80_columns(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        cost.record(
            "a-long-model-name", RunUsage(input_tokens=1, output_tokens=1), None
        )
        await pilot.pause(0.6)
        text = header_text(app)
        assert len(text) <= 80
        assert (
            "cost ? · no price for" in text
        )  # the warning survives, the models list may be cut


async def test_projects_and_system_settings_keys_work_from_a_stage(
    tmp_path, monkeypatch
):
    from textual.widgets import Input

    from hunches.screens.projects import ProjectsScreen
    from hunches.screens.system import SystemSettingsScreen

    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one(
            "#chat-input", Input
        ).focus()  # works with an Input focused
        await pilot.press("f4")
        await pilot.pause()
        assert isinstance(app.screen, ProjectsScreen)
        await pilot.press("p")  # Previous stage is not available over Projects
        await pilot.pause()
        assert isinstance(app.screen, ProjectsScreen) and app.stage == 1
        await pilot.press("f4")  # already open: no second copy
        await pilot.pause()
        assert len(app.screen_stack) == 3
        await pilot.press("f5")
        await pilot.pause()
        assert isinstance(app.screen, SystemSettingsScreen)
        await pilot.press("f5")
        await pilot.pause()
        assert len(app.screen_stack) == 4


async def test_projects_key_is_ignored_during_first_run_setup(tmp_path, monkeypatch):
    from hunches.screens.system import SystemSettingsScreen

    monkeypatch.chdir(tmp_path)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f4")
        await pilot.pause()
        assert isinstance(app.screen, SystemSettingsScreen)
        assert len(app.screen_stack) == 2


def test_main_loads_keyring_keys_into_the_environment(monkeypatch):
    import os

    from hunches import app as app_module
    from hunches import keys

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(app_module, "load_dotenv", lambda: None)
    seen = {}
    monkeypatch.setattr(
        HunchesApp,
        "run",
        lambda self: seen.update(key=os.environ.get("ANTHROPIC_API_KEY")),
    )
    keys.save("ANTHROPIC_API_KEY", "sk-sentinel")
    app_module.main()
    assert seen["key"] == "sk-sentinel"


async def test_opening_a_project_and_regaining_focus_sync_history(
    tmp_path, monkeypatch
):
    from textual import events

    from hunches import history

    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert [e["source"] for e in history.entries("seeds")] == ["baseline"]
        files.write_text("seeds.csv", "seed\nbar\n")  # an editor, a git checkout
        app.post_message(events.AppFocus())
        await pilot.pause()
        assert [e["source"] for e in history.entries("seeds")] == [
            "baseline",
            "external",
        ]
