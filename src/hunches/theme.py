"""The hunches Textual theme and label colours. Every key in `variables` was checked against
textual 8.2.8 (textual/design.py)."""

from rich.style import Style
from rich.text import Text
from textual.markup import escape
from textual.theme import Theme
from textual.widgets import TextArea
from textual.widgets.text_area import TextAreaTheme

LABEL_COLORS = [  # taxonomy.yaml order; off_topic always uses OFF_TOPIC_COLOR
    "#5CC8B4",
    "#E592B8",
    "#A8D46F",
    "#D9A77E",
    "#E8D27C",
    "#F0B37E",
    "#8FD3E8",
    "#9DB4C7",
]
OFF_TOPIC_COLOR = "#6B7585"

HUNCHES = Theme(
    name="hunches",
    dark=True,
    primary="#6EA8FE",
    secondary="#D2BE94",
    accent="#5CC8B4",
    foreground="#CDD4DE",
    background="#0E1218",
    surface="#141A23",
    panel="#1B2230",
    boost="#252E3E",
    success="#7CCB83",
    warning="#EAB54D",
    error="#F2557A",
    variables={
        "boost": "#252E3E",  # Textual derives $boost as a 4% white overlay; the design wants this solid colour
        "text-muted": "#8C96A6",
        "text-disabled": "#5C6676",
        "border": "#6EA8FE",
        "border-blurred": "#344056",
        "block-cursor-background": "#6EA8FE",
        "block-cursor-foreground": "#0E1218",
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-background": "#252E3E",
        "block-cursor-blurred-foreground": "#EEF1F5",
        "block-hover-background": "#252E3E",
        "input-cursor-background": "#6EA8FE",
        "input-selection-background": "#1D2F4D",
        "footer-background": "#141A23",
        "footer-key-foreground": "#6EA8FE",
        "footer-description-foreground": "#8C96A6",
        "scrollbar": "#252E3E",
        "scrollbar-hover": "#344056",
        "scrollbar-active": "#6EA8FE",
    },
)


def label_color(index: int, name: str) -> str:
    """Colour for the label at position `index` in taxonomy.yaml."""
    if name == "off_topic":
        return OFF_TOPIC_COLOR
    return LABEL_COLORS[index % len(LABEL_COLORS)]


def label_tag(names: list[str], name: str) -> str:
    """Markup for a label: its coloured square, then the name verbatim. `names` is the taxonomy's label order."""
    if name == "off_topic":
        return f"[{OFF_TOPIC_COLOR}]■[/] [$text-muted]off_topic[/]"
    color = label_color(names.index(name), name) if name in names else OFF_TOPIC_COLOR
    return f"[{color}]■[/] {escape(name)}"


def _style(color: str, bold: bool = False) -> Style:
    return Style(color=color, bold=bold)


# TextArea colours: yaml keys secondary, values strong, comments faint, markdown headings primary
EDITOR = TextAreaTheme(
    name="hunches",
    base_style=Style(color="#EEF1F5", bgcolor="#0E1218"),
    gutter_style=_style("#5C6676"),
    cursor_style=Style(color="#0E1218", bgcolor="#6EA8FE"),
    cursor_line_style=Style(bgcolor="#141A23"),
    selection_style=Style(bgcolor="#1D2F4D"),
    syntax_styles={
        "yaml.field": _style("#D2BE94"),
        "string": _style("#EEF1F5"),
        "number": _style("#EEF1F5"),
        "boolean": _style("#EEF1F5"),
        "punctuation.delimiter": _style("#8C96A6"),
        "comment": _style("#5C6676"),
        "heading": _style("#6EA8FE", bold=True),
        "heading.marker": _style("#6EA8FE", bold=True),
    },
)


def editor(text_area: TextArea) -> TextArea:
    """Give a TextArea the hunches colours."""
    text_area.register_theme(EDITOR)
    text_area.theme = "hunches"
    return text_area


def label_text(names: list[str], name: str) -> Text:
    """label_tag for DataTable cells, which take Rich renderables (their strings use Rich markup)."""
    color = label_color(names.index(name), name) if name in names else OFF_TOPIC_COLOR
    muted = "#8C96A6" if name == "off_topic" else ""
    return Text.assemble(("■", color), " ", (name, muted))
