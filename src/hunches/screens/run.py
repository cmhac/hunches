import json
import time
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from hunches import cost, files
from hunches.app import AppFooter, StatusHeader
from hunches.classifier import classify_many
from hunches.files import above_threshold, pending
from hunches.screens.final import RESULT
from hunches.screens.progress import RunIndicator, eta_text, seconds_text


def estimate(n: int, model: str) -> str:
    """Time and cost for n remaining items, from recorded timings and sample usage."""
    rate = cost.items_per_second("classify")
    time_text = (
        f"~{seconds_text(n / rate)} at {rate:.2f} items/s"
        if rate
        else "no timing samples yet, so no time estimate"
    )
    per_call, sampled = cost.per_call_dollars(model)
    if not sampled:
        cost_text = "no sample usage yet, so no cost estimate"
    elif per_call is None:
        cost_text = "cost ? (WARNING: price unknown for this model)"
    else:
        cost_text = f"~${per_call * n:.4f}"
    return f"{n} items to classify; time {time_text}; cost {cost_text}"


BLOCKED = (
    "Cannot start: prompt.md differs from the tested prompt (or was never tested). "
    "Run the dev set in the Tuning loop with this prompt first."
)
TITLES = {
    "idle": "Ready to classify",
    "running": "Classifying candidates",
    "complete": "Complete",
    "stopped": "Stopped",
    "failed": "Run failed",
}
BUTTON = {"idle": "start", "running": "stop", "stopped": "resume", "failed": "resume"}


class RunScreen(Screen):
    """Stage 8: classify every candidate at or above the threshold; resumable."""

    BINDINGS: ClassVar = [("s", "start", "Start/resume"), ("x", "stop", "Stop")]
    DEFAULT_CSS = """
    RunScreen RunIndicator { height: 1fr; }
    RunScreen #blocked { height: 1fr; align: center middle; }
    RunScreen #blocked > * { width: auto; max-width: 60; margin-bottom: 1; }
    RunScreen #blocked-text { text-align: center; }
    RunScreen #go-tuning { margin-bottom: 0; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.ready = (
            files.read_text("taxonomy.yaml") is not None
            and files.read_text("threshold.json") is not None
        )
        self.model = files.read_config().classifier_model if self.ready else ""
        self.running = False
        self.started = False
        self.failure = ""
        self.worker = None

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        if not self.ready:
            yield Static(
                "Finish stages 3 and 7 first.", id="not-ready", classes="not-ready"
            )
            yield AppFooter()
            return
        yield RunIndicator()
        with Vertical(id="blocked"):
            yield Static(
                BLOCKED, id="blocked-text", classes="banner -stale", markup=False
            )
            yield Button("Go to Tuning loop", id="go-tuning", variant="primary")
        yield AppFooter()

    def on_mount(self) -> None:
        if self.ready:
            self.show()

    def blocked(self) -> bool:
        """True unless test_result.json was computed under the current prompt, taxonomy and classifier model."""
        text = files.read_text(RESULT)
        if text is None:
            return True
        return bool(set(files.result_changes(json.loads(text))) - {"gold_test"})

    def state(self, todo: list[dict]) -> str:
        if self.running:
            return "running"
        if self.failure:
            return "failed"
        if not todo:
            return "complete"
        resumable = self.started or files.read_jsonl("results.jsonl")
        return "stopped" if resumable else "idle"

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action not in ("start", "stop"):
            return True
        if not self.ready or self.blocked():
            return False
        if action == "stop":
            return self.running
        return not self.running and bool(pending())

    def show(self) -> None:
        blocked = self.blocked()
        indicator = self.query_one(RunIndicator)
        indicator.display = not blocked
        self.query_one("#blocked").display = blocked
        todo = pending()
        total = len(above_threshold())
        state = self.state(todo)
        failed = sum("error" in r for r in files.read_jsonl("results.jsonl"))
        indicator.set_title(TITLES[state])
        indicator.set_progress(total - len(todo), total)
        indicator.set_button(None if blocked else BUTTON.get(state))
        if state == "idle":
            indicator.set_status(estimate(len(todo), self.model))
        elif state == "failed":
            indicator.set_status(self.failure, "error")
        elif state == "complete":
            indicator.set_status(
                "Nothing to classify; every candidate at or above the threshold is done."
            )
        elif state == "stopped" and failed:
            indicator.set_status(
                f"{failed} items failed and are retried on the next run", "warn"
            )
        else:
            indicator.set_status("")
        self.refresh_bindings()

    def action_start(self) -> None:
        if not self.ready or self.running or self.blocked() or not pending():
            return
        self.running = self.started = True
        self.failure = ""
        self.show()
        self.worker = self.run_worker(self.run_all(), exclusive=True)

    def action_stop(self) -> None:
        # cancelling only interrupts an await, never the synchronous one-line append below
        if self.worker is not None and self.running:
            self.worker.cancel()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "go-tuning":
            self.app.goto_stage(5)  # ty: ignore[unresolved-attribute]
        elif "Stop" in str(event.button.label):
            self.action_stop()
        else:
            self.action_start()

    async def run_all(self) -> None:
        indicator = self.query_one(RunIndicator)
        # failed rows and rows of another run are dropped; those items are classified now
        todo = pending()
        redo = {c["id"] for c in todo}
        old = files.read_jsonl("results.jsonl")
        keep = [r for r in old if "error" not in r and r["id"] not in redo]
        if len(keep) != len(old):
            files.write_jsonl("results.jsonl", keep)
        taxonomy = files.read_taxonomy()
        prompt = files.read_text("prompt.md") or ""
        total = len(above_threshold())
        base = total - len(todo)
        run = files.run_digest(prompt, taxonomy, self.model)
        start = time.monotonic()
        done = live = 0
        indicator.set_progress(base, total)
        try:
            async for i, p in classify_many(
                [c["text"] for c in todo], prompt, taxonomy, self.model
            ):
                c = todo[i]
                row = {
                    "id": c["id"],
                    "text": c["text"],
                    "labels": p.labels or [],
                    "max_similarity": c["max_similarity"],
                }
                if p.labels is None:
                    row["error"] = p.error or "unknown error"
                else:
                    row["run"] = run
                files.append_jsonl("results.jsonl", row)
                done += 1
                live += not p.cached
                eta = eta_text(done, len(todo), live, time.monotonic() - start)
                indicator.set_progress(base + done, total, eta)
        except Exception as e:  # noqa: BLE001  auth/network errors must not kill the app
            self.failure = f"Run failed: {e}"
        finally:
            self.running = False
            if self.is_attached:  # a stage switch can remove the screen mid-run
                self.show()
