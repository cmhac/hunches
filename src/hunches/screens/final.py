import dataclasses
import hashlib
import json
import time
from datetime import UTC, datetime
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Static

from hunches import cost, files, metrics
from hunches.app import AppFooter, StatusHeader, key_button, panel, retitle, say
from hunches.classifier import classify_many
from hunches.screens import report
from hunches.screens.gold import GoldScreen
from hunches.screens.progress import RunIndicator, eta_text

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
        ("x", "stop", "Stop"),
        ("s", "start", "Resume"),
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
    FinalScreen #body.-stacked { layout: vertical; }
    FinalScreen #body.-stacked #dis-panel { width: 1fr; height: 5fr; }
    FinalScreen #body.-stacked #text-panel { width: 1fr; height: 4fr; }
    FinalScreen #detail-scroll { height: 1fr; }
    FinalScreen #detail, FinalScreen #reasoning-head, FinalScreen #reasoning { height: auto; }
    FinalScreen #reasoning-head { color: $accent; text-style: bold; margin-top: 1; }
    FinalScreen #actions { height: 3; align: left middle; }
    FinalScreen #actions Button { margin-right: 1; }
    FinalScreen #actions-gap { width: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.taxonomy = files.read_taxonomy()
        self.config = files.read_config()
        self.model = self.config.classifier_model
        self.rows = [r for r in files.read_gold() if r.split == "test" and r.labels]
        text = files.read_text(RESULT)
        self.result: dict | None = json.loads(text) if text else None
        self.running = self.stopped = False
        self.worker = None
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
            with (
                panel(Vertical(id="text-panel"), "text · classifier reasoning"),
                VerticalScroll(id="detail-scroll"),
            ):
                yield Static("", id="detail", markup=False)
                yield Static("classifier reasoning", id="reasoning-head")
                yield Static("", id="reasoning", markup=False)
        with Horizontal(id="actions"):
            yield key_button("Re-run", "r", id="rerun")
            yield key_button("Back to tuning", "t", id="tune")
            yield Static("", id="actions-gap")
            yield key_button("Accept", "F2", id="accept", variant="success")
        yield Static("", id="note", markup=False)
        yield RunIndicator()
        yield AppFooter()

    def on_mount(self) -> None:
        self.query_one(RunIndicator).set_title("Running the held-out test set")
        report.disagreement_columns(self.query_one("#dis", DataTable))
        report.per_label_columns(self.query_one("#per-label", DataTable))
        self.show()
        if self.result is None:  # the one and only automatic run
            self.action_rerun()

    def on_resize(self) -> None:
        self.query_one("#body").set_class(self.size.width >= 120, "-stacked")
        self.call_after_refresh(self.show)  # needs the laid-out table width

    def stale(self) -> bool:
        return self.result is not None and self.result["prompt_hash"] != prompt_hash()

    def action_rerun(self) -> None:
        if self.running:
            return
        self.running, self.stopped = True, False
        self.note = ""
        self.worker = self.run_worker(self.run_test_set(), exclusive=True)

    def action_start(self) -> None:
        if self.stopped:
            self.action_rerun()  # finished items come back from the classifier cache

    def action_stop(self) -> None:
        if self.worker is not None and self.running:
            self.worker.cancel()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "rerun":
            self.action_rerun()
        elif event.button.id == "tune":
            self.action_tune()
        elif event.button.id == "accept":
            self.action_accept()
        elif "Stop" in str(event.button.label):
            self.action_stop()
        else:
            self.action_start()

    async def run_test_set(self) -> None:
        indicator = self.query_one(RunIndicator)
        prompt = files.read_text("prompt.md") or ""
        before = cost.total()[0]
        predicted: list[set[str]] = [set() for _ in self.rows]
        reasons: list[str | None] = [None] * len(self.rows)
        errors: set[int] = set()
        done = live = 0
        total = len(self.rows)
        detail = (
            "prompt changed since the last run"
            if self.result
            else f"classifier {self.config.classifier_model}"
        )
        start = time.monotonic()
        finished = False
        indicator.set_button("stop")
        indicator.set_progress(0, total, detail=detail)
        self.show()
        try:
            async for i, p in classify_many(
                [r.text for r in self.rows], prompt, self.taxonomy, self.model
            ):
                if p.labels is None:  # a failed call counts as a disagreement
                    errors.add(i)
                else:
                    predicted[i] = set(p.labels)
                    reasons[i] = p.reasoning
                done += 1
                live += not p.cached
                indicator.set_progress(
                    done,
                    total,
                    eta_text(done, total, live, time.monotonic() - start),
                    detail,
                )
            finished = True
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
                        "reasoning": reasons[i],
                    }
                    for i in m.disagreements
                ],
            }
            files.write_text(RESULT, json.dumps(self.result, indent=2))
            after, unknown = cost.total()
            self.note = f"Test run finished, cost {'?' if unknown else f'${after - before:.4f}'}."
        except Exception as e:  # noqa: BLE001  auth/network errors must not kill the app
            finished = True  # failed, not stopped: the panels show again
            self.note = f"Test run failed: {e}"
        finally:
            self.running = False
            self.stopped = not finished
            if self.is_attached:  # a stage switch can remove the screen mid-run
                indicator.set_button("resume" if self.stopped else None)
                self.show()

    def show(self) -> None:
        r = self.result
        banner = self.query_one("#banner", Static)
        busy = self.running or self.stopped
        banner.display = self.stale() and not busy
        self.query_one("#metrics-panel").display = not busy
        self.query_one("#body").display = not busy
        self.query_one(RunIndicator).display = busy
        self.query_one("#accept", Button).disabled = busy or r is None or self.stale()
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
            if self.note.startswith("Test run finished")
            else "error"
            if "failed:" in self.note
            else "warn"
        )
        self.show_detail()

    def show_detail(self) -> None:
        table = self.query_one("#dis", DataTable)
        text, reasoning = "", None
        if self.result and table.row_count:
            i = int(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)  # ty: ignore[invalid-argument-type]
            d = self.result["disagreements"][i]
            text = d["text"]
            if d["predicted"] != "failed":  # old results have no reasoning key
                reasoning = d.get("reasoning")
        self.query_one("#detail", Static).update(text)
        self.query_one("#reasoning-head").display = bool(reasoning)
        reason = self.query_one("#reasoning", Static)
        reason.update(reasoning or "")
        reason.display = bool(reasoning)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.show_detail()

    def action_tune(self) -> None:
        self.app.goto_stage(5)  # ty: ignore[unresolved-attribute]

    def action_accept(self) -> None:
        if self.running or self.stopped or self.result is None:
            return
        if self.stale():
            self.note = "The result is stale: re-run (r) before accepting."
            self.show()
            return
        score = metrics.target_value(
            metrics.Metrics.from_dict(self.result["metrics"]),
            self.config.target_metric,
        )
        files.approve(
            "test_done",
            6,
            f"Approved: Gold test (test {self.config.target_metric} {score:.3f})",
        )
        self.app.goto_stage(self.app.stage + 1)  # ty: ignore[unresolved-attribute]
