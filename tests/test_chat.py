import asyncio
import json
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.models.test import TestModel
from textual.app import App, ComposeResult
from textual.widgets import Button, Input

import hunches
from hunches import files
from hunches.app import ChatPanel, FoldLine


class Host(App):
    CSS_PATH = str(Path(hunches.__file__).parent / "hunches.tcss")

    def __init__(self, panel: ChatPanel) -> None:
        super().__init__()
        self.panel = panel
        self.submitted: list[str] = []

    def compose(self) -> ComposeResult:
        yield self.panel

    def on_chat_panel_submitted(self, event: ChatPanel.Submitted) -> None:
        self.submitted.append(event.text)


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def structure(panel: ChatPanel) -> list[tuple[str, str]]:
    """(kind, visible text) of every turn line, in order; the live reply line is not a turn."""
    return [(line.kind, line.text) for line in panel.lines]


def history_with_everything() -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content="find layoffs")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="propose_seeds",
                    args={"seeds": ["a", "b"]},
                    tool_call_id="1",
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="propose_seeds",
                    content="Added 2 seeds.",
                    tool_call_id="1",
                )
            ]
        ),
        ModelResponse(parts=[TextPart(content="Done.")]),
        files.edit_message("Seed 1 edited", "was: a\nnow: z\n\n# Current seeds\nz\nb"),
        ModelRequest(
            parts=[UserPromptPart(content="# State\nlots")],
            metadata={"hunches": "context", "summary": "Seeds and candidates"},
        ),
    ]


def agent_with(stream_function) -> Agent:
    return Agent(FunctionModel(stream_function=stream_function))


async def say_hello(messages, info: AgentInfo):
    yield "hello"


async def test_history_renders_every_kind_in_order_and_collapsed():
    files.save_chat("brief", history_with_everything())
    panel = ChatPanel("brief", agent_with(say_hello))
    async with Host(panel).run_test() as pilot:
        await pilot.pause()
        assert structure(panel) == [
            ("user", "find layoffs"),
            ("tool", "propose_seeds Added 2 seeds."),
            ("assistant", "Done."),
            ("edit", "Seed 1 edited"),
            ("context", "Seeds and candidates"),
        ]
        tool, edit, context = panel.lines[1], panel.lines[3], panel.lines[4]
        assert isinstance(tool, FoldLine)
        assert not tool.expanded and not edit.expanded and not context.expanded
        assert not tool.detail.display and not edit.detail.display
        assert "YOU EDITED" in str(edit.query_one(".badge").render())
        assert not context.query(".badge")  # plain context has no badge


async def test_expanding_shows_arguments_result_and_message_body():
    files.save_chat("brief", history_with_everything())
    panel = ChatPanel("brief", agent_with(say_hello))
    async with Host(panel).run_test() as pilot:
        await pilot.pause()
        tool = panel.query_one(".fold-tool", FoldLine)
        tool.toggle()
        await pilot.pause()
        assert tool.expanded and tool.detail.display
        shown = str(tool.detail.render())
        assert '"seeds"' in shown and '"a"' in shown and "Added 2 seeds." in shown
        edit = panel.query_one(".fold-edit", FoldLine)
        edit.toggle()
        await pilot.pause()
        body = str(edit.detail.render())
        assert body.startswith("What changed")  # heading marker dropped
        assert "was: a" in body and "Current seeds" in body


async def test_long_message_body_is_capped_at_12_lines():
    body = "\n".join(f"line {n}" for n in range(30))
    files.save_chat("brief", [files.edit_message("many", body)])
    panel = ChatPanel("brief", agent_with(say_hello))
    async with Host(panel).run_test() as pilot:
        await pilot.pause()
        line = panel.query_one(".fold-edit", FoldLine)
        line.toggle()
        await pilot.pause()
        lines = str(line.detail.render()).split("\n")
        assert len(lines) == 13
        assert lines[-1].startswith("… ") and "more lines" in lines[-1]
        # the message has 3 heading/instruction lines around the body: 30 + the rest - 12 shown
        total = len(files.edit_message("many", body).parts[0].content.split("\n"))  # ty: ignore[unresolved-attribute]
        assert lines[-1] == f"… {total - 12} more lines"


