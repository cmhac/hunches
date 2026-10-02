"""The hunches Textual theme and label colours. Every key in `variables` was checked against
textual 8.2.8 (textual/design.py)."""

from textual.theme import Theme

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
