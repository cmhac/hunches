from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, SelectionList, Static

from hunches import files
from hunches.app import StatusHeader

# Rendering 100k DataTable rows takes ~10 s, so only the first matches are drawn.
MAX_ROWS = 1000


class BrowseScreen(Screen):
    """Stage 9: browse results.jsonl. Loaded once, filtered in memory."""

    AUTO_FOCUS = "#table"
    DEFAULT_CSS = """
    BrowseScreen #count { height: auto; padding: 0 1; }
    BrowseScreen #body { height: 1fr; }
    BrowseScreen #labels { width: 24; height: 100%; }
    BrowseScreen #table { width: 2fr; }
    BrowseScreen #detail { width: 1fr; padding: 0 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        # failed rows from an interrupted run carry an "error" key and are not results
        self.rows = [r for r in files.read_jsonl("results.jsonl") if "error" not in r]
        self.lower = [r["text"].lower() for r in self.rows]
        self.shown: list[int] = []  # indexes into self.rows, in table order

    def compose(self) -> ComposeResult:
        names = files.all_labels(files.read_taxonomy())
        names += sorted({x for r in self.rows for x in r["labels"]} - set(names))
        yield StatusHeader()
        yield Static("", id="count", markup=False)
        yield Input(placeholder="Search text (case-insensitive)", id="search")
        with Horizontal(id="body"):
            yield SelectionList[str](*[(n, n) for n in names], id="labels")
            with Vertical():
                yield DataTable(id="table", cursor_type="row")
            yield Static("", id="detail", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#table", DataTable).add_columns("ID", "Labels", "Sim", "Text")
        self.refresh_table()

    def refresh_table(self) -> None:
        needle = self.query_one("#search", Input).value.strip().lower()
        wanted = set(self.query_one("#labels", SelectionList).selected)
        self.shown = [
            i
            for i, r in enumerate(self.rows)
            if (not needle or needle in self.lower[i])
            and (not wanted or wanted.intersection(r["labels"]))
        ]
        matches = len(self.shown)
        self.shown = self.shown[:MAX_ROWS]
        table = self.query_one("#table", DataTable)
        table.clear()
        table.add_rows(
            (
                r["id"],
                ", ".join(r["labels"]),
                f"{r['max_similarity']:.3f}",
                r["text"].replace("\n", " ")[:80],
            )
            for r in (self.rows[i] for i in self.shown)
        )
        self.query_one("#count", Static).update(
            f"Showing {len(self.shown)} of {len(self.rows)}"
            + (f" ({matches} match; refine the search)" if matches > MAX_ROWS else "")
        )
        self.show_detail()

    def show_detail(self) -> None:
        table = self.query_one("#table", DataTable)
        text = ""
        if self.shown and table.cursor_row < len(self.shown):
            text = self.rows[self.shown[table.cursor_row]]["text"]
        self.query_one("#detail", Static).update(text)

    def on_input_changed(self, event: Input.Changed) -> None:
        self.refresh_table()

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        self.refresh_table()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.show_detail()
