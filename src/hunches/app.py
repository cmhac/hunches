from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.messages import TextPart, UserPromptPart
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Input, Label, RichLog, Select, Static

from hunches import cost, files


class Placeholder(Screen):
    """Stand-in until a stage's real screen lands (tasks 09-17 replace it in STAGES)."""

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        yield Static(f"Stage {self.app.stage} is not implemented yet.")  # ty: ignore[unresolved-attribute]
        yield Footer()


class StatusHeader(Static):
    """Project, stage and total cost. Every stage screen must yield one first in compose()."""

    DEFAULT_CSS = """
    StatusHeader { dock: top; height: 1; background: $primary; color: $text; padding: 0 1; }
    """

    def on_mount(self) -> None:
        self.refresh_cost()
        # polling picks up cost.record() calls from anywhere, including worker threads
        self.set_interval(0.25, self.refresh_cost)

    def refresh_cost(self) -> None:
        stage = getattr(self.app, "stage", 0)
        name = next((n for num, n, _ in STAGES if num == stage), "Setup")
        dollars, unknown = cost.total()
        text = f"hunches: {Path.cwd().name} | Stage {stage}/{len(STAGES)}: {name} | "
        if unknown:
            # never show $0 (or a bare lower bound) for an unknown price
            unknown_models = [
                m for m, v in cost.breakdown().items() if v["dollars"] is None
            ]
            text += f"cost ? [b reverse] WARNING: cost unknown for {', '.join(unknown_models)} [/]"
        else:
            text += f"cost ${dollars:.4f}"
        self.update(text)


class SetupScreen(Screen):
    """First run: write .hunches/config.toml."""

    def compose(self) -> ComposeResult:
        c = files.Config()
        yield StatusHeader()
        with Vertical():
            yield Label("Set up hunches (writes .hunches/config.toml)")
            yield Select(
                [("Local (numpy)", "local"), ("S3 Vectors", "s3")],
                value="local",
                allow_blank=False,
                id="backend",
            )
            yield Input(placeholder="local: corpus directory", id="corpus_dir")
            yield Input(placeholder="s3: bucket", id="s3_bucket")
            yield Input(placeholder="s3: index", id="s3_index")
            yield Input(
                placeholder="embedding model (e.g. openai:text-embedding-3-small)",
                id="embedding_model",
            )
            yield Input(value=c.smart_model, id="smart_model")
            yield Input(value=c.cheap_model, id="cheap_model")
            yield Button("Save", id="save")
            yield Label("", id="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        value = lambda i: self.query_one(f"#{i}", Input).value.strip()
        backend = self.query_one("#backend", Select).value
        data = {
            "backend": backend,
            "corpus_dir": value("corpus_dir") or None,
            "s3_bucket": value("s3_bucket") or None,
            "s3_index": value("s3_index") or None,
            "embedding_model": value("embedding_model"),
            "smart_model": value("smart_model"),
            "cheap_model": value("cheap_model"),
        }
        needed = ["corpus_dir"] if backend == "local" else ["s3_bucket", "s3_index"]
        missing = [k for k in [*needed, "embedding_model"] if not data[k]]
        if missing:
            self.query_one("#error", Label).update(f"Required: {', '.join(missing)}")
            return
        files.write_config(files.Config.model_validate(data))
        self.dismiss()


class ConfirmScreen(ModalScreen[bool]):
    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.question)
            with Horizontal():
                yield Button("Approve", id="yes", variant="success")
                yield Button("Cancel", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


def confirm_approve(screen: Screen, flag: str, question: str, then=None) -> None:
    """Ask the user; if they approve, set `flag` (a files.State field) in state.json and call `then()`."""

    def done(approved: bool | None) -> None:
        if approved:
            state = files.read_state()
            setattr(state, flag, True)
            files.write_state(state)
            if then:
                then()

    screen.app.push_screen(ConfirmScreen(question), done)


class ChatPanel(Vertical):
    """RichLog + Input. Streams the agent's reply and persists history to chat/<stage>.json."""

    DEFAULT_CSS = (
        "ChatPanel RichLog { height: 1fr; } ChatPanel Static { height: auto; }"
    )

    def __init__(self, stage: str, agent: Agent) -> None:
        super().__init__()
        self.stage = stage
        self.agent = agent
        self.history = files.load_chat(stage)

    def compose(self) -> ComposeResult:
        yield RichLog(wrap=True, markup=False, id="log")
        yield Static("", id="live")  # the reply being streamed
        yield Input(placeholder="Message the assistant", id="chat-input")

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        for message in self.history:  # restore a resumed conversation
            for part in message.parts:
                if isinstance(part, UserPromptPart):
                    log.write(f"> {part.content}")
                elif isinstance(part, TextPart):
                    log.write(part.content)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        self.query_one("#log", RichLog).write(f"> {text}")
        self.run_worker(self.reply(text), exclusive=True)

    async def reply(self, text: str) -> None:
        log = self.query_one("#log", RichLog)
        live = self.query_one("#live", Static)
        try:
            async with self.agent.run_stream(
                text, message_history=self.history
            ) as result:
                reply = ""
                async for delta in result.stream_text(delta=True):
                    reply += delta
                    live.update(reply)
                usage, new = result.usage, result.new_messages()
                self.history = result.all_messages()
        except Exception as e:  # noqa: BLE001  network/auth errors should not kill the app
            live.update("")
            log.write(f"Error: {e}")
            return
        live.update("")
        log.write(reply)
        files.save_chat(self.stage, self.history)
        model = self.agent.model
        name = model if isinstance(model, str) else getattr(model, "model_name", "?")
        cost.record(name, usage, cost.messages_dollars(new))


# Stage screens import ChatPanel/confirm_approve from this module, so they are imported here.
from hunches.screens.brief import BriefScreen

# (number, name, ScreenClass). Each stage task changes exactly one line here.
STAGES = [
    (1, "Brief and seeds", BriefScreen),
    (2, "Search", Placeholder),
    (3, "Taxonomy and prompt", Placeholder),
    (4, "Gold dev set", Placeholder),
    (5, "Tuning loop", Placeholder),
    (6, "Gold test set", Placeholder),
    (7, "Threshold", Placeholder),
    (8, "Full run", Placeholder),
    (9, "Browse", Placeholder),
]


class HunchesApp(App):
    TITLE = "hunches"
    BINDINGS: ClassVar = [
        ("q", "quit", "Quit"),
        ("n", "goto(1)", "Next stage"),
        ("p", "goto(-1)", "Previous stage"),
    ]

    stage = 0  # 1-9 once running
    stage_shown = False

    def on_mount(self) -> None:
        if (files.root() / "config.toml").exists():
            self.goto_stage(files.first_incomplete_stage())
        else:
            self.push_screen(SetupScreen(), lambda _: self.goto_stage(1))

    def goto_stage(self, number: int) -> None:
        number = max(1, min(len(STAGES), number))
        self.stage = number
        screen = STAGES[number - 1][2]()
        if self.stage_shown:
            self.switch_screen(screen)
        else:
            self.stage_shown = True
            self.push_screen(screen)

    def action_goto(self, step: int) -> None:
        if self.stage and not isinstance(self.screen, ModalScreen):
            self.goto_stage(self.stage + step)


def main() -> None:
    load_dotenv()
    HunchesApp().run()
