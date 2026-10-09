import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar, Literal

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.markup import escape
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import Button, Footer, Input, Label, Static

from hunches import cost, files, history, keys, system
from hunches.theme import HUNCHES


class Placeholder(Screen):
    """Stand-in until a stage's real screen lands (tasks 09-17 replace it in STAGES)."""

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        yield Static(f"Stage {self.app.stage} is not implemented yet.")  # ty: ignore[unresolved-attribute]
        yield AppFooter()


def panel(widget, title: str, subtitle: str = ""):
    """Give a container the tinted panel look from hunches.tcss, with a one-row title line first.

    Title and subtitle are markup (a subtitle can carry a badge). Change them with `retitle`.
    """
    widget.add_class("panel")
    widget.compose_add_child(PanelTitle(title, subtitle))
    return widget


class PanelTitle(Horizontal):
    """Title left, subtitle right-aligned and muted. Also the first row of modals."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        self.title_text = Static(title, classes="panel-title")
        self.subtitle_text = Static(subtitle, classes="panel-subtitle")
        super().__init__(self.title_text, self.subtitle_text)


def modal_box(box, title: str):
    """Give a modal's container the shared look (hunches.tcss) with a primary title on its first row."""
    box.add_class("modal-box")
    box.compose_add_child(PanelTitle(title))
    return box


def retitle(widget, title: str | None = None, subtitle: str | None = None) -> None:
    """Change a `panel()`'s title and/or subtitle (markup); None leaves that one alone."""
    row = widget.query(PanelTitle).first()
    if title is not None:
        row.title_text.update(title)
    if subtitle is not None:
        row.subtitle_text.update(subtitle)


def say(widget: Static, text: str) -> None:
    """Set a message line; an empty one is hidden so no blank strip sits above the footer."""
    widget.update(text)
    widget.display = bool(text)


def key_button(label: str, key: str, **kwargs) -> Button:
    """A button whose label carries its key, e.g. "Approve seeds  F2"."""
    return Button(f"{label}  {key}", **kwargs)


class StageBanner(Static):
    """A full-width banner whose text a screen supplies (empty hides it).

    It asks again twice a second, so it follows undo, redo, outside edits and approvals without the
    screen wiring each of them. `warning` is the amber notice, otherwise the red STALE banner.
    """

    def __init__(
        self, text: Callable[[], str], warning: bool = False, **kwargs
    ) -> None:
        super().__init__(
            "",
            classes=f"banner {'-warning' if warning else '-stale'}",
            markup=False,
            **kwargs,
        )
        self.text = text
        self.display = False

    def on_mount(self) -> None:
        self.refresh_text()
        self.set_interval(0.5, self.refresh_text)

    def refresh_text(self) -> None:
        say(self, self.text())


def plan_hint() -> str:
    """The sentence that points at F9, while there is a plan to show."""
    return " F9 shows the redo plan." if marked(current_status()) else ""


RAIL_WIDTH = 26
RAIL_MIN = 100  # terminal columns from which the header becomes the left rail
DESTINATIONS = [
    ("Projects", "F4"),
    ("Project settings", "F3"),
    ("System settings", "F5"),
    ("History", "F8"),
]
# which destination the open screen is, by its stage_name
DESTINATION_OF = {
    "Projects": "Projects",
    "New project": "Projects",
    "Settings": "Project settings",
    "System settings": "System settings",
}
RAIL_ACTIONS = {
    "quit",
    "goto",
    "settings",
    "projects",
    "system_settings",
    "history",
    "redo_plan",
}
MARKS = {
    "stale": "↻",
    "incomplete": "◐",
}  # the stage statuses that get a mark; never colour alone
STATUS_AGE = (
    0.5  # seconds a stage_status result is reused: the rail and banners poll it
)
StageStatus = dict[int, tuple[files.Status, str]]
_STATUS: tuple[Path, float, StageStatus] | None = None


