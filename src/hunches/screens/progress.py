from rich.text import Text
from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Button, Static

_USED = {"primary", "success", "background", "foreground", "boost"}


class LabelBar(Widget):
    """One-row progress bar whose label is drawn over the bar and inverts over the filled part."""

    DEFAULT_CSS = "LabelBar { height: 1; width: 1fr; }"

    def __init__(
        self,
        total: int,
        value: int,
        label: str,
        align: str = "center",
        done_style: str = "success",
        dividers: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.align = align
        self.done_style = done_style  # theme colour of the filled part when complete
        self.dividers = dividers  # faint ticks at 25/50/75 %
        self.update_bar(total, value, label)

    def update_bar(self, total: int, value: int, label: str) -> None:
        self.total, self.value, self.label = total, value, label
        self.set_class(total > 0 and value >= total, "-complete")
        self.refresh()

    def fill_cells(self, width: int) -> int:
        if self.total <= 0:
            return 0
        return width * min(self.value, self.total) // self.total

    def render(self) -> Text:
        width = self.size.width
        label = self.label[:width]
        start = (width - len(label)) // 2 if self.align == "center" else 0
        cells = [" "] * width
        if self.dividers:
            for q in (1, 2, 3):
                cells[min(width - 1, width * q // 4)] = "▏"
        cells[start : start + len(label)] = label
        fill = self.fill_cells(width)
        colors = {
            k: Color.parse(v).hex6
            for k, v in self.app.theme_variables.items()
            if k in _USED or k == self.done_style
        }
        bar = colors[self.done_style if self.has_class("-complete") else "primary"]
        text = Text("".join(cells))
        text.stylize(f"bold {colors['background']} on {bar}", 0, fill)
        text.stylize(f"{colors['foreground']} on {colors['boost']}", fill, width)
        return text


def seconds_text(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


def eta_text(done: int, total: int, live_done: int, elapsed: float) -> str | None:
    """Time left, from the rate of non-cached completions; None until there are 3 of them."""
    if live_done < 3:
        return None
    return seconds_text((total - done) * elapsed / live_done)


BUTTONS = {
    "stop": ("Stop", "x", "error"),
    "resume": ("Resume", "s", "primary"),
    "start": ("Start", "s", "primary"),
}


class RunIndicator(Vertical):
    """Centred run block: title, bar, "N of M · about X left", optional status line and button.

    The button is `#run-button`; its label tells the screen which action it stands for
    (Stop calls the screen's stop action, Start/Resume its start action).
    """

    DEFAULT_CSS = """
    RunIndicator { height: 1fr; align: center middle; }
    RunIndicator > * { width: auto; max-width: 100%; margin-bottom: 1; }
    RunIndicator > LabelBar { width: 36; }
    RunIndicator #run-title { text-style: bold; }
    RunIndicator #run-counts { color: $text-muted; }
    RunIndicator #run-button { width: auto; margin-bottom: 0; }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="run-title")
        yield LabelBar(0, 0, "")
        yield Static("", id="run-counts")
        status = Static("", id="run-status")
        status.display = False
        yield status
        button = Button("Stop  x", id="run-button")
        button.display = False
        yield button

    def set_title(self, title: str) -> None:
        self.query_one("#run-title", Static).update(title)

    def set_progress(
        self, done: int, total: int, eta: str | None = None, detail: str = ""
    ) -> None:
        pct = 100 * done // total if total else 0
        self.query_one(LabelBar).update_bar(total, done, f"{pct}%")
        counts = f"{done} of {total}"
        if eta:
            counts += f" \u00b7 about {eta} left"
        if detail:
            counts += f" \u00b7 {detail}"
        self.query_one("#run-counts", Static).update(counts)

    def set_status(self, text: str, kind: str = "note") -> None:
        status = self.query_one("#run-status", Static)
        status.update(text)
        status.set_classes(kind)
        status.display = bool(text)

    def set_button(self, kind: str | None) -> None:
        button = self.query_one("#run-button", Button)
        button.display = kind is not None
        if kind is not None:
            label, key, variant = BUTTONS[kind]
            button.label = f"{label}  {key}"
            button.variant = variant
