import math
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Static
from textual.widgets.data_table import ColumnKey

from hunches import files
from hunches.app import (
    AppFooter,
    ConfirmScreen,
    StatusHeader,
    current_status,
    key_button,
    modal_box,
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
    taken = {r.id for r in gold} | {
        r["id"] for r in files.read_jsonl("gold_removed.jsonl")
    }
    pool = [c for c in files.read_jsonl("candidates.jsonl") if c["id"] not in taken]
    rng = random.Random(f"{Path.cwd().name}:{split}:{len(gold)}")
    rows = [
        files.GoldRow(id=c["id"], text=c["text"], labels=[], split=split)  # ty: ignore[invalid-argument-type]
        for c in rng.sample(pool, min(n, len(pool)))
    ]
    files.write_gold(gold + rows)  # persisted before the user sees anything
    return rows


def remove(ids: list[str], reason: str) -> int:
    """Move gold rows to the append-only gold_removed.jsonl (labels kept there); returns how many."""
    gold = files.read_gold()
    gone = [r for r in gold if r.id in set(ids)]
    if not gone:
        return 0
    ts = datetime.now(UTC).isoformat()
    for r in gone:
        files.append_jsonl(
            "gold_removed.jsonl", {**r.model_dump(), "reason": reason, "ts": ts}
        )
    files.write_gold([r for r in gold if r not in gone])
    return len(gone)


HELD_OUT = (
    "Test rows are held out so that the test result is an honest estimate. Replacing labelled "
    "test rows changes the items the result is measured on, and the test evaluation has to be "
    "run again. Do not remove rows because the classifier got them wrong."
)
STALE_REASON = "no longer in the candidate pool"


def rows_word(n: int) -> str:
    return f"{n} row{'' if n == 1 else 's'}"


def removal_text(rows: list[files.GoldRow], orphan_ids: set[str]) -> str:
    """What removing these rows does: how many are out of the pool, how many labels are discarded."""
    n = len(rows)
    out = sum(r.id in orphan_ids for r in rows)
    labelled = sum(bool(r.labels) for r in rows)
    splits = " and ".join(s for s in ("dev", "test") if any(r.split == s for r in rows))
    verb = "is" if n == 1 else "are"
    if out == n:
        head = f"{rows_word(n)} {verb} no longer in the candidate pool."
    else:
        head = f"{rows_word(n)} will be removed from the {splits} set{'s' if ' and ' in splits else ''}."
        if out:
            head += f" {out} of them {'is' if out == 1 else 'are'} no longer in the candidate pool."
    if n == 1:
        who = (
            "It is labelled; that 1 label is discarded."
            if labelled
            else "It has no labels; no labels are discarded."
        )
    elif not labelled:
        who = "None of them is labelled; no labels are discarded."
    elif labelled == 1:
        who = "1 of them is labelled; that 1 label is discarded."
    else:
        who = f"{labelled} of them are labelled; those {labelled} labels are discarded."
    return f"{head} {who} The rows are kept in gold_removed.jsonl and are never drawn again."


class RemoveGoldScreen(ModalScreen[bool]):
    """Confirm removing gold rows, for the Gold screen (the user) and remove_gold (the assistant, who
    gives a `reason`). Nothing is written before Remove is pressed."""

    AUTO_FOCUS = "#cancel"
    BINDINGS: ClassVar = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    RemoveGoldScreen > Vertical { height: auto; }
    RemoveGoldScreen Static { height: auto; margin-bottom: 1; }
    RemoveGoldScreen .buttons Button { margin-left: 1; }
    """

    def __init__(self, rows: list[files.GoldRow], reason: str | None = None) -> None:
        super().__init__()
        self.rows = rows
        self.reason = reason
        what = " and ".join(
            f"{n} {split} row{'' if n == 1 else 's'}"
            for split in ("dev", "test")
            if (n := sum(r.split == split for r in rows))
        )
        self.heading = (
            f"Remove {what}?"
            if reason is None
            else f"The assistant wants to remove {what}"
        )
        self.body = removal_text(rows, {r.id for r in files.orphaned_gold()})
        if reason is not None:
            self.body += f"\n\nReason: {reason}"
        self.warning = HELD_OUT if any(r.split == "test" for r in rows) else ""
        self.text = self.body + (f"\n\n{self.warning}" if self.warning else "")

    def compose(self) -> ComposeResult:
        with modal_box(Vertical(), self.heading):
            yield Static(self.body, id="body", markup=False)
            if self.warning:
                yield Static(self.warning, id="held-out", classes="warn", markup=False)
            with Horizontal(classes="buttons"):
                yield key_button(
                    "Cancel" if self.reason is None else "Reject", "Esc", id="cancel"
                )
                yield Button(
                    f"Remove {rows_word(len(self.rows))}", id="remove", variant="error"
                )

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "remove")


def ask_removal(screen: Screen, rows: list[files.GoldRow], then) -> None:
    """Ask the user to confirm removing `rows` (their own choice); on yes remove them and call `then(rows)`."""
    stale = {r.id for r in files.orphaned_gold()}

    def answered(yes: bool | None) -> None:
        if yes:
            remove(
                [r.id for r in rows],
                STALE_REASON
                if all(r.id in stale for r in rows)
                else "removed by the user",
            )
            current_status(fresh=True)  # the rail and banners follow at once
            then(rows)

    screen.app.push_screen(RemoveGoldScreen(rows), answered)


TEXT = ColumnKey("text")


class GoldRowsScreen(ModalScreen[list[files.GoldRow]]):
    """Every row of a split with its pool status; remove the selected row or the stale ones.
    Dismisses with the rows removed while it was open."""

    AUTO_FOCUS = "#rows"
    BINDINGS: ClassVar = [
        ("escape", "close", "Close"),
        ("delete", "remove_row", "Remove row"),
        ("x", "remove_stale", "Remove stale rows"),
    ]
    DEFAULT_CSS = """
    GoldRowsScreen > Vertical { width: 1fr; height: 1fr; margin: 1 2; padding: 0 1; }
    GoldRowsScreen #summary { height: auto; color: $text-muted; }
    GoldRowsScreen #rows-panel { height: 1fr; }
    GoldRowsScreen #rows { height: 1fr; }
    GoldRowsScreen .buttons Button { margin-left: 1; }
    """

    def __init__(self, split: str) -> None:
        super().__init__()
        self.split = split
        self.removed: list[files.GoldRow] = []
        self.shown: list[files.GoldRow] = []

    def compose(self) -> ComposeResult:
        with modal_box(Vertical(), f"{self.split} set rows"):
            yield Static("", id="summary", markup=False)
            with panel(Vertical(id="rows-panel"), "rows"):
                yield DataTable(id="rows", cursor_type="row")
            with Horizontal(classes="buttons"):
                yield key_button("Remove row", "Del", id="remove-row", variant="error")
                yield key_button("Remove stale rows", "x", id="remove-stale")
                yield key_button("Close", "Esc", id="close", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#rows", DataTable)
        table.add_column(Text("#", justify="right"), width=4)
        table.add_column("Pool", width=9)
        table.add_column("Labels", width=16)
        table.add_column("Text", key="text", width=20)
        self.fill()

    def on_resize(self) -> None:
        self.call_after_refresh(self.fill)

    def fill(self) -> None:
        table = self.query_one("#rows", DataTable)
        taxonomy = files.read_taxonomy()
        names = files.all_labels(taxonomy)
        stale = {r.id for r in files.orphaned_gold(self.split)}
        self.shown = [r for r in files.read_gold() if r.split == self.split]
        keep = table.cursor_row
        table.columns[TEXT].width = max(10, table.size.width - 4 - 9 - 16 - 4 * 2 - 2)
        table.clear()
        for i, r in enumerate(self.shown, 1):
            labels = Text(" ").join(label_text(names, n) for n in r.labels) or Text(
                "unlabelled", style="dim"
            )
            table.add_row(
                Text(str(i), justify="right"),
                Text("ORPHANED", style="bold reverse") if r.id in stale else "in pool",
                labels,
                Text(r.text.replace("\n", " "), no_wrap=True, overflow="ellipsis"),
                key=r.id,
            )
        if self.shown:
            table.move_cursor(row=min(keep, len(self.shown) - 1))
        labelled = sum(bool(r.labels) for r in self.shown)
        self.query_one("#summary", Static).update(
            f"{len(self.shown)} rows · {labelled} labelled · {len(stale)} orphaned. "
            "Orphaned rows are not in the candidate pool any more."
        )
        self.query_one("#remove-stale", Button).disabled = not stale
        self.query_one("#remove-row", Button).disabled = not self.shown

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if (
            action == "remove_stale"
            and self.query_one("#remove-stale", Button).disabled
        ):
            return None
        return True

    def asked(self, rows: list[files.GoldRow]) -> None:
        if rows:
            ask_removal(self, rows, self.removed_rows)

    def removed_rows(self, rows: list[files.GoldRow]) -> None:
        self.removed += rows
        self.fill()
        self.refresh_bindings()

    def action_remove_row(self) -> None:
        table = self.query_one("#rows", DataTable)
        if self.shown:
            self.asked([self.shown[table.cursor_row]])

    def action_remove_stale(self) -> None:
        self.asked(files.orphaned_gold(self.split))

    def action_close(self) -> None:
        self.dismiss(self.removed)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        match event.button.id:
            case "remove-row":
                self.action_remove_row()
            case "remove-stale":
                self.action_remove_stale()
            case "close":
                self.action_close()


class GoldScreen(Screen):
    """Label a random sample of candidates one at a time (stage 4 dev, stage 6 test)."""

    BINDINGS: ClassVar = [
        ("left", "move(-1)", "Back"),
        ("right", "move(1)", "Skip"),
        ("enter", "confirm", "Confirm labels"),
        ("d", "draw_more", "Draw 10 more"),
        ("r", "rows", "Rows"),
        ("x", "remove_stale", "Remove stale rows"),
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
    GoldScreen #orphans { height: auto; }
    GoldScreen #remove-stale { width: auto; margin: 1 0; }
    GoldScreen #info { width: 1fr; }
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
        self.info = (
            ""  # banner: rows were removed; cleared on the next label, move or draw
        )
        self.stale: set[str] = (
            set()
        )  # ids of this split's rows not in the candidate pool
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
                with Vertical(id="orphans"):
                    yield Static(
                        "", id="orphan-banner", classes="banner -warning", markup=False
                    )
                    yield key_button("Remove stale rows", "x", id="remove-stale")
                yield Static("", id="info", classes="banner -info", markup=False)
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
                    yield key_button("Rows", "r", id="show-rows")
        yield AppFooter()

    def on_mount(self) -> None:
        if not self.ready:
            return
        # after a removal the user draws the replacements (Draw N replacements), nothing is drawn here
        removed = any(
            r["split"] == self.split for r in files.read_jsonl("gold_removed.jsonl")
        )
        if len(self.rows) < files.SAMPLE_SIZE and not removed:
            self.add_rows(files.SAMPLE_SIZE - len(self.rows))
        table = self.query_one("#counts", DataTable)
        table.add_column("Label")
        table.add_column(Text("Count", justify="right"))
        if len(self.rows) < files.SAMPLE_SIZE and not removed:
            self.block()
            return
        self.stale = {r.id for r in files.orphaned_gold(self.split)}
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
        retitle(
            self.query_one("#item"),
            f"item {row.id}" if row else "item",
            "[b reverse $warning] ORPHANED [/]" if row and row.id in self.stale else "",
        )
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
        say(self.query_one("#info", Static), self.info)
        orphans = [r for r in self.rows if r.id in self.stale]
        say(
            self.query_one("#orphan-banner", Static),
            f"ORPHANED: {len(orphans)} of {total} {self.split} rows are no longer in the "
            f"candidate pool ({sum(bool(r.labels) for r in orphans)} labelled)."
            if orphans
            else "",
        )
        self.query_one("#orphans").display = bool(orphans)
        retitle(
            self.query_one("#counts-panel"),
            subtitle=f"{done} of {total}"
            + (f" · {len(orphans)} orphaned" if orphans else ""),
        )
        table = self.query_one("#counts", DataTable)
        table.clear()
        for name in files.all_labels(self.taxonomy):
            table.add_row(
                label_text(names, name),
                Text(str(sum(name in r.labels for r in self.rows)), justify="right"),
                key=name,
            )
        short = total < files.SAMPLE_SIZE  # rows were removed: draw replacements first
        self.query_one("#finish", Button).disabled = left > 0 or short
        more = self.query_one("#more", Button)
        missing = files.SAMPLE_SIZE - total
        more.label = (
            f"Draw {missing} replacement{'' if missing == 1 else 's'}  d"
            if short
            else f"Draw {DRAW_MORE} more  d"
        )
        more.variant = "primary" if short else "default"
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
        if self.pool_short and action in (
            "move",
            "confirm",
            "draw_more",
            "finish",
            "rows",
            "remove_stale",
        ):
            return False
        if action == "finish" and (
            any(not r.labels for r in self.rows) or len(self.rows) < files.SAMPLE_SIZE
        ):
            return None  # dimmed until every row is labelled
        if action == "remove_stale" and not self.stale:
            return None
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
            case "show-rows":
                self.action_rows()
            case "remove-stale":
                self.action_remove_stale()

    def on_key(self, event) -> None:
        name = self.keys.get(event.character or "")
        if name is None or not self.rows or self.pool_short:
            return
        event.stop()
        self.note = self.exhausted = self.info = ""
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
        self.note = self.exhausted = self.info = ""
        self.celebrate = False
        self.show()

    def action_draw_more(self) -> None:
        if not self.ready or self.pool_short:
            return
        n = (
            max(files.SAMPLE_SIZE - len(self.rows), 0) or DRAW_MORE
        )  # replacements, or 10 more
        got = self.add_rows(n)
        self.info = ""
        self.exhausted = (
            f"No more candidates to draw: only {got} were left, so the set has "
            f"{len(self.rows)} items. If you need more, your corpus may be too small "
            "for this analysis."
            if got < n
            else ""
        )
        self.show()

    def action_rows(self) -> None:
        if self.ready and not self.pool_short:
            self.app.push_screen(GoldRowsScreen(self.split), self.rows_closed)

    def action_remove_stale(self) -> None:
        if self.stale:
            ask_removal(self, files.orphaned_gold(self.split), self.removed)

    def rows_closed(self, removed: list[files.GoldRow] | None) -> None:
        if removed:
            self.removed(removed)

    def removed(self, gone: list[files.GoldRow]) -> None:
        """Follow rows that were removed: reload them, say what happened, and show what is missing."""
        n = len(gone)
        discarded = sum(bool(r.labels) for r in gone)
        every = all(r.id in self.stale for r in gone)
        self.all = files.read_gold()
        self.rows = [r for r in self.all if r.split == self.split]
        self.stale = {r.id for r in files.orphaned_gold(self.split)}
        self.index = min(self.index, max(len(self.rows) - 1, 0))
        self.pending = list(self.rows[self.index].labels) if self.rows else []
        missing = files.SAMPLE_SIZE - len(self.rows)
        self.info = (
            f"Removed {n} {'stale ' if every else ''}row{'' if n == 1 else 's'} "
            f"({discarded} label{'' if discarded == 1 else 's'} discarded). "
            f"The set has {len(self.rows)} of {files.SAMPLE_SIZE} rows."
            + (
                f" Draw {missing} replacement{'' if missing == 1 else 's'} to continue."
                if missing > 0
                else ""
            )
            + (
                " The test result is stale until you re-run it."
                if self.split == "test"
                else ""
            )
        )
        self.exhausted = self.note = ""
        self.show()

    def action_finish(self) -> None:
        if (
            not self.ready
            or self.pool_short
            or any(not r.labels for r in self.rows)
            or len(self.rows) < files.SAMPLE_SIZE
        ):
            return

        def done(approved: bool | None) -> None:
            if approved:
                # the test split stays on stage 6, which now shows the evaluation
                step = 1 if self.split == "dev" else 0
                self.app.goto_stage(self.app.stage + step)  # ty: ignore[unresolved-attribute]

        self.app.push_screen(ConfirmScreen("All items labelled. Continue?"), done)
