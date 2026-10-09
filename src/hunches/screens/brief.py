import csv
import io
from typing import ClassVar
from uuid import uuid4

from pydantic_ai import Agent
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Input, Static

from hunches import candidates, files, history
from hunches.app import (
    AppFooter,
    ChatPanel,
    StatusHeader,
    confirm_approve,
    key_button,
    panel,
    retitle,
)

INSTRUCTIONS = """\
You help the user define what to find in a corpus of text items. Ask short follow-up \
questions until the brief is clear. Then call propose_seeds with seed phrases: statements \
that would be true of a matching item (e.g. "The author describes being laid off"). \
Proposals are appended to the user's seed table, which they review, so do not repeat \
seeds already proposed.
"""


def write_seeds(
    seeds: list[str],
    source: str = "user",
    summary: str = "",
    group: str | None = None,
) -> None:
    """Write seeds.csv in the format candidates.read_seeds() reads: a `seed` header, one per row."""
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows([["seed"], *([s] for s in seeds)])
    history.save("seeds", out.getvalue(), source, summary, group)


class SeedInput(Input):
    """The editor of one seed row. `seed_index` is None for a new seed."""

    def __init__(self, seed_index: int | None, value: str, was: str) -> None:
        super().__init__(value, placeholder="Type a seed phrase")
        self.seed_index = seed_index
        self.was = was


class SeedRow(Horizontal):
    def __init__(self, number: int, seed: str, editor: SeedInput | None = None) -> None:
        super().__init__()
        self.number = number
        self.seed = seed
        self.editor = editor

    def compose(self) -> ComposeResult:
        yield Static(str(self.number), classes="num")
        yield self.editor or Static(self.seed, classes="text")


class SeedList(VerticalScroll, can_focus=True):
    BINDINGS: ClassVar = [("up", "cursor(-1)", "Up"), ("down", "cursor(1)", "Down")]

    def action_cursor(self, step: int) -> None:
        self.screen.move_cursor(step)  # ty: ignore[unresolved-attribute]


def numbered(seeds: list[str]) -> str:
    return "\n".join(f"{i}. {s}" for i, s in enumerate(seeds, 1))


