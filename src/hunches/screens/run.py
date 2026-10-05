import json
import time
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.markup import escape
from textual.screen import Screen
from textual.widgets import ProgressBar, Static

from hunches import cost, files
from hunches.app import AppFooter, StatusHeader, panel, retitle
from hunches.classifier import classify_many
from hunches.screens.final import RESULT, prompt_hash


def pending() -> list[dict]:
    """Candidates at or above the threshold with no successful row in results.jsonl yet."""
    cutoff = json.loads(files.read_text("threshold.json") or "{}")["threshold"]
    done = {r["id"] for r in files.read_jsonl("results.jsonl") if "error" not in r}
    return [
        c
        for c in files.read_jsonl("candidates.jsonl")
        if c["max_similarity"] >= cutoff and c["id"] not in done
    ]


def seconds_text(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{secs:02d}s"


def estimate(n: int, model: str) -> str:
    """Time and cost for n remaining items, from recorded timings and sample usage."""
    rate = cost.items_per_second("classify")
    time_text = (
        f"~{seconds_text(n / rate)} at {rate:.2f} items/s"
        if rate
        else "no timing samples yet, so no time estimate"
    )
    entry = cost.breakdown().get(model)
    if not entry or not entry["calls"]:
        cost_text = "no sample usage yet, so no cost estimate"
    elif entry["dollars"] is None:
        cost_text = "cost ? (WARNING: price unknown for this model)"
    else:
        cost_text = f"~${entry['dollars'] / entry['calls'] * n:.4f}"
    return f"{n} items to classify; time {time_text}; cost {cost_text}"


class RunScreen(Screen):
    """Stage 8: classify every candidate at or above the threshold; resumable."""

    BINDINGS: ClassVar = [("s", "start", "Start/resume"), ("x", "stop", "Stop")]
    DEFAULT_CSS = """
    RunScreen Static { height: auto; }
    RunScreen #estimate-panel { height: auto; }
    RunScreen #run-panel { height: 1fr; }
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
        self.warned = False
        self.errors: list[str] = []

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        if not self.ready:
            yield Static(
                "Finish stages 3 and 7 first.", id="not-ready", classes="not-ready"
            )
            yield AppFooter()
            return
        with panel(Vertical(id="estimate-panel"), "estimate"):
            yield Static("", id="estimate", markup=False)
        yield Static("", id="warn", classes="banner -warning", markup=False)
        with panel(Vertical(id="run-panel", classes="-focused"), "run · results.jsonl"):
            yield ProgressBar(total=1, id="progress")
            yield Static("", id="live", markup=False)
            yield Static("", id="errors")
        yield AppFooter()

    def on_mount(self) -> None:
        if self.ready:
            self.query_one("#warn").display = False
            self.show_estimate()

    def show_estimate(self) -> None:
        todo = pending()
        text = (
            estimate(len(todo), self.model)
            if todo
            else "Nothing to classify; every candidate at or above the threshold is done."
        )
        self.query_one("#estimate", Static).update(text)
        self.query_one("#errors", Static).update(
            "\n[b $warning]Failed (retried next run):[/]\n"
            + "\n".join(f"[$text-muted]{escape(e)}[/]" for e in self.errors[-10:])
            if self.errors
            else ""
        )
        retitle(
            self.query_one("#run-panel"),
            subtitle="running"
            if self.running
            else "complete"
            if not todo
            else "stopped · resumable"
            if self.started or files.read_jsonl("results.jsonl")
            else "not started",
        )

    def action_start(self) -> None:
        if not self.ready or self.running:
            return
        tested = json.loads(files.read_text(RESULT) or "{}").get("prompt_hash")
        if tested != prompt_hash() and not self.warned:
            self.warned = True
            self.query_one("#warn").display = True
            self.query_one("#warn", Static).update(
                "WARNING: prompt.md or classifier model differs from the tested one (or was never tested). "
                "Press s again to start anyway."
            )
            return
        self.running = self.started = True
        self.query_one("#warn").display = False
        retitle(self.query_one("#run-panel"), subtitle="running")
        self.run_worker(self.run_all(), exclusive=True)

    def action_stop(self) -> None:
        # cancelling only interrupts an await, never the synchronous one-line append below
        self.workers.cancel_all()

    async def run_all(self) -> None:
        live = self.query_one("#live", Static)
        live.set_classes("")
        # failed rows from an earlier run are dropped; the items are retried now
        old = files.read_jsonl("results.jsonl")
        if any("error" in r for r in old):
            files.write_jsonl("results.jsonl", [r for r in old if "error" not in r])
        todo = pending()
        taxonomy = files.read_taxonomy()
        prompt = files.read_text("prompt.md") or ""
        bar = self.query_one("#progress", ProgressBar)
        bar.update(total=max(len(todo), 1), progress=0)
        before = cost.total()[0]
        start = time.monotonic()
        done = 0
        self.errors = []
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
                    self.errors.append(f"{c['id']}: {row['error']}")
                files.append_jsonl("results.jsonl", row)
                done += 1
                bar.update(progress=done)
                elapsed = time.monotonic() - start
                dollars, unknown = cost.total()
                spent = "?" if unknown else f"${dollars - before:.4f}"
                eta = seconds_text(elapsed / done * (len(todo) - done))
                live.update(
                    f"{done}/{len(todo)} | cost {spent} | "
                    f"{done / elapsed:.2f} items/s | ETA {eta}"
                )
        except Exception as e:  # noqa: BLE001  auth/network errors must not kill the app
            live.update(f"Run failed: {e}")
            live.set_classes("error")
        finally:
            self.running = False
            self.show_estimate()