def current_status(fresh: bool = False) -> StageStatus:
    """`files.stage_status()`, reused for STATUS_AGE seconds unless `fresh` or the project changed.

    The rail and the stage banners ask several times a second; the status reads a handful of small
    files and scans results.jsonl once per change, which on a big project is worth not repeating.
    """
    global _STATUS
    now = time.monotonic()
    here = Path.cwd()
    last = _STATUS
    if fresh or last is None or last[0] != here or now - last[1] > STATUS_AGE:
        try:
            last = _STATUS = (here, now, files.stage_status())
        except (OSError, ValueError):  # a half-written file; look again next time
            if last is None or last[0] != here:
                return {n: ("not_started", "") for n in range(1, 10)}
    return last[2]


def marked(status: StageStatus) -> list[int]:
    """The stages with a stale or incomplete mark, in order."""
    return [n for n, (kind, _) in status.items() if kind in MARKS]


def wide(app) -> bool:
    """True when the terminal is wide enough for the left rail (works on any App, e.g. test hosts)."""
    return app.size.width >= RAIL_MIN


def markup(style: str, text: str) -> str:
    return f"[{style}]{text}[/]" if style else text


class AppFooter(Footer):
    """Footer that drops the keys the rail already shows and sits under the content column in rail mode."""

    rail = False

    def compose(self) -> ComposeResult:
        self.rail = wide(self.app)
        for widget in super().compose():
            action = getattr(widget, "action", "").split("(")[0]  # "goto(1)"
            if not (self.rail and action in RAIL_ACTIONS):
                yield widget

    def on_mount(self) -> None:
        self.fit()

    def fit(self) -> None:
        rail = wide(self.app)
        # Footer docks at the full screen width, so beside the rail it needs an explicit width
        self.styles.margin = (0, 0, 0, RAIL_WIDTH if rail else 0)
        self.styles.width = self.app.size.width - RAIL_WIDTH if rail else None
        if rail != self.rail:
            self.refresh(recompose=True)