async def test_live_turns_build_the_same_structure_as_restored_history():
    async def stream(messages, info):
        if any(p.part_kind == "tool-return" for p in messages[-1].parts):
            yield "Done."
        else:
            yield {
                0: DeltaToolCall(
                    name="propose_seeds", json_args='{"seeds": ["a", "b"]}'
                )
            }

    agent = agent_with(stream)

    @agent.tool_plain
    def propose_seeds(seeds: list[str]) -> str:
        return f"Added {len(seeds)} seeds."

    panel = ChatPanel("brief", agent)
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        panel.query_one("#chat-input", Input).focus()
        panel.query_one("#chat-input", Input).value = "find layoffs"
        await pilot.press("enter")
        await pilot.pause(0.5)
        await host.workers.wait_for_complete()
        await pilot.pause()
        live = structure(panel)
    assert live == [
        ("user", "find layoffs"),
        ("tool", "propose_seeds Added 2 seeds."),
        ("assistant", "Done."),
    ]
    fresh = ChatPanel("brief", agent)
    async with Host(fresh).run_test() as pilot:
        await pilot.pause()
        assert structure(fresh) == live


async def test_running_tool_shows_ellipsis_then_the_result():
    gate = asyncio.Event()

    async def stream(messages, info):
        if any(p.part_kind == "tool-return" for p in messages[-1].parts):
            yield "Done."
        else:
            yield {0: DeltaToolCall(name="slow", json_args="{}")}

    agent = agent_with(stream)

    @agent.tool_plain
    async def slow() -> str:
        await gate.wait()
        return "finished"

    panel = ChatPanel("brief", agent)
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        panel.query_one("#chat-input", Input).focus()
        panel.query_one("#chat-input", Input).value = "go"
        await pilot.press("enter")
        await pilot.pause(0.3)
        tool = panel.query_one(".fold-tool", FoldLine)
        assert tool.text == "slow …"
        gate.set()
        await host.workers.wait_for_complete()
        await pilot.pause()
        assert [k for k, _ in structure(panel)] == ["user", "tool", "assistant"]
        assert structure(panel)[1][1] == "slow finished"


async def test_record_makes_no_model_call_persists_and_reaches_the_next_reply():
    calls: list[list] = []

    async def stream(messages, info):
        calls.append(messages)
        yield "ok"

    panel = ChatPanel("brief", agent_with(stream))
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        panel.record("Seed 1 edited", "was: a\nnow: z\n\n# Current seeds\nz")
        await pilot.pause()
        assert calls == []
        saved = files.load_chat("brief")
        assert len(saved) == 1 and saved[0].metadata == {
            "hunches": "edit",
            "summary": "Seed 1 edited",
        }
        content = str(saved[0].parts[0].content)  # ty: ignore[unresolved-attribute]
        assert content.startswith("# What changed\nSeed 1 edited\n")
        assert content.endswith(
            "# Instructions\nNo reply needed. Treat this as the current state in your next turn."
        )
        assert structure(panel) == [("edit", "Seed 1 edited")]
        panel.query_one("#chat-input", Input).focus()
        panel.query_one("#chat-input", Input).value = "next"
        await pilot.press("enter")
        await pilot.pause(0.5)
        await host.workers.wait_for_complete()
        assert len(calls) == 1
        sent = [
            p.content
            for m in calls[0]
            for p in m.parts
            if isinstance(p, UserPromptPart)
        ]
        assert sent[0].startswith("# What changed") and sent[-1] == "next"


def test_edit_message_shape():
    msg = files.edit_message("Seed added", "# Current seeds\n1. x")
    assert msg.metadata == {"hunches": "edit", "summary": "Seed added"}
    assert msg.parts[0].content == (  # ty: ignore[unresolved-attribute]
        "# What changed\nSeed added\n\n# Current seeds\n1. x\n\n"
        "# Instructions\nNo reply needed. Treat this as the current state in your next turn."
    )


