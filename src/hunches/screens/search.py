from collections import Counter
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Label, Static

from hunches import candidates, files, search
from hunches.app import StatusHeader


class SearchScreen(Screen):
    BINDINGS: ClassVar = [("r", "run", "Run search")]
    DEFAULT_CSS = """
    SearchScreen DataTable { height: 1fr; }
    SearchScreen #warning { color: $warning; }
    SearchScreen #error { color: $error; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.embedder = None  # tests inject a stub; None means the configured model

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        with Vertical():
            yield Button("Run search (r)", id="run")
            yield Label("", id="status")
            yield Label("", id="warning")
            yield Label("", id="error")
            yield DataTable(id="bands")
            yield Static("", id="seeds")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#bands", DataTable)
        table.add_columns("Band", "Candidates", "At or above")
        if not files.read_state().seeds_approved:
            self.query_one("#status", Label).update("Seeds are not approved yet.")
        self.show(files.read_jsonl("candidates.jsonl"))  # resume: show the last run

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_run()

    def action_run(self) -> None:
        self.query_one("#run", Button).disabled = True
        self.query_one("#error", Label).update("")
        self.query_one("#warning", Label).update("")
        self.query_one("#status", Label).update("Searching...")
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
            self.query_one("#error", Label).update(message)
        else:
            rows = files.read_jsonl("candidates.jsonl")
            status.update(
                f"Done. {len(rows)} candidates written to candidates.jsonl. Re-running "
                "overwrites it; gold labels refer to ids and stay valid, but refresh "
                "sample sets if the candidate set changed a lot."
            )
            if capped:
                self.query_one("#warning", Label).update(
                    f"WARNING: S3 returned its topK cap of {search.S3_TOP_K:,} hits for "
                    "at least one seed; only the highest-scoring hits are kept."
                )
            self.show(rows)
        self.query_one("#run", Button).disabled = False

    def show(self, rows: list[dict]) -> None:
        table = self.query_one("#bands", DataTable)
        table.clear()
        counts = candidates.band_counts(rows)
        for i, edge in enumerate(candidates.BANDS):
            last = i == len(candidates.BANDS) - 1
            name = f"{edge:g}+" if last else f"{edge:g}-{candidates.BANDS[i + 1]:g}"
            table.add_row(name, str(counts[i]), str(sum(counts[i:])))
        table.add_row("Total", str(len(rows)), "")
        top = Counter(r["best_seed"] for r in rows).most_common(10)
        self.query_one("#seeds", Static).update(
            "Best seed (items won):\n" + "\n".join(f"{n:>6}  {s}" for s, n in top)
            if top
            else ""
        )