class BriefScreen(Screen):
    BINDINGS: ClassVar = [
        ("a", "add", "Add seed"),
        ("e", "edit", "Edit seed"),
        ("d", "delete", "Delete seed"),
        ("f2", "approve", "Approve seeds"),
        Binding("escape", "discard", "Discard"),
    ]
    DEFAULT_CSS = """
    BriefScreen Horizontal#main { height: 1fr; }
    BriefScreen ChatPanel { width: 1fr; }
    BriefScreen #seeds-pane { width: 1fr; }
    BriefScreen #seed-list { height: 1fr; }
    BriefScreen #empty-seeds { height: 1fr; color: $text-muted; content-align: center middle; text-align: center; }
    BriefScreen SeedRow { height: 1; }
    BriefScreen SeedRow .num { width: 3; margin-right: 1; text-align: right; color: $text-disabled; }
    BriefScreen SeedRow .text { width: 1fr; text-wrap: nowrap; text-overflow: ellipsis; }
    BriefScreen SeedRow.-dim { opacity: 45%; }
    BriefScreen SeedRow.-selected, BriefScreen SeedRow.-editing { background: $boost; }
    BriefScreen SeedList:focus SeedRow.-selected { border-left: outer $primary; }
    BriefScreen SeedRow Input { width: 1fr; }
    BriefScreen #editor-box { height: auto; background: $panel; border-left: outer $primary; padding: 0 1; margin-top: 1; }
    BriefScreen #editor-head { height: 1; }
    BriefScreen #editor-title { width: auto; text-style: bold; color: #EEF1F5; margin-right: 2; }
    BriefScreen #was { color: $text-muted; text-wrap: nowrap; text-overflow: ellipsis; }
    BriefScreen #editor-buttons { height: auto; margin-top: 1; }
    BriefScreen #editor-buttons Button { margin-right: 1; }
    BriefScreen #seed-buttons { height: auto; margin-top: 1; align-horizontal: center; }
    BriefScreen #seed-buttons Button { margin: 0 1; }
    BriefScreen #seed-buttons.-narrow { layout: grid; grid-size: 2; grid-gutter: 0 1; grid-rows: 1; }
    BriefScreen #seed-buttons.-narrow Button { width: 1fr; margin: 0; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.seeds: list[str] = []
        self.cursor = 0
        self.editor: SeedInput | None = None  # the row being edited or added, if any
        config = files.read_config()
        self.agent = Agent(
            config.assistant_model,
            instructions=INSTRUCTIONS,
            model_settings=files.thinking_settings(config),
            defer_model_check=True,
        )

        @self.agent.instructions
        def current_seeds() -> str:
            return (
                "# Current seeds\n"
                + (numbered(self.seeds) or "None yet.")
                + "\n\n"
                + files.assistant_context()
            )

        @self.agent.tool_plain
        async def propose_seeds(seeds: list[str]) -> str:
            """Append seed phrases to the user's seed table."""
            self.add_seeds(seeds, "assistant", uuid4().hex)
            return f"Added {len(seeds)} seeds."

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        with Horizontal(id="main"):
            yield ChatPanel(
                "brief",
                self.agent,
                empty="Describe what concepts you want to search for and the assistant will help you generate seed phrases",
            )
            with panel(Vertical(id="seeds-pane"), "Seeds", "0 seeds"):
                yield SeedList(id="seed-list")
                yield Static(
                    "No seeds yet. Describe what to find in the chat, or press a to add one.",
                    id="empty-seeds",
                )
                with Vertical(id="editor-box"):
                    with Horizontal(id="editor-head"):
                        yield Static("", id="editor-title")
                        yield Static("UNSAVED", id="unsaved", classes="badge -stale")
                    yield Static("", id="was")
                    with Horizontal(id="editor-buttons"):
                        yield key_button("Save", "Enter", id="save", variant="success")
                        yield key_button("Discard", "Esc", id="discard")
                with Horizontal(id="seed-buttons"):
                    yield key_button("Add seed", "a", id="add")
                    yield key_button("Edit", "e", id="edit")
                    yield key_button("Delete", "d", id="delete")
                    yield key_button(
                        "Approve seeds", "F2", id="approve", variant="success"
                    )
        yield AppFooter()

    def on_mount(self) -> None:
        self.seeds = candidates.read_seeds()
        self.show()

    def on_resize(self) -> None:
        # the four buttons need about 56 columns on one row; below that, two rows of two
        self.query_one("#seed-buttons").set_class(
            self.query_one("#seeds-pane").size.width < 58, "-narrow"
        )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "discard":
            return self.editor is not None
        if action in ("add", "edit", "delete", "approve"):
            return self.editor is None
        return True

    def show(self, start: tuple[int | None, str] | None = None) -> None:
        """Rebuild the rows. A row being edited keeps its draft, so the agent can append while the user types."""
        if start is None and self.editor is not None:
            start = (self.editor.seed_index, self.editor.value)
        self.editor = None
        self.cursor = min(self.cursor, max(len(self.seeds) - 1, 0))
        box = self.query_one("#seed-list", SeedList)
        rows = []
        for i, seed in enumerate(self.seeds):
            editor = SeedInput(i, start[1], seed) if start and start[0] == i else None
            editing = editor is not None
            row = SeedRow(i + 1, seed, editor)
            row.set_class(start is not None and not editing, "-dim")
            row.set_class(editing, "-editing")
            row.set_class(start is None and i == self.cursor, "-selected")
            rows.append(row)
            self.editor = editor or self.editor
        if start is not None and start[0] is None:
            self.editor = SeedInput(None, start[1], "")
            row = SeedRow(len(self.seeds) + 1, "", self.editor)
            row.add_class("-editing")
            rows.append(row)
        box.remove_children()
        box.mount(*rows)
        has_rows = bool(rows)
        box.display = has_rows
        self.query_one("#empty-seeds").display = not has_rows
        retitle(
            self.query_one("#seeds-pane"),
            subtitle=f"{len(self.seeds)} seed{'' if len(self.seeds) == 1 else 's'}",
        )
        self.query_one("#editor-box").display = self.editor is not None
        self.query_one("#seed-buttons").display = self.editor is None
        for button, off in (
            ("#edit", not self.seeds),
            ("#delete", not self.seeds),
            ("#approve", not self.seeds),
        ):
            self.query_one(button, Button).disabled = off
        self.refresh_bindings()
        if self.editor:
            self.sync_editor()
            self.call_after_refresh(self.editor.focus)
        elif start is not None or self.focused is None:
            self.call_after_refresh(box.focus)

    def sync_editor(self) -> None:
        editor = self.editor
        if editor is None:
            return
        new = editor.seed_index is None
        text = editor.value.strip()
        self.query_one("#editor-title", Static).update(
            "New seed" if new else f"Editing seed {editor.seed_index + 1}"
        )
        was = self.query_one("#was", Static)
        was.update(f"was: {editor.was}")
        was.display = not new
        self.query_one("#unsaved").display = (
            bool(editor.value) if new else editor.value != editor.was
        )
        save = self.query_one("#save", Button)
        save.label = "Add  Enter" if new else "Save  Enter"
        save.disabled = not text or text == editor.was

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is self.editor:
            self.sync_editor()

    def save(
        self, summary: str = "", source: str = "user", group: str | None = None
    ) -> None:
        write_seeds(self.seeds, source, summary, group)
        self.show()

    def record(self, summary: str, change: str) -> None:
        body = f"{change}\n\n# Current seeds\n{numbered(self.seeds) or 'None.'}"
        self.query_one(ChatPanel).record(summary, body)

    def add_seeds(
        self, new: list[str], source: str = "assistant", group: str | None = None
    ) -> None:
        self.seeds += [s.strip() for s in new if s.strip()]
        self.save(f"Seeds added: {len(new)}", source, group)

    def move_cursor(self, step: int) -> None:
        if self.editor is None and self.seeds:
            self.cursor = max(0, min(self.cursor + step, len(self.seeds) - 1))
            self.show()

    def action_add(self) -> None:
        self.show((None, ""))

    def action_edit(self) -> None:
        if self.seeds:
            self.show((self.cursor, self.seeds[self.cursor]))

    def action_delete(self) -> None:
        if not self.seeds:
            return
        gone = self.seeds.pop(self.cursor)
        number = self.cursor + 1
        self.save(f"Seed {number} deleted")
        self.record(f"Seed {number} deleted", f"- {number}  {gone}")

    def action_discard(self) -> None:
        self.editor = None
        self.show()

    def action_commit(self) -> None:
        editor = self.editor
        text = editor.value.strip() if editor else ""
        if editor is None or not text or text == editor.was:
            return
        if editor.seed_index is None:
            self.seeds.append(text)
            number = len(self.seeds)
            self.editor = None
            self.save("Seed added")
            self.record("Seed added", f"+ {number}  {text}")
        else:
            number = editor.seed_index + 1
            self.seeds[editor.seed_index] = text
            self.editor = None
            self.save(f"Seed {number} edited")
            self.record(
                f"Seed {number} edited",
                f"~ {number}\n  was: {editor.was}\n  now: {text}",
            )

    def action_approve(self) -> None:
        if not self.seeds or self.editor is not None:
            return
        confirm_approve(
            self,
            "seeds_approved",
            1,
            f"Approve {len(self.seeds)} seeds and start searching?",
            f"Approved: {len(self.seeds)} seeds",
            then=lambda: self.app.goto_stage(2),  # ty: ignore[unresolved-attribute]
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = {
            "add": self.action_add,
            "edit": self.action_edit,
            "delete": self.action_delete,
            "approve": self.action_approve,
            "save": self.action_commit,
            "discard": self.action_discard,
        }.get(event.button.id or "")
        if action:
            action()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is self.editor:
            event.stop()
            self.action_commit()

    def on_chat_panel_submitted(self, event: ChatPanel.Submitted) -> None:
        if files.read_text("brief.md") is None:
            files.write_text("brief.md", event.text + "\n")  # first message, verbatim
