"""The Redo plan (spec 004, F9): the stale and incomplete stages in order, what redoing each costs, and a
button that goes to the earliest one. It never approves anything."""

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static
from textual.widgets.data_table import ColumnKey

from hunches import classifier, files
from hunches.app import MARKS, key_button, modal_box, panel

WIDTHS = {"live": 6, "cached": 6, "cost": 9}  # Live, Cached, Cost content widths
WHY = ColumnKey("why")
INTRO = (
    "These stages were approved before something upstream changed. Nothing is approved "
    "for you; each stage needs your approval again."
)


def count(n: int | None) -> str:
    return "·" if n is None else f"{n:,}"


def money(row: dict) -> str:
    if row["live_calls"] is None:
        return "·"
    return "?" if row["price_unknown"] else f"${row['dollars']:.4f}"


class RedoPlanScreen(ModalScreen[int | None]):
    """Dismisses with the stage to go to, or None for Close. `done` are the stages approved again so far."""

    AUTO_FOCUS = "#go"
    BINDINGS: ClassVar = [("escape", "close", "Close")]
    DEFAULT_CSS = """
    RedoPlanScreen > Vertical { height: auto; }
    RedoPlanScreen #plan-panel { height: auto; }
    RedoPlanScreen #plan { height: auto; max-height: 12; }
    RedoPlanScreen #intro, RedoPlanScreen #plan-note { height: auto; }
    RedoPlanScreen #intro.-current { color: $success; }
    RedoPlanScreen .buttons Button { margin-left: 1; }
    """

    def __init__(self, done: list[int] | None = None) -> None:
        super().__init__()
        self.done = done or []
        self.plan = classifier.redo_plan()
        self.next = self.plan[0]["stage"] if self.plan else None

    def stage_label(self, stage: int) -> str:
        return files.STAGE_NAMES[stage - 1]

    def intro(self) -> str:
        if self.next is None:
            return "All stages are current."
        if self.done:
            return (
                f"{self.stage_label(self.done[-1])} approved again. Next stale stage: "
                f"{self.stage_label(self.next)}. Nothing is approved for you; each stage needs your approval."
            )
        return INTRO

    def compose(self) -> ComposeResult:
        with modal_box(Vertical(), "Redo plan"):
            yield Static(
                self.intro(),
                id="intro",
                classes="-current" if self.next is None else "",
            )
            with panel(
                Vertical(id="plan-panel"),
                "stages in order",
                "calls: live = needs the model, cached = free",
            ):
                yield DataTable(id="plan", show_cursor=False, cell_padding=1)
            yield Static("", id="plan-note")
            with Horizontal(classes="buttons"):
                yield key_button("Close", "Esc", id="close")
                if self.next is not None:
                    verb = "Continue to" if self.done else "Go to"
                    yield key_button(
                        f"{verb} {self.stage_label(self.next)}",
                        "Enter",
                        id="go",
                        variant="primary",
                    )

    def on_mount(self) -> None:
        table = self.query_one("#plan", DataTable)
        rows = []  # (stage cell, why, live, cached, cost) with the stage's number first
        shown = {r["stage"] for r in self.plan}
        for n in self.done:
            if n not in shown:
                rows.append(
                    (n, f"✓ {n} {self.stage_label(n)}", "approved again", "·", "·", "·")
                )
        for r in self.plan:
            mark = "▸" if r["stage"] == self.next else MARKS[r["status"]]
            why = f"{r['status'].upper()} · {r['reason']}"
            rows.append(
                (
                    r["stage"],
                    f"{mark} {r['stage']} {self.stage_label(r['stage'])}",
                    why,
                    count(r["live_calls"]),
                    count(r["cached_calls"]),
                    money(r),
                )
            )
        rows.sort(key=lambda row: row[0])
        stage_width = max([len(r[1]) for r in rows] + [11])
        table.add_column("Stage", width=stage_width)
        table.add_column("Why", key="why", width=20)
        for name, align in (("Live", "live"), ("Cached", "cached"), ("Cost", "cost")):
            table.add_column(Text(name, justify="right"), width=WIDTHS[align])
        self.stage_width = stage_width
        for _, *cells in rows:
            table.add_row(*cells[:2], *(Text(c, justify="right") for c in cells[2:]))
        if self.plan:
            live = sum(r["live_calls"] or 0 for r in self.plan)
            cached = sum(r["cached_calls"] or 0 for r in self.plan)
            has_calls = any(r["live_calls"] is not None for r in self.plan)
            unknown = any(r["price_unknown"] for r in self.plan)
            dollars = sum(r["dollars"] or 0 for r in self.plan)
            total = "?" if unknown else f"${dollars:.4f}" if has_calls else "·"
            table.add_row(
                "Still to do",
                "",
                *(
                    Text(c, justify="right")
                    for c in (
                        count(live) if has_calls else "·",
                        count(cached) if has_calls else "·",
                        total,
                    )
                ),
            )
        note = self.query_one("#plan-note", Static)
        models = sorted(
            {
                files.read_config().embedding_model
                if r["stage"] == 2
                else files.read_config().classifier_model
                for r in self.plan
                if r["price_unknown"]
            }
        )
        if models:
            note.update(
                f"No price for {', '.join(models)}: dollars show ? and are not counted as $0."
            )
            note.add_class("warn")
        else:
            note.update("Cached calls cost nothing. Cost counts live calls only.")
            note.add_class("note")
        self.size_box()

    def on_resize(self) -> None:
        self.size_box()
        self.call_after_refresh(self.fit)

    def size_box(self) -> None:
        box = self.query_one(Vertical)
        box.styles.width = min(92, self.size.width - 4) if self.size.width else 76
        box.styles.max_height = (
            min(24, max(8, self.size.height - 2)) if self.size.height else 22
        )

    def fit(self) -> None:
        """DataTable has no flex column: Why gets what the others leave."""
        table = self.query_one("#plan", DataTable)
        fixed = (self.stage_width + 2) + sum(w + 2 for w in WIDTHS.values()) + 2
        table.columns[WHY].width = max(8, table.size.width - fixed - 2)

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None if event.button.id == "close" else self.next)