class StatusHeader(Static):
    """Project, stage stepper and total cost; the left rail from 100 columns. Every stage screen must yield one first in compose()."""

    def on_mount(self) -> None:
        self.fit()
        # polling picks up cost.record() calls from anywhere, including worker threads
        self.set_interval(0.25, self.refresh_cost)

    def on_resize(self) -> None:
        self.refresh_cost()

    def fit(self) -> None:
        self.set_class(wide(self.app), "-rail")
        self.refresh_cost()

    def follow(self, status: StageStatus) -> None:
        """Tooltip with the reasons, and the footer when the set of marked stages changed."""
        tip = "\n".join(
            f"{n} {files.STAGE_NAMES[n - 1]} · {status[n][0].upper()}: {status[n][1]}"
            for n in marked(status)
        )
        if tip != (self.tooltip or ""):
            self.tooltip = tip or None
            self.screen.refresh_bindings()  # F9 appears and disappears with the marks

    def refresh_rail(self, stage: int) -> None:
        """Rail markup: stages and destinations at the top, cost at the bottom."""
        dollars, unknown = cost.total()
        self.set_class(bool(unknown), "-cost-unknown")
        screen_name = getattr(self.screen, "stage_name", None)
        here = DESTINATION_OF.get(screen_name or "")
        current = 0 if screen_name else stage  # an overlay screen: no stage is current

        def row(mark, mark_style, text, text_style, on=False, key=""):
            bg = "on $panel" if on else ""
            room = RAIL_WIDTH - 5 - (len(key) + 1 if key else 0)
            if len(text) > room:
                text = text[: room - 1] + "…"
            tail = markup(f"$text-disabled {bg}", f" {key}") if key else ""
            return "".join(
                (
                    markup(f"$primary {bg}", "▌" if on else " "),
                    markup(bg, " "),
                    markup(f"{mark_style} {bg}", mark),
                    markup(bg, " "),
                    markup(f"{text_style} {bg}", escape(text.ljust(room))),
                    tail,
                    markup(bg, " "),
                )
            )

        def plain(text, style):
            return "  " + markup(style, escape(text))

        project = Path.cwd().name
        if len(project) > RAIL_WIDTH - 3:
            project = project[: RAIL_WIDTH - 4] + "…"
        lines = [plain("hunches", "b $primary"), plain(project, "$text-muted"), ""]
        status = current_status()
        for num, label, _ in STAGES:
            mark = MARKS.get(status[num][0])
            if num == current:
                lines.append(
                    row(
                        mark or "●",
                        "$warning" if mark else "$primary",
                        label,
                        "b #EEF1F5",
                        on=True,
                    )
                )
            elif mark:
                lines.append(row(mark, "$warning", label, "$warning"))
            elif num < stage:
                lines.append(row("✓", "$success", label, "$text-muted"))
            else:
                lines.append(row("·", "$text-disabled", label, "$text-disabled"))
        kinds = [k for k in MARKS if any(status[n][0] == k for n in status)]
        if kinds:
            lines.append(
                plain("  ".join(f"{MARKS[k]} {k}" for k in kinds), "$text-muted")
            )
        lines.append("")
        for label, key in DESTINATIONS:
            if label == here:
                lines.append(row("▸", "$primary", label, "b #EEF1F5", on=True, key=key))
            else:
                # History is unavailable while an editor draft is open
                tone = (
                    "$text-disabled"
                    if label == "History" and getattr(self.screen, "editing", False)
                    else "$text-muted"
                )
                lines.append(row(" ", tone, label, tone, key=key))
        if kinds:
            lines.append(row(" ", "$warning", "↻ Redo plan", "$warning", key="F9"))
        bottom = [
            plain("n/p stage · q quit", "$text-disabled"),
            "",
            plain("cost", "$text-muted"),
        ]
        if unknown:
            models = [m for m, v in cost.breakdown().items() if v["dollars"] is None]
            bottom += [
                "  [b reverse $warning] cost ? [/]",
                plain("no price for", "$warning"),
            ]
            bottom += [plain(m[: RAIL_WIDTH - 3], "$warning") for m in models[:3]]
        else:
            bottom.append(plain(f"${dollars:.4f}", "b #EEF1F5"))
        gap = max(1, self.size.height - len(lines) - len(bottom))
        self.update("\n".join(lines + [""] * gap + bottom))

    def refresh_cost(self) -> None:
        stage = getattr(self.app, "stage", 0)
        name = next(
            (n for num, n, _ in STAGES if num == stage),
            getattr(
                self.screen, "stage_name", "Setup"
            ),  # non-stage screens name themselves
        )
        status = current_status()
        self.follow(status)
        if self.has_class("-rail"):
            return self.refresh_rail(stage)
        project = Path.cwd().name
        if len(project) > 16:
            project = project[:15] + "…"
        stepper = "".join(
            f"[$warning]{MARKS[status[num][0]]}[/]"
            if status[num][0] in MARKS
            else "[$text-disabled]○[/]"
            if num > stage
            else "[$primary]◉[/]"
            if num == stage
            else "[$text-muted]●[/]"
            for num, _, _ in STAGES
        )
        kind = status[stage][0] if stage else ""
        badge = f" [b reverse $warning] {kind.upper()} [/]" if kind in MARKS else ""

        def left(with_name: bool, with_badge: bool = True) -> tuple[str, int]:
            """Markup and plain length of everything left of the cost."""
            text = f"[b $primary]hunches[/]  [#EEF1F5]{escape(project)}[/]  {stepper}"
            width = len(f"hunches  {project}  ") + len(STAGES)
            if stage:
                text += f"  [b $primary]{stage}[/][$text-disabled]/{len(STAGES)}[/]"
                width += len(f"  {stage}/{len(STAGES)}")
                if with_name:
                    text += f" {name}"
                    width += 1 + len(name)
                if badge and with_badge:
                    text += badge
                    width += 3 + len(kind)
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
        # the stage name goes first, then (an unknown price can be cut to 24 cells) the badge
        markup, width = left(True)
        if room and width + 2 + len(right_plain) > room:
            markup, width = left(False)
        if room and width + 2 + (24 if unknown else len(right_plain)) > room:
            markup, width = left(False, False)
        if unknown and room and width + 2 + len(right_plain) > room:
            right_plain = right_plain[: max(24, room - width - 2) - 2] + "… "
        if unknown:
            right = f"[b reverse $warning]{escape(right_plain)}[/]"
        else:
            right = f"[$text-muted]cost[/] [b #EEF1F5]${dollars:.4f}[/]"
        pad = max(2, room - width - len(right_plain))
        self.update(markup + " " * pad + right)


