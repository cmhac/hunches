"""Path entry with directory auto-complete, and a modal directory browser."""

from itertools import islice
from pathlib import Path
from typing import ClassVar

from textual.actions import SkipAction
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.suggester import Suggester
from textual.widgets import Button, DirectoryTree, Input

MAX_ENTRIES = 2000
BROWSE_LABEL = "Browse (b)"


class PathSuggester(Suggester):
    def __init__(self) -> None:
        super().__init__(use_cache=False, case_sensitive=True)

    async def get_suggestion(self, value: str) -> str | None:
        head, _, segment = value.rpartition("/")
        parent = Path(head + "/" if head or value.startswith("/") else ".").expanduser()
        try:
            entries = list(islice(parent.iterdir(), MAX_ENTRIES))
        except OSError:  # permission, missing, not a directory
            return None
        for path in sorted(entries):
            hidden_ok = segment.startswith(".") or not path.name.startswith(".")
            if hidden_ok and path.name.startswith(segment) and path.is_dir():
                return f"{value[: len(value) - len(segment)]}{path.name}/"
        return None


class PathInput(Input):
    BINDINGS: ClassVar = [Binding("tab", "complete", "Complete", show=False)]

    def __init__(self, value: str = "", **kwargs) -> None:
        super().__init__(
            value, placeholder="path (→ completes)", suggester=PathSuggester(), **kwargs
        )

    def action_complete(self) -> None:
        """Accept the suggestion; with none, let tab move focus as usual."""
        before = self.value
        self.cursor_position = len(before)
        self.action_cursor_right()
        if self.value == before:
            raise SkipAction()


class DirTree(DirectoryTree):
    def filter_paths(self, paths):
        return [p for p in paths if p.is_dir() and not p.name.startswith(".")]


class PathPicker(ModalScreen[Path | None]):
    """Browse directories. Nothing is chosen until Select is pressed."""

    DEFAULT_CSS = """
    PathPicker > Vertical { width: 100%; max-width: 78; height: 100%; max-height: 22; padding: 0 1; }
    PathPicker #bar { height: 1; }
    PathPicker #root { width: 1fr; }
    PathPicker #bar Button { margin-left: 1; width: auto; min-width: 8; }
    PathPicker DirTree { height: 1fr; }
    """

    BINDINGS: ClassVar = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, start: str | Path = "") -> None:
        super().__init__()
        path = Path(start).expanduser()
        # Path("") is "." and is_dir(): an empty input must root at the real cwd
        self.start = path if start and path.is_dir() else Path.cwd()

    def compose(self) -> ComposeResult:
        with Vertical() as box:
            box.border_title = "Choose a directory"
            with Horizontal(id="bar"):
                yield PathInput(str(self.start), id="root", compact=True)
                yield Button("Up", id="up", compact=True)
                yield Button("Select", id="select", compact=True)
                yield Button("Cancel", id="cancel", compact=True)
            yield DirTree(self.start)

    def reroot(self, path: Path) -> None:
        self.start = path
        self.query_one("#root", PathInput).value = str(path)
        self.query_one(DirTree).path = path

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = Path(event.value).expanduser()
        if path.is_dir():
            self.reroot(path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        tree = self.query_one(DirTree)
        node = tree.cursor_node
        if event.button.id == "up":
            self.reroot(self.start.parent)
        elif event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "select":
            self.dismiss(node.data.path if node and node.data else self.start)


def browse(screen: Screen | App, box: Input) -> None:
    """Open the picker at the input's value and write the chosen directory back."""

    def done(path: Path | None) -> None:
        if path is not None:
            box.value = str(path)

    screen.app.push_screen(PathPicker(box.value), done)
