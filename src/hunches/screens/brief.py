import csv
import io
from typing import ClassVar

from pydantic_ai import Agent
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, Static

from hunches import candidates, files
from hunches.app import (
    AppFooter,
    ChatPanel,
    StatusHeader,
    confirm_approve,
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


def write_seeds(seeds: list[str]) -> None:
    """Write seeds.csv in the format candidates.read_seeds() reads: a `seed` header, one per row."""
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows([["seed"], *([s] for s in seeds)])
    files.write_text("seeds.csv", out.getvalue())


class BriefScreen(Screen):
    BINDINGS: ClassVar = [
        ("a", "add", "Add seed"),
        ("e", "edit", "Edit seed"),
        ("d", "delete", "Delete seed"),
        ("f2", "approve", "Approve seeds"),
    ]
    DEFAULT_CSS = """
    BriefScreen Horizontal { height: 1fr; }
    BriefScreen ChatPanel { width: 1fr; }
    BriefScreen #seeds-pane { width: 1fr; }
    BriefScreen DataTable { height: 1fr; }
    BriefScreen #empty { height: 1fr; color: $text-muted; }
    BriefScreen #status { height: auto; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.seeds: list[str] = []
        self.editing: int | None = None  # row being edited; None means a new seed
        config = files.read_config()
        self.agent = Agent(
            config.assistant_model,
            instructions=INSTRUCTIONS,
            model_settings=files.thinking_settings(config),
            defer_model_check=True,
        )

        @self.agent.tool_plain
        async def propose_seeds(seeds: list[str]) -> str:
            """Append seed phrases to the user's seed table."""
            self.add_seeds(seeds)
            return f"Added {len(seeds)} seeds."

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        with Horizontal():
            yield ChatPanel("brief", self.agent)
            with panel(Vertical(id="seeds-pane"), "seeds.csv · 0"):
                yield DataTable(cursor_type="row", id="seeds")
                yield Static(
                    "No seeds yet. Describe what to find in the chat, or press a to add one.",
                    id="empty",
                )
                yield Input(placeholder="a: add, e: edit, then Enter", id="seed-input")
                yield Static("", id="status", classes="warn")
        yield AppFooter()

    def on_mount(self) -> None:
        self.query_one("#seeds", DataTable).add_column("Seed phrases")
        self.seeds = candidates.read_seeds()
        self.refresh_table()

    def refresh_table(self) -> None:
        table = self.query_one("#seeds", DataTable)
        table.clear()
        for seed in self.seeds:
            table.add_row(seed)
        table.display = bool(self.seeds)
        self.query_one("#empty").display = not self.seeds
        retitle(self.query_one("#seeds-pane"), f"seeds.csv · {len(self.seeds)}")

    def save(self) -> None:
        write_seeds(self.seeds)
        self.refresh_table()

    def add_seeds(self, new: list[str]) -> None:
        self.seeds += [s.strip() for s in new if s.strip()]
        self.save()

    def action_add(self) -> None:
        self.editing = None
        self.query_one("#seed-input", Input).focus()

    def action_edit(self) -> None:
        row = self.query_one("#seeds", DataTable).cursor_row
        if row < len(self.seeds):
            self.editing = row
            box = self.query_one("#seed-input", Input)
            box.value = self.seeds[row]
            box.focus()

    def action_delete(self) -> None:
        row = self.query_one("#seeds", DataTable).cursor_row
        if row < len(self.seeds):
            del self.seeds[row]
            self.save()

    def action_approve(self) -> None:
        if not self.seeds:
            self.query_one("#status", Static).update("Add at least one seed first.")
            return
        confirm_approve(
            self,
            "seeds_approved",
            f"Approve {len(self.seeds)} seeds and continue to search?",
            then=lambda: self.app.goto_stage(2),  # ty: ignore[unresolved-attribute]
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if event.input.id == "seed-input":
            if text and self.editing is not None:
                self.seeds[self.editing] = text
                self.save()
            elif text:
                self.add_seeds([text])
            event.input.value = ""
            self.editing = None
            self.query_one("#seeds", DataTable).focus()
        elif text and files.read_text("brief.md") is None:
            files.write_text("brief.md", text + "\n")  # first message, verbatim