class ConfirmScreen(ModalScreen[bool]):
    AUTO_FOCUS = "#yes"

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with modal_box(Vertical(), "Confirm"):
            yield Label(self.question)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="no")
                yield Button("Approve", id="yes", variant="success")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


def confirm_approve(
    screen: Screen, flag: str, stage: int, question: str, summary: str, then=None
) -> None:
    """Ask the user; if they approve, `files.approve` the `flag` (a files.State field) and call `then()`."""

    def done(approved: bool | None) -> None:
        if approved:
            files.approve(flag, stage, summary)
            if then:
                then()

    screen.app.push_screen(ConfirmScreen(question), done)


TURN_KINDS = ("context", "update", "edit")  # ModelRequest.metadata["hunches"]
BADGES = {
    "edit": "[b reverse $primary] YOU EDITED [/]",
    "update": "[b reverse $secondary] UPDATED [/]",
}
MAX_BODY_ROWS = 12


class ChatLine(Horizontal):
    """One text turn: a coloured gutter and the text wrapping beside it. Errors have no gutter."""

    def __init__(self, kind: str, text: str = "", **kwargs) -> None:
        self.kind = kind
        self.text = text
        gutter = {"user": "›", "assistant": "│"}.get(kind, "")
        super().__init__(
            Static(gutter, classes="gutter"),
            Static(text, markup=False, classes="body"),
            classes=f"turn chat-{kind}",
            **kwargs,
        )

    def set(self, text: str) -> None:
        self.text = text
        self.query_one(".body", Static).update(text)
        self.display = bool(text)


def body_content(body: str, rows: int | None = None) -> Content:
    """A message body as text: `# ` headings bold, long bodies cut to `rows` lines with a count."""
    lines = body.split("\n")
    shown = lines if rows is None else lines[:rows]
    parts: list = []
    for line in shown:
        if parts:
            parts.append("\n")
        parts.append((line[2:], "bold") if line.startswith("# ") else line)
    if len(shown) < len(lines):
        parts.append(f"\n… {len(lines) - len(shown)} more lines")
    return Content.assemble(*parts)


class FoldLine(Vertical):
    """A tool call (`↳ name  summary  ▸`) or a context/update/edit message (`◇ [badge] summary ▸`); click to open."""

    def __init__(
        self,
        kind: str,
        summary: str,
        detail: str,
        tool: str = "",
        rows: int | None = None,
    ) -> None:
        super().__init__(classes=f"turn fold fold-{kind}")
        self.kind = kind
        self.tool = tool
        self.summary = " ".join(
            summary.split()
        )  # one row; the CSS clips it with an ellipsis
        self.rows = rows
        self.expanded = False
        self.detail = Static(body_content(detail, rows), classes="detail")
        self.detail.display = False
        self.summary_text = Static(self.summary, classes="summary", markup=False)
        self.toggle_mark = Static("▸", classes="toggle")

    @property
    def text(self) -> str:
        return f"{self.tool} {self.summary}" if self.tool else self.summary

    def compose(self) -> ComposeResult:
        with Horizontal(classes="head"):
            yield Static("↳" if self.kind == "tool" else "◇", classes="gutter")
            if self.tool:
                yield Static(self.tool, classes="name", markup=False)
            if self.kind in BADGES:
                yield Static(BADGES[self.kind], classes="badge")
            yield self.summary_text
            yield self.toggle_mark
        yield self.detail

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self.detail.display = self.expanded
        self.toggle_mark.update("▾" if self.expanded else "▸")

    def on_click(self) -> None:
        self.toggle()

    def set_result(self, summary: str, detail: str) -> None:
        self.summary = " ".join(summary.split())
        self.summary_text.update(self.summary)
        self.detail.update(body_content(detail, self.rows))


def tool_line(call: ToolCallPart, result: ToolReturnPart | None) -> FoldLine:
    line = FoldLine("tool", "…", "", tool=call.tool_name)
    line.set_result(*tool_texts(call, result))
    return line


