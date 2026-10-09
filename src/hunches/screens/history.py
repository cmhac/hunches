"""Screens for the edit history (spec 004): the History modal, the label-changing confirmation and
the notice for edits made outside hunches."""

from collections.abc import Callable
from datetime import datetime
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.markup import escape
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Select, Static
from textual.widgets.data_table import ColumnKey

from hunches import files, history
from hunches.app import key_button, modal_box, panel, retitle
from hunches.theme import HUNCHES, diff_markup

FILES = list(history.ARTIFACTS.values())
# source word and its badge colours (background, text); never colour alone
BADGES = {
    "user": ("YOU", HUNCHES.boost, "#EEF1F5"),
    "assistant": ("ASSISTANT", HUNCHES.accent, HUNCHES.background),
    "external": ("EXTERNAL", HUNCHES.warning, HUNCHES.background),
    "undo": ("UNDO", HUNCHES.secondary, HUNCHES.background),
    "redo": ("REDO", HUNCHES.secondary, HUNCHES.background),
    "restore": ("RESTORE", HUNCHES.secondary, HUNCHES.background),
    "baseline": ("BASELINE", HUNCHES.panel, "#8C96A6"),
    "approval": ("APPROVAL", HUNCHES.success, HUNCHES.background),
    "version": ("VERSION", HUNCHES.primary, HUNCHES.background),
}
SUMMARY = ColumnKey("summary")
FIXED = 11 + 15 + 11  # Time, File and Source column widths


