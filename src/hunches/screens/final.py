import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from hunches import cost, files, metrics
from hunches.app import StatusHeader
from hunches.classifier import classify_many
from hunches.screens.gold import GoldScreen

RESULT = "test_result.json"


def test_stage() -> Screen:
    """Stage 6: label the test set first (GoldScreen), then show the held-out evaluation."""
    rows = [r for r in files.read_gold() if r.split == "test"]
    if not rows or any(not r.labels for r in rows):
        return GoldScreen("test")
    return FinalScreen()


def prompt_hash() -> str:
    return hashlib.sha256((files.read_text("prompt.md") or "").encode()).hexdigest()


class FinalScreen(Screen):
    """Stage 6: the test set is classified once; the result goes stale if prompt.md changes."""

    BINDINGS: ClassVar = [
        ("r", "rerun", "Re-run"),
        ("t", "tune", "Back to tuning"),
        ("f2", "accept", "Accept"),
    ]
    AUTO_FOCUS = "#dis"
    DEFAULT_CSS = """
    FinalScreen #banner { height: auto; color: $error; text-style: bold; }
    FinalScreen #metrics, FinalScreen #note { height: auto; }
    FinalScreen #note { color: $warning; }
    FinalScreen Horizontal { height: 1fr; }
    FinalScreen DataTable { width: 2fr; }
    FinalScreen #detail { width: 1fr; padding: 0 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.taxonomy = files.read_taxonomy()
        self.config = files.read_config()
        self.model = self.config.cheap_model
        self.rows = [r for r in files.read_gold() if r.split == "test" and r.labels]
        text = files.read_text(RESULT)
        self.result: dict | None = json.loads(text) if text else None
        self.running = False
        self.note = ""

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        yield Static("", id="banner", markup=False)
        yield Static("", id="metrics", markup=False)
        with Horizontal():
            yield DataTable(id="dis", cursor_type="row")
            yield Static("", id="detail", markup=False)
        yield Static("", id="note", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#dis", DataTable).add_columns("Text", "Gold", "Predicted")
        self.show()
        if self.result is None:  # the one and only automatic run
            self.action_rerun()

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
        self.query_one("#banner", Static).update(
            "STALE: prompt.md changed since this result was computed. Press r to re-run."
            if self.stale()
            else ""
        )
        lines = [
            "Tuning against test disagreements weakens this held-out result (t: back to tuning)."
        ]
        if r:
            m = r["metrics"]
            value = {
                "accuracy": m["exact_match"],
                "exact_match": m["exact_match"],
                "macro_f1": m["macro_f1"],
                "micro_f1": m["micro_f1"],
            }[self.config.target_metric]
            lines.append(
                f"{self.config.target_metric} = {value:.3f}  "
                f"{'PASS' if value >= self.config.target_score else 'FAIL'} "
                f"(target {self.config.target_score:.2f})   n={m['n']}  "
                f"exact-match {m['exact_match']:.3f}  macro-F1 {m['macro_f1']:.3f}  "
                f"micro-F1 {m['micro_f1']:.3f}  [{r['timestamp']}]"
            )
            lines += [
                f"  {name:<20} P {x['precision']:.2f}  R {x['recall']:.2f}  F1 {x['f1']:.2f}  (gold {x['gold_count']})"
                for name, x in m["per_label"].items()
            ]
        self.query_one("#metrics", Static).update("\n".join(lines))
        table = self.query_one("#dis", DataTable)
        table.clear()
        for i, d in enumerate(r["disagreements"] if r else []):
            table.add_row(
                d["text"].replace("\n", " ")[:60],
                ", ".join(d["gold"]),
                d["predicted"]
                if isinstance(d["predicted"], str)
                else ", ".join(d["predicted"]),
                key=str(i),
            )
        self.query_one("#note", Static).update(self.note)
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
