from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label, Select, Static

from hunches import candidates, files, search
from hunches.app import (
    AppFooter,
    ConfirmScreen,
    PanelTitle,
    StatusHeader,
    key_button,
    panel,
    retitle,
    say,
)
from hunches.screens.progress import LabelBar

RERUN = (
    "You've already run the searches, and haven't changed the seed candidates. "
    "Depending on the size of the corpus, this can take a long time. "
    "Are you sure you want to rerun searches?"
)
BAR_WIDTH = 30  # longest band bar, in cells
SEED_BAR_WIDTH = 12


def bar(n: int, biggest: int, width: int) -> str:
    """A block bar scaled to `biggest`; any non-zero count gets at least one cell."""
    if n <= 0 or biggest <= 0:
        return ""
    return "█" * max(1, round(width * n / biggest))


class SearchScreen(Screen):
    BINDINGS: ClassVar = [("r", "run", "Run search")]
    DEFAULT_CSS = """
    SearchScreen #top { height: 1; margin-bottom: 1; }
    SearchScreen #top > Button { width: auto; }
    SearchScreen #status { width: auto; margin-left: 2; }
    SearchScreen #progress { margin-left: 2; }
    SearchScreen #results { height: 1fr; }
    SearchScreen #results.-inactive { opacity: 40%; }
    SearchScreen #bands-panel { height: auto; }
    SearchScreen #bands { height: auto; }
    SearchScreen #seeds-panel { height: 1fr; }
    SearchScreen #seeds { height: auto; }
    SearchScreen #threshold { width: 10; margin-left: 1; }
    SearchScreen #threshold > SelectCurrent { padding: 0; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.embedder = None  # tests inject a stub; None means the configured model
        self.searching = False
        self.rows: list[dict] = []
        self.threshold = candidates.FLOOR  # top-seeds minimum similarity

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        with Horizontal(id="top"):
            yield key_button("Run search", "r", id="run", variant="primary")
            yield Label("", id="status")
            yield LabelBar(0, 0, "", align="left", id="progress")
        yield Static("", id="pool", classes="banner -stale")
        yield Label("", id="warning", classes="warn")
        yield Label("", id="error", classes="error")
        with Vertical(id="results"):
            with panel(Vertical(id="bands-panel"), "Candidates by similarity"):
                yield Static("", id="bands")
            with panel(
                VerticalScroll(id="seeds-panel"), "Top seeds", "similarity at or above"
            ):
                yield Static("", id="seeds")
        yield AppFooter()

    @staticmethod
    def cap_warning(top_k: int) -> str:
        return (
            f"WARNING: S3 returned its cap of {top_k:,} hits for at least one seed; "
            f"only the {top_k:,} highest-scoring hits are kept."
        )

    def on_mount(self) -> None:
        for id_ in ("#warning", "#error"):
            self.query_one(id_).display = False
        select = Select(
            [(f"{edge:g}", edge) for edge in candidates.BANDS],
            value=candidates.FLOOR,
            allow_blank=False,
            id="threshold",
            compact=True,
        )
        self.query_one("#seeds-panel").query_one(PanelTitle).mount(select)
        self.refresh_state()
        self.show(files.read_jsonl("candidates.jsonl"))  # resume: show the last run

    def refresh_state(self) -> None:
        """Button label, notes, dimming and the pool banner from the files and `searching`."""
        approved = files.read_state().seeds_approved
        exists = files.read_text("candidates.jsonl") is not None
        changed = exists and candidates.seeds_changed()
        button = self.query_one("#run", Button)
        if self.searching:
            button.label = "Searching…"
        elif exists and not changed:
            button.label = "Rerun search  r"
        else:
            button.label = "Run search  r"
        button.disabled = self.searching or not approved
        note = ""
        if not approved:
            note = "Seeds are not approved yet."
        elif changed and not self.searching:
            note = "Seeds changed, rerun needed"
        status = self.query_one("#status", Label)
        status.update(note)
        status.set_class(bool(note), "warn")
        status.display = bool(note)
        self.query_one("#progress").display = self.searching
        self.query_one("#results").set_class(not approved or not exists, "-inactive")
        count = len(files.read_jsonl("candidates.jsonl")) if exists else 0
        need = 2 * files.SAMPLE_SIZE
        say(
            self.query_one("#pool", Static),
            f"Only {count:,} candidates found. Labelling needs at least {need}: "
            f"{files.SAMPLE_SIZE} dev and {files.SAMPLE_SIZE} test."
            if exists and count < need and not self.searching
            else "",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_run()

    def action_run(self) -> None:
        if self.searching or not files.read_state().seeds_approved:
            return
        if files.read_text("candidates.jsonl") is not None and not (
            candidates.seeds_changed()
        ):
            self.app.push_screen(ConfirmScreen(RERUN), self.confirmed)
        else:
            self.start()

    def confirmed(self, yes: bool | None) -> None:
        if yes:
            self.start()

    def start(self) -> None:
        self.searching = True
        for id_ in ("#error", "#warning"):
            say(self.query_one(id_, Label), "")
        total = len(candidates.read_seeds())
        self.query_one("#progress", LabelBar).update_bar(total, 0, f"0/{total}")
        self.refresh_state()
        self.run_worker(self.run_search(), exclusive=True)

    def on_progress(self, done: int, total: int, seed: str) -> None:
        self.query_one("#progress", LabelBar).update_bar(
            total, done, f"{done}/{total}  {seed}"
        )

    async def run_search(self) -> None:
        try:
            capped = await candidates.build_candidates(self.embedder, self.on_progress)
        except Exception as e:  # noqa: BLE001  config/model/network errors must not kill the app
            message = f"Search failed: {e}"
            if "mismatch" in str(e):
                message += (
                    "\nFix: set embedding_model in .hunches/config.toml to the model "
                    "the corpus was embedded with."
                )
            say(self.query_one("#error", Label), message)
        else:
            if capped:
                say(
                    self.query_one("#warning", Label),
                    self.cap_warning(search.S3_TOP_K),
                )
            self.show(files.read_jsonl("candidates.jsonl"))
        self.searching = False
        self.refresh_state()

    def on_select_changed(self, event: Select.Changed) -> None:
        self.threshold = float(event.value)  # ty: ignore[invalid-argument-type]
        self.show_seeds()

    def color(self, name: str) -> str:
        return Color.parse(self.app.theme_variables[name]).hex6

    def show(self, rows: list[dict]) -> None:
        self.rows = rows
        counts = candidates.band_counts(rows)
        text = Text()
        for i, edge in enumerate(candidates.BANDS):
            last = i == len(candidates.BANDS) - 1
            name = f"{edge:g}+" if last else f"{edge:g}-{candidates.BANDS[i + 1]:g}"
            text.append(f"{name:<12}")
            text.append(
                f"{bar(counts[i], max(counts), BAR_WIDTH):<{BAR_WIDTH}}",
                self.color("primary"),
            )
            text.append(f"{counts[i]:>8,}", "bold")
            text.append("" if last else "\n")
        self.query_one("#bands", Static).update(text)
        retitle(self.query_one("#bands-panel"), subtitle=f"{len(rows):,} candidates")
        self.show_seeds()

    def show_seeds(self) -> None:
        top = candidates.top_seeds(self.rows, self.threshold)
        seeds = self.query_one("#seeds", Static)
        if not top:
            seeds.update(
                Text(
                    "No items at or above this similarity."
                    if self.rows
                    else "Run the search to see which seeds find the most items.",
                    "dim",
                )
            )
            return
        text = Text()
        for rank, (seed, n) in enumerate(top, 1):
            text.append(f"{rank:>3}  ", "dim")
            text.append(f"{n:>7,}  ", "bold")
            text.append(
                f"{bar(n, top[0][1], SEED_BAR_WIDTH):<{SEED_BAR_WIDTH}}",
                self.color("accent" if rank == 1 else "primary"),
            )
            text.append(f"  {seed}")
            text.append("" if rank == len(top) else "\n")
        seeds.update(text)