def tool_texts(call: ToolCallPart, result: ToolReturnPart | None) -> tuple[str, str]:
    """(summary, expanded block) of a tool call; no result yet is a running call."""
    args = json.dumps(call.args_as_dict(), indent=2, ensure_ascii=False)
    if result is None:
        return "…", f"# Arguments\n{args}"
    return str(result.content), f"# Arguments\n{args}\n\n# Result\n{result.content}"


class ChatPanel(Vertical):
    """Scrolling turns (one widget each) + a one-row Input and send button; persists history to chat/<stage>.json.

    The agent should see the current files on every run: register `@agent.instructions` on it, returning
    the state read fresh (it is evaluated per run, and never persisted: `files.save_chat` clears it).
    """

    DEFAULT_CSS = """
    ChatPanel #messages { height: 1fr; padding: 0 1 1 1; }
    ChatPanel #empty { height: 1fr; content-align: center middle; text-align: center; }
    ChatPanel .turn { height: auto; margin-top: 1; }
    ChatPanel .turn.first, ChatPanel .fold-tool { margin-top: 0; }
    ChatPanel #chat-row { height: 1; }
    """

    class Submitted(Message):
        """The user sent `text` (also posted when the chat itself answers it)."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class Changed(Message):
        """A turn started or finished (`running` flipped)."""

    def __init__(self, stage: str, agent: Agent, empty: str = "") -> None:
        super().__init__()
        self.card_for: Callable[[ToolCallPart], Widget | None] | None = None
        self.stage = stage
        self.agent = agent
        self.empty = empty
        self.history = files.load_chat(stage)
        self.running = False
        model = agent.model
        panel(
            self,
            f"chat · {stage}",
            model if isinstance(model, str) else getattr(model, "model_name", "?"),
        )

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="messages"):
            yield Static(self.empty, id="empty")
            yield ChatLine("assistant", id="live")  # the reply being streamed
        with Horizontal(id="chat-row"):
            yield Input(placeholder="Message the assistant", id="chat-input")
            yield Button("↑", id="send", variant="primary", disabled=True)

    async def on_mount(self) -> None:
        self.query_one(
            "#messages"
        ).anchor()  # stay at the bottom unless the user scrolls up
        self.query_one("#live").display = False
        await self.write_messages(self.history)  # restore a resumed conversation

    @property
    def lines(self) -> list:
        return [
            w
            for w in self.query_one("#messages").children
            if "turn" in w.classes and w.id != "live"
        ]

    async def add(self, line) -> None:
        if not self.lines:
            line.add_class("first")
            self.query_one("#empty").display = False
        await self.query_one("#messages").mount(line, before="#live")

    async def write_messages(self, messages: list, users: bool = True) -> None:
        """Mount a widget per turn. Restoring history and showing a live turn both come through here."""
        results = {
            part.tool_call_id: part
            for m in messages
            if isinstance(m, ModelRequest)
            for part in m.parts
            if isinstance(part, ToolReturnPart)
        }
        for message in messages:
            kind = (getattr(message, "metadata", None) or {}).get("hunches")
            if isinstance(message, ModelRequest) and kind in TURN_KINDS:
                text = "\n".join(
                    str(p.content)
                    for p in message.parts
                    if isinstance(p, UserPromptPart)
                )
                summary = (message.metadata or {}).get("summary") or next(
                    (ln for ln in text.split("\n") if ln and not ln.startswith("#")),
                    kind,
                )
                await self.add(FoldLine(kind, summary, text, rows=MAX_BODY_ROWS))
                continue
            for part in message.parts:
                if isinstance(part, UserPromptPart) and users:
                    await self.add(ChatLine("user", str(part.content)))
                elif isinstance(part, TextPart):
                    await self.add(ChatLine("assistant", part.content))
                elif isinstance(part, ToolCallPart):
                    await self.add(tool_line(part, results.get(part.tool_call_id)))
                    card = self.card_for(part) if self.card_for else None
                    if card:  # e.g. a proposal card under its tool line
                        await self.add(card)
        if not self.empty and not self.lines:
            self.query_one("#empty").display = False

    def sync_send(self) -> None:
        self.query_one("#send", Button).disabled = (
            self.running or not self.query_one("#chat-input", Input).value.strip()
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        self.sync_send()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()  # the screen hears ChatPanel.Submitted instead
        self.submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send":
            event.stop()
            self.submit()

    def submit(self) -> None:
        box = self.query_one("#chat-input", Input)
        text = box.value.strip()
        if text and not self.running:
            box.value = ""
            self.send(text)

    def send(self, text: str) -> None:
        """Send `text` as the user's turn (the typed message, or a canned one from a screen button)."""
        if self.running:
            return
        self.post_message(self.Submitted(text))
        self.run_worker(self.reply(text, show=True), exclusive=True)

    async def reply(self, text: str, show: bool = False) -> None:
        """One user turn. `show` mounts the user's line first (typed text; tests call reply() directly)."""
        if show:
            await self.add(ChatLine("user", text))
        await self.run_turn(text)

    async def send_context(
        self, text: str, kind: Literal["context", "update"], summary: str
    ) -> None:
        """Tell the agent something with a hidden user prompt; it answers, the chat shows a collapsed line."""
        await self.run_turn(text, tag={"hunches": kind, "summary": summary})

    def record(self, summary: str, body: str) -> None:
        """Remember a user edit for the agent's next turn. No model call."""
        message = files.edit_message(summary, body)
        self.history.append(message)
        files.save_chat(self.stage, self.history)
        self.run_worker(self.write_messages([message]))

    async def run_turn(self, text: str, tag: dict | None = None) -> None:
        box = self.query_one("#chat-input", Input)
        had_focus = box.has_focus
        self.running = True
        box.disabled = True
        self.sync_send()
        self.post_message(self.Changed())
        live = self.query_one("#live", ChatLine)
        running: dict[str, FoldLine] = {}

        async def on_events(_, events) -> None:
            async for event in events:
                if isinstance(event, FunctionToolCallEvent):
                    line = tool_line(event.part, None)
                    running[event.part.tool_call_id] = line
                    await self.add(line)
                elif isinstance(event, FunctionToolResultEvent) and isinstance(
                    event.part, ToolReturnPart
                ):
                    call = running.get(event.part.tool_call_id)
                    if call:
                        call.set_result(str(event.part.content), "")

        try:
            async with self.agent.run_stream(
                text, message_history=self.history, event_stream_handler=on_events
            ) as result:
                reply = ""
                async for delta in result.stream_text(delta=True):
                    reply += delta
                    live.set(reply)
                usage, new = result.usage, result.new_messages()
                # not all_messages(): it merges the consecutive edit lines before this turn and drops their metadata
                self.history = [*self.history, *new]
            if tag:
                new[0].metadata = tag
        except Exception as e:  # noqa: BLE001  network/auth errors should not kill the app
            live.set("")
            for line in running.values():
                await line.remove()
            await self.add(ChatLine("error", f"Error: {e}"))
            return
        finally:
            self.running = False
            box.disabled = False
            self.sync_send()
            self.post_message(self.Changed())
            if had_focus:
                box.focus()
        live.set("")
        for (
            line
        ) in running.values():  # redrawn from the messages, in order, with arguments
            await line.remove()
        await self.write_messages(new, users=False)
        files.save_chat(self.stage, self.history)
        model = self.agent.model
        name = model if isinstance(model, str) else getattr(model, "model_name", "?")
        cost.record(name, usage, cost.messages_dollars(new))