async def test_send_context_is_tagged_persisted_and_restored_collapsed():
    seen: list[str] = []

    async def stream(messages, info):
        seen.append(messages[-1].parts[0].content)
        yield "noted"

    panel = ChatPanel("taxonomy", agent_with(stream))
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        await panel.send_context("# Seeds\nx\ny", "update", "Seeds: 1 added")
        await pilot.pause()
        assert seen == ["# Seeds\nx\ny"]
        assert structure(panel) == [
            ("update", "Seeds: 1 added"),
            ("assistant", "noted"),
        ]
        assert not panel.query_one(".fold-update", FoldLine).expanded
        assert "UPDATED" in str(panel.query_one(".fold-update .badge").render())
        before = structure(panel)
    saved = files.load_chat("taxonomy")
    assert saved[0].metadata == {"hunches": "update", "summary": "Seeds: 1 added"}
    fresh = ChatPanel("taxonomy", agent_with(stream))
    async with Host(fresh).run_test() as pilot:
        await pilot.pause()
        assert structure(fresh) == before
        assert not fresh.query_one(".fold-update", FoldLine).expanded


async def test_context_turn_records_cost():
    from hunches import cost

    panel = ChatPanel("taxonomy", Agent(TestModel(custom_output_text="hi")))
    async with Host(panel).run_test() as pilot:
        await pilot.pause()
        before = cost.breakdown().get("test", {"calls": 0})["calls"]
        await panel.send_context("ctx", "context", "Context")
        assert cost.breakdown()["test"]["calls"] == before + 1


async def test_instructions_are_evaluated_each_run_and_never_persisted():
    runs = []
    agent = Agent(TestModel(custom_output_text="ok"))

    @agent.instructions
    def state() -> str:
        runs.append(1)
        return f"CURRENT-STATE-{len(runs)}"

    panel = ChatPanel("brief", agent)
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        for text in ("one", "two"):
            panel.query_one("#chat-input", Input).focus()
            panel.query_one("#chat-input", Input).value = text
            await pilot.press("enter")
            await pilot.pause(0.3)
            await host.workers.wait_for_complete()
    assert len(runs) == 2
    raw = (files.root() / "chat" / "brief.json").read_text()
    assert "CURRENT-STATE" not in raw
    assert all(
        m["instructions"] is None for m in json.loads(raw) if "instructions" in m
    )


async def test_send_button_and_enter_behave_the_same_and_disable_correctly():
    gate = asyncio.Event()

    async def stream(messages, info):
        await gate.wait()
        yield "reply"

    panel = ChatPanel("brief", agent_with(stream))
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        send = panel.query_one("#send", Button)
        box = panel.query_one("#chat-input", Input)
        assert send.disabled  # empty
        box.focus()
        box.value = "via enter"
        await pilot.pause()
        assert not send.disabled
        await pilot.press("enter")  # focus is on the input after mount
        await pilot.pause(0.2)
        assert host.submitted == ["via enter"] and box.value == ""
        assert send.disabled and box.disabled  # streaming
        gate.set()
        await host.workers.wait_for_complete()
        await pilot.pause()
        assert not box.disabled
        box.value = "via button"
        await pilot.pause()
        await pilot.click("#send")
        await pilot.pause(0.3)
        await host.workers.wait_for_complete()
        assert host.submitted == ["via enter", "via button"] and box.value == ""
        assert [k for k, _ in structure(panel)] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]


async def test_empty_state_shows_until_the_first_turn():
    panel = ChatPanel("brief", agent_with(say_hello), empty="Describe what to find")
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        empty = panel.query_one("#empty")
        assert empty.display and str(empty.render()) == "Describe what to find"
        panel.query_one("#chat-input", Input).focus()
        panel.query_one("#chat-input", Input).value = "hi"
        await pilot.press("enter")
        await pilot.pause(0.3)
        await host.workers.wait_for_complete()
        assert not empty.display


async def test_error_line_and_no_record_of_failed_turn():
    agent = Agent(TestModel())

    def boom(*a, **k):
        raise RuntimeError("no key")

    agent.run_stream = boom  # ty: ignore[invalid-assignment]
    panel = ChatPanel("brief", agent)
    host = Host(panel)
    async with host.run_test() as pilot:
        await pilot.pause()
        panel.query_one("#chat-input", Input).focus()
        panel.query_one("#chat-input", Input).value = "h"
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert structure(panel)[-1] == ("error", "Error: no key")
        assert not panel.query_one("#chat-input", Input).disabled
