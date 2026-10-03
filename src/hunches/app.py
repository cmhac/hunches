import os
from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.messages import TextPart, ToolReturnPart, UserPromptPart
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Input, Label, RichLog, Select, Static

from hunches import cost, files, system
from hunches.theme import HUNCHES


class Placeholder(Screen):
    """Stand-in until a stage's real screen lands (tasks 09-17 replace it in STAGES)."""

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        yield Static(f"Stage {self.app.stage} is not implemented yet.")  # ty: ignore[unresolved-attribute]
        yield Footer()


def panel(widget, title: str, subtitle: str = ""):
    """Give a container the bordered, titled look from hunches.tcss."""
    widget.add_class("panel")
    widget.border_title = title
    widget.border_subtitle = subtitle
    return widget


class StatusHeader(Static):
    """Project, stage stepper and total cost. Every stage screen must yield one first in compose()."""

    def on_mount(self) -> None:
        self.refresh_cost()
        # polling picks up cost.record() calls from anywhere, including worker threads
        self.set_interval(0.25, self.refresh_cost)

    def on_resize(self) -> None:
        self.refresh_cost()

    def refresh_cost(self) -> None:
        stage = getattr(self.app, "stage", 0)
        name = next(
            (n for num, n, _ in STAGES if num == stage),
            getattr(
                self.screen, "stage_name", "Setup"
            ),  # non-stage screens name themselves
        )
        project = Path.cwd().name
        if len(project) > 16:
            project = project[:15] + "…"
        stepper = "".join(
            "[$text-disabled]○[/]"
            if num > stage
            else "[$primary]◉[/]"
            if num == stage
            else "[$text-muted]●[/]"
            for num, _, _ in STAGES
        )

        def left(with_name: bool) -> tuple[str, int]:
            """Markup and plain length of everything left of the cost."""
            text = f"[b $primary]hunches[/]  [#EEF1F5]{escape(project)}[/]  {stepper}"
            width = len(f"hunches  {project}  ") + len(STAGES)
            if stage:
                text += f"  [b $primary]{stage}[/][$text-disabled]/{len(STAGES)}[/]"
                width += len(f"  {stage}/{len(STAGES)}")
                if with_name:
                    text += f" {name}"
                    width += 1 + len(name)
            elif with_name:
                text += f"  {name}"
                width += 2 + len(name)
            return text, width

        dollars, unknown = cost.total()
        self.set_class(bool(unknown), "-cost-unknown")
        if unknown:
            # never show $0 (or a bare lower bound) for an unknown price
            models = [m for m, v in cost.breakdown().items() if v["dollars"] is None]
            right_plain = f" cost ? · no price for {', '.join(models)} "
        else:
            right_plain = f"cost ${dollars:.4f}"
        room = self.size.width - 2  # padding; 0 before the first layout
        markup, width = left(True)
        if room and width + 2 + len(right_plain) > room:
            markup, width = left(False)  # drop the stage name first
        if unknown and room and width + 2 + len(right_plain) > room:
            right_plain = right_plain[: max(24, room - width - 2) - 2] + "… "
        if unknown:
            right = f"[b reverse $warning]{escape(right_plain)}[/]"
        else:
            right = f"[$text-muted]cost[/] [b #EEF1F5]${dollars:.4f}[/]"
        pad = max(2, room - width - len(right_plain))
        self.update(markup + " " * pad + right)


class SetupScreen(Screen):
    """First run: write .hunches/config.toml."""

    DEFAULT_CSS = """
    SetupScreen #config { height: auto; }
    SetupScreen .row { height: 1; }
    SetupScreen .row Label { width: 16; color: $text-muted; }
    SetupScreen .row Input, SetupScreen .row Select { width: 1fr; }
    SetupScreen .gap { height: 1; }
    SetupScreen #actions { height: 1; margin-top: 1; }
    SetupScreen #save { width: 10; }
    SetupScreen #error { margin-left: 2; }
    """

    def compose(self) -> ComposeResult:
        c = files.Config()
        yield StatusHeader()
        yield Static("Set up hunches (writes .hunches/config.toml)", classes="note")
        with panel(Vertical(id="config"), "config.toml"):
            with Horizontal(classes="row"):
                yield Label("backend")
                yield Select(
                    [("Local (numpy)", "local"), ("S3 Vectors", "s3")],
                    value="local",
                    allow_blank=False,
                    compact=True,
                    id="backend",
                )
            yield Static("", classes="gap")
            for id_, placeholder in [
                ("corpus_dir", "local: corpus directory"),
                ("s3_bucket", "s3: bucket"),
                ("s3_index", "s3: index"),
            ]:
                yield self.field(
                    id_, Input(placeholder=placeholder, compact=True, id=id_)
                )
            yield Static("", classes="gap")
            yield self.field(
                "embedding_model",
                Input(
                    placeholder="e.g. openai:text-embedding-3-small",
                    compact=True,
                    id="embedding_model",
                ),
            )
            yield self.field(
                "assistant_model",
                Input(value=c.assistant_model, compact=True, id="assistant_model"),
            )
            yield self.field(
                "classifier_model",
                Input(value=c.classifier_model, compact=True, id="classifier_model"),
            )
        with Horizontal(id="actions"):
            yield Button("Save", id="save", variant="primary", compact=True)
            yield Label("", id="error", classes="error")
        yield Footer()

    def field(self, name: str, widget: Input) -> Horizontal:
        return Horizontal(Label(name), widget, classes="row")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        value = lambda i: self.query_one(f"#{i}", Input).value.strip()
        backend = self.query_one("#backend", Select).value
        data = {
            "backend": backend,
            "corpus_dir": value("corpus_dir") or None,
            "s3_bucket": value("s3_bucket") or None,
            "s3_index": value("s3_index") or None,
            "embedding_model": value("embedding_model"),
            "assistant_model": value("assistant_model"),
            "classifier_model": value("classifier_model"),
        }
        needed = ["corpus_dir"] if backend == "local" else ["s3_bucket", "s3_index"]
        missing = [k for k in [*needed, "embedding_model"] if not data[k]]
        if missing:
            self.query_one("#error", Label).update(f"Required: {', '.join(missing)}")
            return
        files.write_config(files.Config.model_validate(data))
        self.dismiss()