# Stage screens import ChatPanel/confirm_approve from this module, so they are imported here.
from hunches.screens.brief import BriefScreen
from hunches.screens.browse import BrowseScreen
from hunches.screens.final import test_stage
from hunches.screens.gold import GoldScreen
from hunches.screens.history import ExternalNotice, HistoryScreen
from hunches.screens.project_settings import ProjectSettingsScreen
from hunches.screens.projects import ProjectsScreen
from hunches.screens.redo_plan import RedoPlanScreen
from hunches.screens.run import RunScreen
from hunches.screens.search import SearchScreen
from hunches.screens.system import RecommendationModal, SystemSettingsScreen
from hunches.screens.taxonomy import TaxonomyScreen
from hunches.screens.threshold import ThresholdScreen
from hunches.screens.tune import TuneScreen

# (number, name, ScreenClass). Each stage task changes exactly one line here.
STAGES = [
    (1, files.STAGE_NAMES[0], BriefScreen),
    (2, files.STAGE_NAMES[1], SearchScreen),
    (3, files.STAGE_NAMES[2], TaxonomyScreen),
    (4, files.STAGE_NAMES[3], GoldScreen),
    (5, files.STAGE_NAMES[4], TuneScreen),
    (6, files.STAGE_NAMES[5], test_stage),
    (7, files.STAGE_NAMES[6], ThresholdScreen),
    (8, files.STAGE_NAMES[7], RunScreen),
    (9, files.STAGE_NAMES[8], BrowseScreen),
]


