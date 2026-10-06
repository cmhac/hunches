import math
import random
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.screen import Screen
from textual.widgets import Button, DataTable, Static

from hunches import files
from hunches.app import (
    AppFooter,
    ConfirmScreen,
    StatusHeader,
    key_button,
    panel,
    retitle,
    say,
)
from hunches.screens.progress import LabelBar
from hunches.theme import label_color, label_text

DRAW_MORE = 10
# (fraction of the rows, name for "Next milestone", message when the count lands on it)
MILESTONES = [
    (0.25, "a quarter of the way", "A quarter of the way there."),
    (0.5, "halfway", "Halfway there."),
    (0.75, "three quarters", "Three quarters of the way there."),
    (1, "done", "All labelled. Press F2 to finish."),
]


def milestone(done: int, total: int) -> tuple[str, int, str | None]:
    """(name of the next milestone, rows still to label to reach it, message if `done` is on one)."""
    marks = [(math.ceil(total * f), name, msg) for f, name, msg in MILESTONES]
    hit = next((msg for q, _, msg in marks if q == done and done > 0), None)
    nxt = next(((q, name) for q, name, _ in marks if q > done), (done, "done"))
    return nxt[1], nxt[0] - done, hit


def draw(split: str, n: int = files.SAMPLE_SIZE) -> list[files.GoldRow]:
    """Sample n candidates not yet in gold.jsonl (either split), append them with empty labels, return them.

    Reproducible: the RNG seed is the project (directory) name, the split and the number of gold
    rows so far, so the same project state always draws the same items. Tasks 14 and 15 reuse this.
    """
    gold = files.read_gold()
    taken = {r.id for r in gold}
    pool = [c for c in files.read_jsonl("candidates.jsonl") if c["id"] not in taken]
    rng = random.Random(f"{Path.cwd().name}:{split}:{len(gold)}")
    rows = [
        files.GoldRow(id=c["id"], text=c["text"], labels=[], split=split)  # ty: ignore[invalid-argument-type]
        for c in rng.sample(pool, min(n, len(pool)))
    ]
    files.write_gold(gold + rows)  # persisted before the user sees anything
    return rows


