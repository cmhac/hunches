import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Static

from hunches import cost, files, metrics
from hunches.app import AppFooter, StatusHeader, panel, retitle, say
from hunches.classifier import classify_many
from hunches.screens import report
from hunches.screens.gold import GoldScreen

RESULT = "test_result.json"


def test_stage() -> Screen:
    """Stage 6: label the test set first (GoldScreen), then show the held-out evaluation."""
    rows = [r for r in files.read_gold() if r.split == "test"]
    if not rows or any(not r.labels for r in rows):
        return GoldScreen("test")
    return FinalScreen()


def prompt_hash() -> str:
    # JSON keeps ("ab", "c") and ("a", "bc") distinct
    data = [files.read_text("prompt.md") or "", files.read_config().classifier_model]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


class FinalScreen(Screen):
    """Stage 6: the test set is classified once; the result goes stale if prompt.md or the classifier model changes."""

    BINDINGS: ClassVar = [
        ("r", "rerun", "Re-run"),
        ("t", "tune", "Back to tuning"),
        ("f2", "accept", "Accept"),
    ]
    AUTO_FOCUS = "#dis"
    DEFAULT_CSS = """
    FinalScreen #metrics-panel { height: auto; }
    FinalScreen #metrics-panel DataTable { height: auto; }
    FinalScreen #warning, FinalScreen #summary, FinalScreen #note { height: auto; }
    FinalScreen #body { height: 1fr; }
    FinalScreen #dis-panel { width: 3fr; }
    FinalScreen #text-panel { width: 2fr; }
    FinalScreen #dis { height: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.taxonomy = files.read_taxonomy()
        self.config = files.read_config()
        self.model = self.config.classifier_model
        self.rows = [r for r in files.read_gold() if r.split == "test" and r.labels]
        text = files.read_text(RESULT)
        self.result: dict | None = json.loads(text) if text else None
        self.running = False
        self.note = ""

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        yield Static("", id="banner", classes="banner -stale", markup=False)
        with panel(Vertical(id="metrics-panel"), "test set · held out"):
            yield Static(
                "Tuning against test disagreements weakens this held-out result.",
                id="warning",
                classes="note",
            )
            yield Static("", id="summary")
            yield DataTable(id="per-label")
        with Horizontal(id="body"):
            with panel(Vertical(id="dis-panel"), "disagreements"):
                yield DataTable(id="dis", cursor_type="row")
            with panel(Vertical(id="text-panel"), "text"):
                yield Static("", id="detail", markup=False)
        yield Static("", id="note", markup=False)
        yield AppFooter()

    def on_mount(self) -> None:
        report.disagreement_columns(self.query_one("#dis", DataTable))
        report.per_label_columns(self.query_one("#per-label", DataTable))
        self.show()
        if self.result is None:  # the one and only automatic run
            self.action_rerun()

    def on_resize(self) -> None:
        self.call_after_refresh(self.show)  # needs the laid-out table width

    def stale(self) -> bool:
        return self.result is not None and self.result["prompt_hash"] != prompt_hash()

    def action_rerun(self) -> None:
        if self.running:
            return
        self.running = True
        self.note = f"Running test set 0/{len(self.rows)}..."
        self.show()
        self.run_worker(self.run_test_set(), exclusive=True)

    async def run_test_set(self) -> None:
        prompt = files.read_text("prompt.md") or ""
        before = cost.total()[0]
        predicted: list[set[str]] = [set() for _ in self.rows]
        errors: set[int] = set()
        done = 0
        try:
            async for i, p in classify_many(
                [r.text for r in self.rows], prompt, self.taxonomy, self.model
            ):
                if p.labels is None:  # a failed call counts as a disagreement
                    errors.add(i)
                else:
                    predicted[i] = set(p.labels)
                done += 1
                self.query_one("#note", Static).update(
                    f"Running test set {done}/{len(self.rows)}..."
                )
        except Exception as e:  # noqa: BLE001  auth/network errors must not kill the app
            self.note = f"Test run failed: {e}"
            self.running = False
            self.show()
            return
        m = metrics.compute_metrics(
            [set(r.labels) for r in self.rows],
            predicted,
            files.all_labels(self.taxonomy),
        )
        self.result = {
            "prompt_hash": prompt_hash(),
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "metrics": dataclasses.asdict(m),
            "disagreements": [
                {
                    "text": self.rows[i].text,
                    "gold": self.rows[i].labels,
                    "predicted": "failed" if i in errors else sorted(predicted[i]),
                }
                for i in m.disagreements
            ],
        }
        files.write_text(RESULT, json.dumps(self.result, indent=2))
        after, unknown = cost.total()
        self.note = (
            f"Test run finished, cost {'?' if unknown else f'${after - before:.4f}'}."
        )
        self.running = False
        self.show()

    def show(self) -> None:
        r = self.result
        banner = self.query_one("#banner", Static)
        banner.display = self.stale()
        banner.update(
            "STALE: prompt.md or classifier model changed since this result was computed. Press r to re-run."
        )
        names = [lab.name for lab in self.taxonomy.labels]
        retitle(
            self.query_one("#metrics-panel"),
            "test set · held out" + (f" · {r['timestamp']}" if r else ""),
        )
        per_label = self.query_one("#per-label", DataTable)
        per_label.display = r is not None
        if r:
            m = metrics.Metrics.from_dict(r["metrics"])
            self.query_one("#summary", Static).update(
                report.summary(m, self.config.target_metric, self.config.target_score)
            )
            report.fill_per_label(per_label, names, m)
        else:
            self.query_one("#summary", Static).update("")
        table = self.query_one("#dis", DataTable)
        report.fit_text_column(table)
        table.clear()
        wrong = r["disagreements"] if r else []
        retitle(self.query_one("#dis-panel"), f"disagreements · {len(wrong)}")
        for i, d in enumerate(wrong):
            table.add_row(
                report.clipped(d["text"]),
                report.tags(names, d["gold"]),
                report.tags(names, d["predicted"]),
                key=str(i),
            )
        note = self.query_one("#note", Static)
        say(note, self.note)
        note.set_classes(
            "note"
            if self.note.startswith(("Running", "Test run finished"))
            else "error"
            if "failed:" in self.note
            else "warn"
        )
        self.show_detail()

    def show_detail(self) -> None:
        table = self.query_one("#dis", DataTable)
        text = ""
        if self.result and table.row_count:
            i = int(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)  # ty: ignore[invalid-argument-type]
            text = self.result["disagreements"][i]["text"]
        self.query_one("#detail", Static).update(text)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.show_detail()

    def action_tune(self) -> None:
        self.app.goto_stage(5)  # ty: ignore[unresolved-attribute]

    def action_accept(self) -> None:
        if self.running or self.result is None:
            return
        if self.stale():
            self.note = "The result is stale: re-run (r) before accepting."
            self.show()
            return
        state = files.read_state()
        state.test_done = True
        files.write_state(state)
        self.app.goto_stage(self.app.stage + 1)  # ty: ignore[unresolved-attribute]
