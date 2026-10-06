from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, SelectionList, Static
from textual.widgets.data_table import ColumnKey

from hunches import files
from hunches.app import RAIL_WIDTH, AppFooter, StatusHeader, panel, retitle, wide
from hunches.theme import label_text

# Rendering 100k DataTable rows takes ~10 s, so only the first matches are drawn.
MAX_ROWS = 1000
NARROW = 100  # below this many content columns the detail pane moves under the table


class BrowseScreen(Screen):
    """Stage 9: browse results.jsonl. Loaded once, filtered in memory."""

    AUTO_FOCUS = "#table"
    DEFAULT_CSS = """
    BrowseScreen #body { height: 1fr; }
    BrowseScreen #labels-panel { width: 24; height: 100%; }
    BrowseScreen #main { width: 1fr; layout: horizontal; }
    BrowseScreen #table-panel { width: 2fr; height: 100%; }
    BrowseScreen #detail-panel { width: 1fr; height: 100%; }
    BrowseScreen.-narrow #main { layout: vertical; }
    BrowseScreen.-narrow #table-panel { width: 100%; height: 1fr; }
    BrowseScreen.-narrow #detail-panel { width: 100%; height: 5; }
    BrowseScreen #empty { color: $text-muted; }
    """

    def __init__(self) -> None:
        super().__init__()
        # failed rows from an interrupted run carry an "error" key and are not results
        self.rows = [r for r in files.read_jsonl("results.jsonl") if "error" not in r]
        self.lower = [r["text"].lower() for r in self.rows]
        self.shown: list[int] = []  # indexes into self.rows, in table order
        self.names = files.all_labels(files.read_taxonomy())
        self.names += sorted(
            {x for r in self.rows for x in r["labels"]} - set(self.names)
        )

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        yield Input(placeholder="Search text (case-insensitive)", id="search")
        with Horizontal(id="body"):
            with panel(Vertical(id="labels-panel"), "labels"):
                yield SelectionList[str](
                    *[(label_text(self.names, n), n) for n in self.names], id="labels"
                )
            with Horizontal(id="main"):
                with panel(Vertical(id="table-panel"), "results.jsonl"):
                    yield DataTable(id="table", cursor_type="row")
                    yield Static("", id="empty")
                with panel(Vertical(id="detail-panel"), "item"):
                    yield Static("", id="detail", markup=False)
        yield AppFooter()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.add_column("ID", width=8)
        table.add_column("Labels", key="labels", width=30)
        table.add_column(Text("Sim", justify="right"), width=7)
        table.add_column(
            "Text", key="text", width=20
        )  # fixed; refresh_table resizes it
        self.on_resize()

    def on_resize(self) -> None:
        # the rail takes 26 columns, so judge the room by the content column
        room = self.size.width - (RAIL_WIDTH if wide(self.app) else 0)
        narrow = room < NARROW
        self.set_class(narrow, "-narrow")
        table = self.query_one("#table", DataTable)
        table.columns[ColumnKey("labels")].width = 30 if room >= 120 else 16
        self.call_after_refresh(
            self.refresh_table
        )  # the Text column needs the laid-out width

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
        # DataTable has no flex column: Text takes what the others leave (+2 padding per column)
        table.columns[ColumnKey("text")].width = max(
            4,
            table.size.width
            - 8
            - table.columns[ColumnKey("labels")].width
            - 7
            - 4 * 2
            - 2,
        )
        clip = lambda t: Text(t, no_wrap=True, overflow="ellipsis")
        table.add_rows(
            (
                r["id"],
                clip("")
                + Text(", ").join(label_text(self.names, n) for n in r["labels"]),
                Text(f"{r['max_similarity']:.3f}", justify="right"),
                clip(r["text"].replace("\n", " ")),
            )
            for r in (self.rows[i] for i in self.shown)
        )
        empty = self.query_one("#empty", Static)
        table.display = bool(self.shown)
        empty.display = not self.shown
        empty.update(
            "No results match."
            if self.rows
            else "results.jsonl is empty. Run stage 8 first."
        )
        retitle(
            self.query_one("#table-panel"),
            subtitle=f"Showing {len(self.shown)} of {len(self.rows)}"
            + (f" ({matches} match; refine the search)" if matches > MAX_ROWS else ""),
        )
        self.show_detail()

    def show_detail(self) -> None:
        table = self.query_one("#table", DataTable)
        row = None
        if self.shown and table.cursor_row < len(self.shown):
            row = self.rows[self.shown[table.cursor_row]]
        self.query_one("#detail", Static).update(row["text"] if row else "")
        retitle(self.query_one("#detail-panel"), f"item {row['id']}" if row else "item")

    def on_input_changed(self, event: Input.Changed) -> None:
        self.refresh_table()

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        self.refresh_table()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.show_detail()