class GoldScreen(Screen):
    """Label a random sample of candidates one at a time (stage 4 dev, stage 6 test)."""

    BINDINGS: ClassVar = [
        ("left", "move(-1)", "Back"),
        ("right", "move(1)", "Skip"),
        ("enter", "confirm", "Confirm labels"),
        ("d", "draw_more", "Draw 10 more"),
        ("f2", "finish", "Finish"),
    ]
    AUTO_FOCUS = ""  # the counts table would swallow the arrow and Enter keys
    DEFAULT_CSS = """
    GoldScreen #short-banner, GoldScreen #exhausted { width: 1fr; }
    GoldScreen #short { height: 1fr; align: center middle; }
    GoldScreen #short > Static { width: auto; text-align: center; margin-bottom: 1; }
    GoldScreen #short-title { color: $error; text-style: bold; }
    GoldScreen #short-text { color: $text-muted; max-width: 64; }
    GoldScreen #short-buttons { width: auto; height: 1; }
    GoldScreen #short-buttons > Button { width: auto; margin: 0 1; }
    GoldScreen #main { height: 1fr; }
    GoldScreen #left { width: 1fr; }
    GoldScreen #progress-block {
        height: auto; padding: 0 1; background: $surface; border-left: outer $primary;
    }
    GoldScreen #progress-block.-complete { border-left: outer $success; }
    GoldScreen #progress-block > Horizontal { height: 1; }
    GoldScreen #progress-block Static { width: auto; height: 1; }
    GoldScreen #p-item { margin-left: 2; }
    GoldScreen #p-left, GoldScreen #p-next { width: 1fr; }
    GoldScreen #p-left { text-align: right; }
    GoldScreen #item { height: 1fr; }
    GoldScreen #labels-panel { height: auto; }
    GoldScreen #labels, GoldScreen #note { height: auto; }
    GoldScreen #note:empty { display: none; }
    GoldScreen #right { width: 36%; max-width: 30; }
    GoldScreen #counts-panel { height: 1fr; }
    GoldScreen #actions { height: auto; align-horizontal: center; margin-top: 1; }
    GoldScreen #actions > Button { width: auto; margin-bottom: 1; }
    GoldScreen DataTable { height: auto; }
    """

    def __init__(self, split: str = "dev") -> None:
        super().__init__()
        self.split = split
        self.ready = (
            files.read_text("taxonomy.yaml") is not None
        )  # n/p can reach us early
        self.taxonomy = (
            files.read_taxonomy()
            if self.ready
            else files.Taxonomy(mode="single", labels=[])
        )
        self.all = files.read_gold()
        self.rows = [r for r in self.all if r.split == split]
        self.pool_short: dict[str, int] | None = None  # set on mount; blocks labelling
        self.pending: list[str] = []  # multi mode: labels toggled but not yet confirmed
        self.index = 0
        self.note = ""
        self.exhausted = ""  # banner: a draw found the pool empty
        self.celebrate = (
            False  # show the milestone message until the next label or move
        )
        # key "1".."9" for the user labels in order, "0" for off_topic
        self.keys = {
            str(i + 1): n
            for i, n in enumerate(files.all_labels(self.taxonomy)[:-1][:9])
        }
        self.keys["0"] = files.OFF_TOPIC

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        if not self.ready:
            yield Static(
                "Finish stage 3 (taxonomy and prompt) first.",
                id="not-ready",
                classes="not-ready",
            )
            yield AppFooter()
            return
        yield Static("", id="short-banner", classes="banner -stale", markup=False)
        with Vertical(id="short"):
            yield Static(
                "Your corpus may be too small for this analysis",
                id="short-title",
                markup=False,
            )
            yield Static(
                "The gold sets are drawn from the candidates the search found. Without "
                "enough of them, the classifier cannot be tuned or tested reliably.",
                id="short-text",
                markup=False,
            )
            yield Static("", id="short-numbers", markup=False)
            yield Static(
                "Add seeds to find more candidates, or use a larger corpus.",
                id="short-text2",
                classes="note",
                markup=False,
            )
            with Horizontal(id="short-buttons"):
                yield Button("Add seeds", id="add-seeds", variant="primary")
                yield key_button("Project settings", "F3", id="settings")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static("", id="exhausted", classes="banner -stale", markup=False)
                with Vertical(id="progress-block"):
                    with Horizontal():
                        yield Static("", id="p-split")
                        yield Static("", id="p-item")
                        yield Static("", id="p-left")
                    yield LabelBar(0, 0, "", dividers=True, id="bar")
                    with Horizontal():
                        yield Static("", id="p-next")
                        yield Static("", id="p-pct")
                with panel(Vertical(id="item", classes="-focused"), "item"):
                    yield Static("", id="text", markup=False)
                with panel(Vertical(id="labels-panel"), "labels"):
                    yield Static("", id="labels")
                yield Static("", id="note", classes="warn", markup=False)
            with Vertical(id="right"):
                with panel(Vertical(id="counts-panel"), "counts"):
                    yield DataTable(id="counts")
                with Vertical(id="actions"):
                    yield key_button(
                        f"Finish {self.split} set", "F2", id="finish", variant="success"
                    )
                    yield key_button(f"Draw {DRAW_MORE} more", "d", id="more")
        yield AppFooter()

    def on_mount(self) -> None:
        if not self.ready:
            return
        if len(self.rows) < files.SAMPLE_SIZE:
            self.add_rows(files.SAMPLE_SIZE - len(self.rows))
        table = self.query_one("#counts", DataTable)
        table.add_column("Label")
        table.add_column(Text("Count", justify="right"))
        if len(self.rows) < files.SAMPLE_SIZE:
            self.block()
            return
        self.query_one("#short-banner").display = False
        self.query_one("#short").display = False
        self.index = next((i for i, r in enumerate(self.rows) if not r.labels), 0)
        self.show()

    def block(self) -> None:
        """Too few candidates to fill this split: show why, and the ways out, instead of the labelling view."""
        found = {c["id"] for c in files.read_jsonl("candidates.jsonl")}
        other = {r.id for r in self.all if r.split != self.split} & found
        self.pool_short = {
            "found": len(found),
            "used": len(other),
            "left": len(found) - len(other),  # what this split can draw from
            "need": files.SAMPLE_SIZE,
        }
        p = self.pool_short
        if self.split == "dev":
            banner = f"Only {p['found']} candidates were found; the dev set needs {p['need']}."
        else:
            banner = f"Only {p['left']} unlabelled candidates are left for the test set; it needs {p['need']}."
        self.query_one("#short-banner", Static).update(banner)
        lines = [("candidates found", p["found"])]
        if self.split == "test":
            lines.append(("already in the dev set", p["used"]))
        lines += [
            ("left to draw", p["left"]),
            (f"needed for the {self.split} set", p["need"]),
        ]
        self.query_one("#short-numbers", Static).update(
            "\n".join(f"{k:>26}  {v:>5}" for k, v in lines)
        )
        self.query_one("#main").display = False
        self.refresh_bindings()

    def add_rows(self, n: int) -> int:
        new = draw(self.split, n)
        self.all += new
        self.rows += new
        return len(new)

    def show(self) -> None:
        row = self.rows[self.index] if self.rows else None
        done = sum(bool(r.labels) for r in self.rows)
        total = len(self.rows)
        left = total - done
        complete = total > 0 and left == 0
        self.show_progress(done, total, complete)
        self.query_one("#text", Static).update(row.text if row else "")
        retitle(self.query_one("#item"), f"item {row.id}" if row else "item")
        single = self.taxonomy.mode == "single"
        labels_panel = self.query_one("#labels-panel")
        retitle(
            labels_panel,
            f"labels · {self.taxonomy.mode}",
            "press a key to label" if single else "keys toggle, enter confirms",
        )
        names = [lab.name for lab in self.taxonomy.labels]
        descriptions = {lab.name: lab.description for lab in self.taxonomy.labels}
        chosen = set(self.pending)
        lines = []
        for key, name in self.keys.items():
            color = label_color(names.index(name) if name in names else 0, name)
            on = name in chosen
            mark = ("●" if on else "○") if single else ("■" if on else "□")
            line = (
                f"[b on $panel] {key} [/] [{color}]{mark}[/] "
                f"[{'b ' if on else ''}#EEF1F5]{escape(name)}[/]"
            )
            if descriptions.get(name):
                line += f"  [$text-muted]{escape(descriptions[name])}[/]"
            lines.append(f"[on $boost][$primary]▌[/]{line}[/]" if on else f" {line}")
        self.query_one("#labels", Static).update("\n".join(lines))
        say(self.query_one("#note", Static), self.note)
        say(self.query_one("#exhausted", Static), self.exhausted)
        retitle(self.query_one("#counts-panel"), subtitle=f"{done} of {total}")
        table = self.query_one("#counts", DataTable)
        table.clear()
        for name in files.all_labels(self.taxonomy):
            table.add_row(
                label_text(names, name),
                Text(str(sum(name in r.labels for r in self.rows)), justify="right"),
                key=name,
            )
        self.query_one("#finish", Button).disabled = left > 0
        self.refresh_bindings()

    def show_progress(self, done: int, total: int, complete: bool) -> None:
        colour = "$success" if complete else "$primary"
        self.query_one("#progress-block").set_class(complete, "-complete")
        self.query_one("#p-split", Static).update(f"[b {colour}]{self.split} set[/]")
        self.query_one("#p-item", Static).update(
            f"[$text-muted]item {min(self.index + 1, total)}[/]"
        )
        self.query_one("#p-left", Static).update(
            "[b $success]Complete[/]"
            if complete
            else f"[b #EEF1F5]{total - done} to go[/]"
        )
        self.query_one("#bar", LabelBar).update_bar(total, done, f"{done} / {total}")
        name, more, message = milestone(done, total)
        if complete:
            line = f"[$success]{message}[/]"
        elif self.celebrate and message:
            line = f"[b $success]{message}[/] [$text-muted]{total - done} to go.[/]"
        else:
            line = f"[$text-muted]Next milestone: {name} · {more} more[/]"
        self.query_one("#p-next", Static).update(line)
        pct = done * 100 // total if total else 0
        self.query_one("#p-pct", Static).update(f"[$text-muted]{pct}%[/]")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if self.pool_short and action in ("move", "confirm", "draw_more", "finish"):
            return False
        if action == "finish" and any(not r.labels for r in self.rows):
            return None  # dimmed until every row is labelled
        return True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        match event.button.id:
            case "add-seeds":
                self.app.goto_stage(1)  # ty: ignore[unresolved-attribute]
            case "settings":
                self.app.action_settings()  # ty: ignore[unresolved-attribute]
            case "finish":
                self.action_finish()
            case "more":
                self.action_draw_more()

    def on_key(self, event) -> None:
        name = self.keys.get(event.character or "")
        if name is None or not self.rows or self.pool_short:
            return
        event.stop()
        self.note = self.exhausted = ""
        self.celebrate = False
        if self.taxonomy.mode == "single":
            self.pending = [name]
            self.action_confirm()
            return
        if name == files.OFF_TOPIC:
            self.pending = [] if name in self.pending else [name]
        else:
            others = [n for n in self.pending if n != files.OFF_TOPIC]
            self.pending = [n for n in others if n != name] + (
                [] if name in others else [name]
            )
        self.show()

    def action_confirm(self) -> None:
        if not self.rows or self.pool_short:
            return
        row = self.rows[self.index]
        try:
            files.validate_labels(self.pending, self.taxonomy)
        except ValueError as e:
            self.note = f"Not saved: {e}"
            self.show()
            return
        was_new = not row.labels
        row.labels = list(self.pending)
        files.write_gold(self.all)
        self.note = ""
        self.action_move(1, clamp=True)
        if was_new:
            self.celebrate = (
                True  # one-time milestone message, until the next label or move
            )
            self.show()

    def action_move(self, step: int, clamp: bool = False) -> None:
        if not self.rows or self.pool_short:
            return
        i = self.index + step
        if not 0 <= i < len(self.rows):
            if clamp:
                i = self.index
            else:
                return
        self.index = i
        self.pending = list(self.rows[i].labels)
        self.note = self.exhausted = ""
        self.celebrate = False
        self.show()

    def action_draw_more(self) -> None:
        if not self.ready or self.pool_short:
            return
        got = self.add_rows(DRAW_MORE)
        self.exhausted = (
            f"No more candidates to draw: only {got} were left, so the set has "
            f"{len(self.rows)} items. If you need more, your corpus may be too small "
            "for this analysis."
            if got < DRAW_MORE
            else ""
        )
        self.show()

    def action_finish(self) -> None:
        if not self.ready or self.pool_short or any(not r.labels for r in self.rows):
            return

        def done(approved: bool | None) -> None:
            if approved:
                # the test split stays on stage 6, which now shows the evaluation
                step = 1 if self.split == "dev" else 0
                self.app.goto_stage(self.app.stage + step)  # ty: ignore[unresolved-attribute]

        self.app.push_screen(ConfirmScreen("All items labelled. Continue?"), done)