class ConfirmScreen(ModalScreen[bool]):
    AUTO_FOCUS = "#yes"

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical() as box:
            box.border_title = "Confirm"
            yield Label(self.question)
            with Horizontal():
                yield Button("Cancel", id="no")
                yield Button("Approve", id="yes", variant="success")

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
        self.turns = 0
        model = agent.model
        panel(
            self,
            f"chat · {stage}",
            model if isinstance(model, str) else getattr(model, "model_name", "?"),
        )

    def compose(self) -> ComposeResult:
        yield RichLog(wrap=True, markup=False, id="log")
        yield Static("", id="live")  # the reply being streamed
        yield Input(placeholder="Message the assistant", id="chat-input")

    def on_mount(self) -> None:
        self.write_messages(self.history)  # restore a resumed conversation

    def say(self, gutter: str, color: str, text: str) -> None:
        """One chat turn: a coloured gutter, the text wrapping beside it, a blank row before every turn but the first."""
        if self.turns:
            self.query_one("#log", RichLog).write("")
        self.turns += 1
        if not gutter:  # errors
            self.query_one("#log", RichLog).write(Text(text, style=color))
            return
        grid = Table.grid()
        grid.add_column(width=2)
        grid.add_column(ratio=1)
        grid.add_row(Text(gutter, style=color), Text(text))
        self.query_one("#log", RichLog).write(grid, expand=True)

    def write_messages(self, messages: list, users: bool = True) -> None:
        theme = self.app.current_theme
        for message in messages:
            for part in message.parts:
                if isinstance(part, UserPromptPart) and users:
                    self.say("› ", theme.primary, str(part.content))
                elif isinstance(part, TextPart):
                    self.say("│ ", theme.accent or "", part.content)
                elif isinstance(part, ToolReturnPart):
                    muted = theme.variables["text-muted"]
                    self.say("↳ ", muted, f"{part.tool_name} · {part.content}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        self.say("› ", self.app.current_theme.primary, text)
        self.run_worker(self.reply(text), exclusive=True)

    async def reply(self, text: str) -> None:
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
            self.say("", self.app.current_theme.error or "", f"Error: {e}")
            return
        live.update("")
        self.write_messages(new, users=False)
        files.save_chat(self.stage, self.history)
        model = self.agent.model
        name = model if isinstance(model, str) else getattr(model, "model_name", "?")
        cost.record(name, usage, cost.messages_dollars(new))


# Stage screens import ChatPanel/confirm_approve from this module, so they are imported here.
from hunches.screens.brief import BriefScreen
from hunches.screens.browse import BrowseScreen
from hunches.screens.final import test_stage
from hunches.screens.gold import GoldScreen
from hunches.screens.run import RunScreen
from hunches.screens.search import SearchScreen
from hunches.screens.taxonomy import TaxonomyScreen
from hunches.screens.threshold import ThresholdScreen
from hunches.screens.tune import TuneScreen

# (number, name, ScreenClass). Each stage task changes exactly one line here.
STAGES = [
    (1, "Brief and seeds", BriefScreen),
    (2, "Search", SearchScreen),
    (3, "Taxonomy and prompt", TaxonomyScreen),
    (4, "Gold dev set", GoldScreen),
    (5, "Tuning loop", TuneScreen),
    (6, "Gold test set", test_stage),
    (7, "Threshold", ThresholdScreen),
    (8, "Full run", RunScreen),
    (9, "Browse", BrowseScreen),
]


class HunchesApp(App):
    TITLE = "hunches"
    CSS_PATH = "hunches.tcss"
    BINDINGS: ClassVar = [
        ("q", "quit", "Quit"),
        ("n", "goto(1)", "Next stage"),
        ("p", "goto(-1)", "Previous stage"),
    ]

    stage = 0  # 1-9 once running
    stage_shown = False

    def on_mount(self) -> None:
        self.register_theme(HUNCHES)
        self.theme = "hunches"
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

    def open_project(self, path: str | Path) -> None:
        """Switch to the project at `path`. The only place that changes the working directory."""
        path = Path(path)
        status, detail = system.project_status(path)
        if status not in ("OK", "OK (s3 not checked)"):
            self.notify(f"Cannot open {path.name}: {status} {detail}", severity="error")
            return
        if any(w.is_running for w in self.workers):
            self.push_screen(
                ConfirmScreen("A run is in progress; stop it and switch?"),
                lambda stop: stop and self.switch_to(path),
            )
        else:
            self.switch_to(path)

    def switch_to(self, path: Path) -> None:
        try:
            os.chdir(path)
        except OSError as e:
            self.notify(f"Cannot open {path.name}: {e}", severity="error")
            return
        self.workers.cancel_all()
        self.stage = 0
        while len(self.screen_stack) > 1:
            self.pop_screen()
        system.touch_project(path)
        self.stage_shown = False
        self.goto_stage(files.first_incomplete_stage())

    def action_goto(self, step: int) -> None:
        if self.stage and not isinstance(self.screen, ModalScreen):
            self.goto_stage(self.stage + step)


def main() -> None:
    load_dotenv()
    HunchesApp().run()
