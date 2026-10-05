from rich.text import Text
from textual.color import Color
from textual.widget import Widget

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
