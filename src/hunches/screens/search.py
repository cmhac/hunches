from collections import Counter
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.markup import escape
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Label, Static

from hunches import candidates, files, search
from hunches.app import StatusHeader, panel


class SearchScreen(Screen):
    BINDINGS: ClassVar = [("r", "run", "Run search")]
    DEFAULT_CSS = """
    SearchScreen #top { height: 1; }
    SearchScreen #status { margin-left: 2; }
    SearchScreen #bands-panel { height: auto; }
    SearchScreen DataTable { height: auto; }
    SearchScreen #seeds-panel { height: 1fr; }
    SearchScreen #seeds { height: auto; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.embedder = None  # tests inject a stub; None means the configured model

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        with Horizontal(id="top"):
            yield Button("Run search (r)", id="run", compact=True)
            yield Label("", id="status", classes="note")
        yield Label("", id="done", classes="ok")
        yield Label("", id="warning", classes="warn")
        yield Label("", id="error", classes="error")
        with panel(Vertical(id="bands-panel"), "candidates.jsonl · by similarity band"):
            yield DataTable(id="bands")
        with panel(VerticalScroll(id="seeds-panel"), "best seed (items won)"):
            yield Static("", id="seeds")
        yield Footer()

    def tell(self, id_: str, text: str) -> None:
        """Set one of the message lines; an empty one takes no row."""
        label = self.query_one(id_, Label)
        label.update(text)
        label.display = bool(text)

    def on_mount(self) -> None:
        for id_ in ("#done", "#warning", "#error"):
            self.query_one(id_).display = False
        table = self.query_one("#bands", DataTable)
        table.add_column("Band", width=13)
        table.add_column(Text("Candidates", justify="right"))
        table.add_column(Text("At or above", justify="right"))
        if not files.read_state().seeds_approved:
            status = self.query_one("#status", Label)
            status.update("Seeds are not approved yet.")
            status.set_classes("warn")
        self.show(files.read_jsonl("candidates.jsonl"))  # resume: show the last run

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_run()

    def action_run(self) -> None:
        self.query_one("#run", Button).disabled = True
        for id_ in ("#error", "#warning", "#done"):
            self.tell(id_, "")
        status = self.query_one("#status", Label)
        status.update("Searching...")
        status.set_classes("note")
        self.run_worker(self.run_search(), exclusive=True)

    async def run_search(self) -> None:
        status = self.query_one("#status", Label)
        try:
            capped = await candidates.build_candidates(self.embedder)
        except Exception as e:  # noqa: BLE001  config/model/network errors must not kill the app
            message = f"Search failed: {e}"
            if "mismatch" in str(e):
                message += (
                    "\nFix: set embedding_model in .hunches/config.toml to the model "
                    "the corpus was embedded with."
                )
            status.update("")
            self.tell("#error", message)
        else:
            rows = files.read_jsonl("candidates.jsonl")
            status.update("")
            self.tell(
                "#done",
                f"Done. {len(rows):,} candidates written to candidates.jsonl. Re-running "
                "overwrites it; gold labels refer to ids and stay valid, but refresh "
                "sample sets if the candidate set changed a lot.",
            )
            if capped:
                self.tell(
                    "#warning",
                    f"WARNING: S3 returned its topK cap of {search.S3_TOP_K:,} hits for "
                    "at least one seed; only the highest-scoring hits are kept.",
                )
            self.show(rows)
        self.query_one("#run", Button).disabled = False

    def show(self, rows: list[dict]) -> None:
        table = self.query_one("#bands", DataTable)
        table.clear()
        right = lambda n: Text(f"{n:,}" if n is not None else "", justify="right")
        counts = candidates.band_counts(rows)
        for i, edge in enumerate(candidates.BANDS):
            last = i == len(candidates.BANDS) - 1
            name = f"{edge:g}+" if last else f"{edge:g}-{candidates.BANDS[i + 1]:g}"
            table.add_row(name, right(counts[i]), right(sum(counts[i:])))
        table.add_row(
            Text("Total", style="bold"),
            Text(f"{len(rows):,}", "bold", justify="right"),
            "",
        )
        top = Counter(r["best_seed"] for r in rows).most_common(10)
        self.query_one("#seeds", Static).update(
            "\n".join(f"[b #EEF1F5]{n:>6}[/]  {escape(s)}" for s, n in top)
            if top
            else "[$text-muted]Run the search to see which seeds find the most items.[/]"
        )
