import random
from pathlib import Path
from typing import ClassVar

from pydantic_ai.models import Model
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from hunches import files
from hunches.app import ConfirmScreen, StatusHeader, panel, retitle, say
from hunches.classifier import Prediction, classify
from hunches.theme import label_color, label_tag, label_text

DRAW_MORE = 10


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
    GoldScreen #main { height: 1fr; }
    GoldScreen #left { width: 1fr; }
    GoldScreen #item { height: 1fr; }
    GoldScreen #labels-panel { height: auto; }
    GoldScreen #labels, GoldScreen #prediction, GoldScreen #note, GoldScreen #progress { height: auto; }
    GoldScreen #counts-panel { width: 36%; max-width: 30; height: auto; max-height: 100%; }
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
        self.prompt = files.read_text("prompt.md") or ""
        self.model: str | Model = files.read_config().classifier_model
        self.all = files.read_gold()
        self.rows = [r for r in self.all if r.split == split]
        self.predictions: dict[str, Prediction | None] = {}  # None while running
        self.pending: list[str] = []  # multi mode: labels toggled but not yet confirmed
        self.index = 0
        self.note = ""
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
            yield Footer()
            return
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static("", id="progress")
                with panel(Vertical(id="item", classes="-focused"), "item"):
                    yield Static("", id="text", markup=False)
                with panel(Vertical(id="labels-panel"), "labels"):
                    yield Static("", id="labels")
                yield Static("", id="prediction")
                yield Static("", id="note", classes="warn", markup=False)
            with panel(Vertical(id="counts-panel"), "counts"):
                yield DataTable(id="counts")
        yield Footer()

    def on_mount(self) -> None:
        if not self.ready:
            return
        if len(self.rows) < files.SAMPLE_SIZE:
            self.add_rows(files.SAMPLE_SIZE - len(self.rows))
        table = self.query_one("#counts", DataTable)
        table.add_column("Label")
        table.add_column(Text("Count", justify="right"))
        self.index = next((i for i, r in enumerate(self.rows) if not r.labels), 0)
        self.show()

    def add_rows(self, n: int) -> None:
        new = draw(self.split, n)
        self.all += new
        self.rows += new
        if len(new) < n:
            self.note = f"Only {len(new)} unlabelled candidates were left to draw."

    def show(self) -> None:
        row = self.rows[self.index] if self.rows else None
        done = sum(bool(r.labels) for r in self.rows)
        strong = lambda x: f"[b #EEF1F5]{x}[/]"
        self.query_one("#progress", Static).update(
            f"[b $primary]{self.split} set[/]  item {strong(self.index + 1)}/{strong(len(self.rows))}, "
            f"{strong(done)} labelled"
        )
        self.query_one("#text", Static).update(row.text if row else "")
        retitle(self.query_one("#item"), f"item {row.id}" if row else "item")
        single = self.taxonomy.mode == "single"
        panel = self.query_one("#labels-panel")
        retitle(
            panel,
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
                f"[b on $boost] {key} [/] [{color}]{mark}[/] "
                f"[{'b ' if on else ''}#EEF1F5]{escape(name)}[/]"
            )
            if descriptions.get(name):
                line += f"  [$text-muted]{escape(descriptions[name])}[/]"
            lines.append(f"[on $surface]{line}[/]" if on else line)
        self.query_one("#labels", Static).update("\n".join(lines))
        say(self.query_one("#note", Static), self.note)
        self.show_prediction()
        retitle(self.query_one("#counts-panel"), subtitle=f"{done} of {len(self.rows)}")
        table = self.query_one("#counts", DataTable)
        table.clear()
        for name in files.all_labels(self.taxonomy):
            table.add_row(
                label_text(names, name),
                Text(str(sum(name in r.labels for r in self.rows)), justify="right"),
                key=name,
            )

    def show_prediction(self) -> None:
        """Only after the user has labelled the item, to avoid anchoring."""
        row = self.rows[self.index] if self.rows else None
        names = [lab.name for lab in self.taxonomy.labels]
        line = ""
        failed = False
        if row and row.labels:
            if row.id not in self.predictions:
                line = "[$text-muted]Model: (not classified)[/]"
            elif (p := self.predictions[row.id]) is None:
                line = "[$text-muted]Model: classifying...[/]"
            elif p.labels is None:
                line = f"Model: failed ({escape(str(p.error))})"
                failed = True
            else:
                tags = "  ".join(label_tag(names, n) for n in p.labels)
                verdict = (
                    "[$success]✓ agrees[/]"
                    if set(p.labels) == set(row.labels)
                    else "[b reverse $secondary] DIFFERS [/]"
                )
                line = f"Model: {tags} {verdict}"
        prediction = self.query_one("#prediction", Static)
        prediction.set_classes("error" if failed else "")
        prediction.update(line)

    def on_key(self, event) -> None:
        name = self.keys.get(event.character or "")
        if name is None or not self.rows:
            return
        event.stop()
        self.note = ""
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
        if not self.rows:
            return
        row = self.rows[self.index]
        try:
            files.validate_labels(self.pending, self.taxonomy)
        except ValueError as e:
            self.note = f"Not saved: {e}"
            self.show()
            return
        row.labels = list(self.pending)
        files.write_gold(self.all)
        previous = self.predictions.get(row.id, "new")
        if previous == "new" or (previous and previous.labels is None):
            self.predictions[row.id] = None
            self.run_worker(self.predict(row.id, row.text))
        self.note = ""
        self.action_move(1, clamp=True)

    async def predict(self, row_id: str, text: str) -> None:
        try:
            p = await classify(text, self.prompt, self.taxonomy, self.model)
        except Exception as e:  # noqa: BLE001  auth/network errors must not kill the app
            p = Prediction(None, error=str(e))
        self.predictions[row_id] = p
        self.show_prediction()

    def action_move(self, step: int, clamp: bool = False) -> None:
        if not self.rows:
            return
        i = self.index + step
        if not 0 <= i < len(self.rows):
            if clamp:
                i = self.index
            else:
                return
        self.index = i
        self.pending = list(self.rows[i].labels)
        self.note = ""
        self.show()

    def action_draw_more(self) -> None:
        if not self.ready:
            return
        self.add_rows(DRAW_MORE)
        self.show()

    def action_finish(self) -> None:
        if not self.ready:
            return
        left = sum(not r.labels for r in self.rows)
        if left:
            self.note = f"{left} items still unlabelled."
            self.show()
            return

        def done(approved: bool | None) -> None:
            if approved:
                # the test split stays on stage 6, which now shows the evaluation
                step = 1 if self.split == "dev" else 0
                self.app.goto_stage(self.app.stage + step)  # ty: ignore[unresolved-attribute]

        self.app.push_screen(ConfirmScreen("All items labelled. Continue?"), done)