class HunchesApp(App):
    TITLE = "hunches"
    CSS_PATH = "hunches.tcss"
    BINDINGS: ClassVar = [
        ("q", "quit", "Quit"),
        ("n", "goto(1)", "Next stage"),
        ("p", "goto(-1)", "Previous stage"),
        ("f3", "settings", "Project settings"),
        ("f4", "projects", "Projects"),
        ("f5", "system_settings", "System settings"),
        ("f8", "history", "History"),
        ("f9", "redo_plan", "Redo plan"),
        # the screens bind F6 and F7 themselves; this one undoes an outside edit announced on any other screen
        Binding("f6", "undo_notice", "Undo", show=False),
        Binding("escape", "dismiss_notice", "Dismiss", show=False),
    ]

    stage = 0  # 1-9 once running
    stage_shown = False
    plan_active = False  # the user left the Redo plan with "Go to": reopen it after each re-approval
    plan_stages: tuple[int, ...] = ()  # the stages the plan listed then
    plan_done: tuple[int, ...] = ()  # of those, the ones approved again since
    seen = 0  # the highest history seq already checked for outside edits

    @property
    def rail(self) -> bool:
        """True when the terminal is wide enough for the left rail."""
        return wide(self)

    def on_resize(self) -> None:
        self.call_later(
            self.fit_rail
        )  # App._on_resize stores the new size after this handler

    def fit_rail(self) -> None:
        for screen in self.screen_stack:
            for widget in screen.query("StatusHeader, AppFooter"):
                widget.fit()  # ty: ignore[unresolved-attribute]

    def on_mount(self) -> None:
        self.register_theme(HUNCHES)
        self.theme = "hunches"
        current = system.read_system()
        if current is None:  # first run
            self.push_screen(SystemSettingsScreen(), lambda _: self.start())
        elif system.recommended_changed(current):
            self.push_screen(RecommendationModal(current), lambda _: self.start())
        else:
            self.start()

    def start(self) -> None:
        """Open the project in the current directory, or show Projects."""
        if (files.root() / "config.toml").exists():
            system.add_project(Path.cwd())
            self.open_project(Path.cwd())
            if self.stage:
                return
        self.push_screen(ProjectsScreen())

    def goto_stage(self, number: int) -> None:
        number = max(1, min(len(STAGES), number))
        self.stage = number
        screen = STAGES[number - 1][2]()
        if self.stage_shown:
            self.switch_screen(screen)
        else:
            self.stage_shown = True
            self.push_screen(screen)
        self.call_later(self.check_history)

    def open_project(self, path: str | Path) -> None:
        """Switch to the project at `path`. The only place that changes the working directory."""
        path = Path(path)
        status, detail = system.project_status(path)
        if status not in ("OK", "OK (s3 not checked)", "OK (pgvector not checked)"):
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
        self.seen = len(history.entries())  # what the sync below finds is news
        self.stage = 0
        while len(self.screen_stack) > 1:
            self.pop_screen()
        system.touch_project(path)
        self.stage_shown = False
        self.goto_stage(files.first_incomplete_stage())

    def on_app_focus(self) -> None:
        """An editor or git may have changed the three files while the terminal was in the background."""
        if self.stage:
            self.check_history()

    def base_screen(self) -> Screen:
        """The topmost screen that is not a modal."""
        return next(
            s for s in reversed(self.screen_stack) if not isinstance(s, ModalScreen)
        )

    def check_history(self) -> None:
        """Log outside edits (history.sync) and announce each new one once, on the screen the user is on."""
        history.sync()
        new = [e for e in history.entries() if e["seq"] > self.seen]
        self.seen = max([self.seen, *(e["seq"] for e in new)])
        screen = self.base_screen()
        again = [
            e["stage"]
            for e in new
            if e["kind"] == "approval" and e["stage"] in self.plan_stages
        ]
        if self.plan_active and not again and not marked(current_status(fresh=True)):
            self.plan_active, self.plan_done = (
                False,
                (),
            )  # nothing left to redo: the plan is over
        if self.plan_active and again:
            self.plan_done = (
                *self.plan_done,
                *(n for n in again if n not in self.plan_done),
            )
            self.open_plan()
        for entry in new:
            if entry["kind"] == "edit" and entry["source"] == "external":
                if moved := getattr(screen, "history_changed", None):
                    moved(entry)
                if screen.query(StatusHeader):
                    screen.mount(ExternalNotice(entry), before=0)

    def notices(self) -> list[ExternalNotice]:
        return list(self.base_screen().query(ExternalNotice))

    def action_undo_notice(self) -> None:
        self.notices()[0].undo()

    def action_dismiss_notice(self) -> None:
        for notice in self.notices():
            notice.remove()

    def action_redo_plan(self) -> None:
        self.open_plan()

    def open_plan(self) -> None:
        if not isinstance(self.screen, RedoPlanScreen):
            self.push_screen(
                RedoPlanScreen(list(self.plan_done) if self.plan_active else []),
                self.plan_closed,
            )

    def plan_closed(self, stage: int | None) -> None:
        """Close ends the plan; "Go to" starts (or continues) it and opens that stage."""
        if stage is None:
            self.plan_active, self.plan_done = False, ()
            return
        if not self.plan_active:
            self.plan_active, self.plan_done = True, ()
        self.plan_stages = tuple(marked(current_status(fresh=True)))
        self.goto_stage(stage)

    def action_history(self) -> None:
        """The History modal; not while an editor is open (its draft is not in the history)."""
        if self.check_action("history", ()):
            self.push_screen(HistoryScreen(), self.restored)

    def restored(self, result: tuple[dict, str] | None) -> None:
        """History restored a file: the screen underneath follows it."""
        screen = self.base_screen()
        if result and (moved := getattr(screen, "history_changed", None)):
            moved(*result)

    def action_settings(self) -> None:
        """Project settings of the open project (not on top of a modal or itself)."""
        if self.stage and not isinstance(
            self.screen, (ModalScreen, ProjectSettingsScreen)
        ):
            self.push_screen(ProjectSettingsScreen())

    def action_projects(self) -> None:
        """Not on a modal, over itself, or before first-run setup has written system.json."""
        if (
            not isinstance(self.screen, (ModalScreen, ProjectsScreen))
            and system.read_system()
        ):
            self.push_screen(ProjectsScreen())

    def action_system_settings(self) -> None:
        if (
            not isinstance(self.screen, (ModalScreen, SystemSettingsScreen))
            and system.read_system()
        ):
            self.push_screen(SystemSettingsScreen())

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ("history", "undo_notice", "dismiss_notice"):
            if isinstance(self.screen, ModalScreen) or not self.stage:
                return False
            if action == "history":
                return None if getattr(self.screen, "editing", False) else True
            notices = self.notices()
            return bool(notices) and (
                action == "dismiss_notice" or notices[0].can_undo()
            )
        if action == "redo_plan":  # stage screens only, and only with something to redo
            return (
                bool(self.stage)
                and not isinstance(self.screen, ModalScreen)
                and not hasattr(self.screen, "stage_name")
                and bool(marked(current_status()))
            )
        if (
            action == "goto"
        ):  # n/p mean nothing outside a project (Projects uses n for New)
            return self.stage > 0 and not isinstance(self.screen, ProjectsScreen)
        return True

    def action_goto(self, step: int) -> None:
        if self.stage and not isinstance(self.screen, ModalScreen):
            self.goto_stage(self.stage + step)


def main() -> None:
    load_dotenv()
    keys.load_into_env()
    HunchesApp().run()