class NeedsVersionScreen(ModalScreen[bool]):
    """history.NeedsVersion: archive the current state as a taxonomy version first, or cancel."""

    AUTO_FOCUS = "#cancel"
    BINDINGS: ClassVar = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    NeedsVersionScreen > Vertical { width: 66; height: auto; max-height: 100%; }
    NeedsVersionScreen VerticalScroll { height: auto; max-height: 6; background: $panel; padding: 0 1; }
    """

    def __init__(self, need: history.NeedsVersion, verb: str) -> None:
        super().__init__()
        self.need = need
        self.verb = verb

    def compose(self) -> ComposeResult:
        n = self.need.number
        if self.need.kind == "restore":
            why = (
                f"{self.verb.capitalize()} goes back to the labels an earlier set of gold labels was made "
                f"with. hunches first archives the current labels, prompt, gold labels and results as "
                f"taxonomy version {n}. Then those earlier gold labels come back."
            )
        else:
            why = (
                f"{self.verb.capitalize()} changes the labels your gold labels were made with. hunches "
                f"first archives the current labels, prompt, gold labels and results as taxonomy "
                f"version {n}, so nothing is lost. Then the labels change and the gold labels are "
                "cleared on the same items, ready to label again."
            )
        with modal_box(Vertical(), f"{self.verb.capitalize()} changes the labels"):
            yield Static(why, id="why", classes="note")
            yield Static("The labels become:", classes="note")
            with VerticalScroll():
                yield Static(files.taxonomy_yaml(self.need.taxonomy), markup=False)
            with Horizontal(classes="buttons"):
                yield key_button("Cancel", "Esc", id="cancel")
                yield Button(
                    f"Archive as version {n} and {self.verb}",
                    id="archive",
                    variant="primary",
                )

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "archive")


def attempt(
    screen: Screen,
    verb: str,
    move: Callable[[bool], dict | None],
    done: Callable[[dict], object],
) -> None:
    """Run a history move (`move(confirmed)`); a label-changing one asks the user first, then runs again."""

    def run(confirmed: bool) -> None:
        try:
            entry = move(confirmed)
        except history.NeedsVersion as need:
            screen.app.push_screen(
                NeedsVersionScreen(need, verb),
                lambda yes: run(True) if yes else None,
            )
            return
        if entry:
            done(entry)

    run(False)


def when(ts: str) -> str:
    """A log time in local time: the clock for today, else the date and the minute."""
    moment = datetime.fromisoformat(ts).astimezone()
    if moment.date() == datetime.now().astimezone().date():
        return moment.strftime("%H:%M:%S")
    return moment.strftime("%m-%d %H:%M")


def badge(word_key: str) -> Text:
    word, background, foreground = BADGES[word_key]
    return Text(f" {word} ", style=f"bold {foreground} on {background}")


def file_of(entry: dict) -> str | None:
    return history.ARTIFACTS[entry["artifact"]] if entry["kind"] == "edit" else None


class HistoryScreen(ModalScreen[tuple[dict, str] | None]):
    """The combined timeline, newest first. Dismisses with (restore entry, note) or None."""

    AUTO_FOCUS = "#timeline"
    BINDINGS: ClassVar = [
        ("escape", "close", "Close"),
        ("v", "switch", "Show text"),
        ("r", "restore", "Restore this"),
    ]
    DEFAULT_CSS = """
    HistoryScreen { align: center middle; }
    HistoryScreen > Vertical { width: 1fr; height: 1fr; margin: 1 2; padding: 0 1; }
    HistoryScreen #top { height: 1; }
    HistoryScreen #top Static { width: auto; color: $text-muted; margin-right: 1; }
    HistoryScreen #file { width: 22; margin-right: 1; }
    HistoryScreen #timeline-panel { height: 3fr; }
    HistoryScreen #preview-panel { height: 2fr; }
    HistoryScreen #timeline { height: 1fr; }
    HistoryScreen #preview-scroll { height: 1fr; }
    HistoryScreen #preview { height: auto; }
    HistoryScreen .buttons Button { margin-left: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.text_mode = False
        self.shown: list[dict] = []

    def compose(self) -> ComposeResult:
        with modal_box(Vertical(), "History"):
            with Horizontal(id="top"):
                yield Static("file")
                yield Select(
                    [("All files", "all"), *((f, f) for f in FILES)],
                    value="all",
                    allow_blank=False,
                    compact=True,
                    id="file",
                )
                yield Static("", id="count")
            with panel(Vertical(id="timeline-panel"), "timeline"):
                yield DataTable(id="timeline", cursor_type="row")
            with (
                panel(Vertical(id="preview-panel"), "diff"),
                VerticalScroll(id="preview-scroll"),
            ):
                yield Static("", id="preview")
            with Horizontal(classes="buttons"):
                yield key_button("Show text", "v", id="mode")
                yield key_button("Restore this", "r", id="restore", variant="primary")
                yield key_button("Close", "Esc", id="close")

    def on_mount(self) -> None:
        table = self.query_one("#timeline", DataTable)
        table.add_column("Time", width=11)
        table.add_column("File", width=15)
        table.add_column("Source", width=11)
        table.add_column("Summary", key="summary", width=20)
        self.rows()

    def on_resize(self) -> None:
        self.call_after_refresh(self.rows)

    def rows(self) -> None:
        """Rebuild the timeline for the chosen file, keeping the selected entry."""
        table = self.query_one("#timeline", DataTable)
        chosen = self.query_one("#file", Select).value
        keep = self.selected()
        table.columns[SUMMARY].width = max(10, table.size.width - FIXED - 4 * 2 - 2)
        current = {
            history.entries(a)[-1]["seq"]
            for a in history.ARTIFACTS
            if history.entries(a)
        }
        self.shown = [
            e
            for e in reversed(history.entries())
            if chosen == "all" or file_of(e) == chosen
        ]
        table.clear()
        for e in self.shown:
            summary = e["summary"] + ("  (current)" if e["seq"] in current else "")
            table.add_row(
                when(e["ts"]),
                file_of(e) or "·",
                badge(e["source"] if e["kind"] == "edit" else e["kind"]),
                Text(summary, no_wrap=True, overflow="ellipsis"),
                key=str(e["seq"]),
            )
        if keep:
            seqs = [e["seq"] for e in self.shown]
            if keep["seq"] in seqs:
                table.move_cursor(row=seqs.index(keep["seq"]))
        n = len(self.shown)
        self.query_one("#count", Static).update(
            f"newest first · {n} {'entry' if n == 1 else 'entries'}"
        )
        self.show()

    def selected(self) -> dict | None:
        table = self.query_one("#timeline", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def can_restore(self, entry: dict | None) -> bool:
        if entry is None or entry["kind"] != "edit" or entry["after"] is None:
            return False
        name = history.ARTIFACTS[entry["artifact"]]
        return history.text(entry["after"]) != files.read_text(name)

    def show(self) -> None:
        """The preview and the buttons for the selected entry."""
        entry = self.selected()
        name = file_of(entry) if entry else None
        restorable = self.can_restore(entry)
        self.query_one("#mode", Button).disabled = name is None
        self.query_one("#mode", Button).label = (
            "Show diff  v" if self.text_mode else "Show text  v"
        )
        self.query_one("#restore", Button).disabled = not restorable
        if entry is None:
            body, title, sub = "", "diff", ""
        elif name is None:
            body = escape(self.event_text(entry))
            title, sub = f"{entry['kind']} · {when(entry['ts'])}", "event"
        else:
            new = history.text(entry["after"])
            old = history.text(entry["before"]) or ""
            if new is None:
                body = "(the file did not exist)"
            elif self.text_mode:
                body = escape(new)
            else:
                body = (
                    diff_markup(
                        old, new, f"{name} · before", f"{name} · {when(entry['ts'])}"
                    )
                    or "(no difference)"
                )
            title = (
                f"{'text' if self.text_mode else 'diff'} · {name} · {when(entry['ts'])}"
            )
            sub = (
                f"Restore this makes {name} match"
                if restorable
                else "this is the current text"
                if new is not None and new == files.read_text(name)
                else ""
            )
        retitle(self.query_one("#preview-panel"), title, sub)
        self.query_one("#preview", Static).update(body)
        self.refresh_bindings()

    def event_text(self, entry: dict) -> str:
        if entry["kind"] == "approval":
            return (
                f"{entry['summary']}\nstage {entry['stage']} · {when(entry['ts'])}\n\n"
                "An approval is not a file. It cannot be restored; it is what you approve "
                "again when a stage is stale."
            )
        return (
            f"{entry['summary']}\n{when(entry['ts'])}\n\nA taxonomy version keeps the labels, "
            "gold labels, prompt and results as they were. Restore it with Versions on the "
            "taxonomy screen."
        )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        entry = self.selected()
        if action == "switch":
            return True if entry and file_of(entry) else None
        if action == "restore":
            return True if self.can_restore(entry) else None
        return True

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.show()

    def on_select_changed(self, event: Select.Changed) -> None:
        self.rows()

    def action_switch(self) -> None:
        if self.check_action("switch", ()):
            self.text_mode = not self.text_mode
            self.show()

    def action_restore(self) -> None:
        entry = self.selected()
        if entry is None or not self.can_restore(entry):
            return
        artifact = entry["artifact"]
        note = f"Restored {history.ARTIFACTS[artifact]} to {when(entry['ts'])}. Undo with F6."
        attempt(
            self,
            "restore",
            lambda confirmed: history.restore(artifact, entry["seq"], confirmed),
            lambda moved: self.dismiss((moved, note)),
        )

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "mode":
                self.action_switch()
            case "restore":
                self.action_restore()
            case _:
                self.action_close()


class ExternalNotice(Vertical):
    """Shown once per outside edit, at the top of the screen the user is on."""

    DEFAULT_CSS = """
    ExternalNotice { height: auto; margin-bottom: 1; }
    ExternalNotice Horizontal { height: auto; }
    ExternalNotice Button { margin-right: 1; }
    """

    def __init__(self, entry: dict) -> None:
        super().__init__(classes="banner -warning")
        self.entry = entry
        self.artifact = entry["artifact"]

    def compose(self) -> ComposeResult:
        name = history.ARTIFACTS[self.artifact]
        yield Static(f"{name} changed outside hunches.", classes="notice-text")
        with Horizontal():
            yield key_button(
                "Undo",
                "F6",
                id="notice-undo",
                disabled=not self.can_undo(),
            )
            yield key_button("History", "F8", id="notice-history")
            yield key_button("Dismiss", "Esc", id="notice-dismiss")

    def can_undo(self) -> bool:
        """Undo reverts to the entry before the outside edit, so that edit must still be the newest."""
        return history.is_current(self.entry) and history.can_undo(self.artifact)

    def undo(self) -> None:
        if self.can_undo():
            attempt(
                self.screen,
                "undo",
                lambda confirmed: history.undo(self.artifact, confirmed),
                self.undone,
            )

    def undone(self, entry: dict) -> None:
        screen = self.screen
        self.remove()
        if moved := getattr(screen, "history_changed", None):
            moved(entry)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        match event.button.id:
            case "notice-undo":
                self.undo()
            case "notice-history":
                self.app.action_history()  # ty: ignore[unresolved-attribute]
            case _:
                self.remove()
