import json
import random
import time
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Static

from hunches import candidates, cost, files
from hunches.app import (
    AppFooter,
    StageBanner,
    StatusHeader,
    current_status,
    key_button,
    panel,
    plan_hint,
    say,
)
from hunches.classifier import classify_many
from hunches.screens.progress import RunIndicator, eta_text

SAMPLE = "threshold_sample.json"
PER_BAND = 30


def sample_bands(
    cands: list[dict], per_band: int = PER_BAND, fresh: bool = False
) -> list[list[str]]:
    """Candidate ids sampled from each band (all of them if the band is smaller).

    Reproducible (RNG seeded by project name and band) and persisted in SAMPLE, so reopening
    the screen reuses the same items (`fresh`: the candidates changed, so draw again).
    Task 12's gold.draw excludes gold ids, so it can't be used.
    """
    saved = None if fresh else files.read_text(SAMPLE)
    if saved:
        return json.loads(saved)["ids"]
    ids = []
    for band in range(len(candidates.BANDS)):
        pool = sorted(
            c["id"] for c in cands if candidates.band_of(c["max_similarity"]) == band
        )
        rng = random.Random(f"{Path.cwd().name}:threshold:{band}")
        ids.append(rng.sample(pool, min(per_band, len(pool))))
    files.write_text(
        SAMPLE,
        json.dumps(
            {
                "ids": ids,
                "predictions": {},
                "inputs": files.current_inputs("threshold_chosen"),
            }
        ),
    )
    return ids


def band_rows(
    cands: list[dict], ids: list[list[str]], predictions: dict[str, list[str] | None]
) -> list[dict]:
    """Per band: candidates, sampled (classified successfully), off_topic count, cumulative at or above."""
    counts = candidates.band_counts(cands)
    rows = []
    for i, edge in enumerate(candidates.BANDS):
        done = [predictions[x] for x in ids[i] if predictions.get(x) is not None]
        rows.append(
            {
                "lower": edge,
                "candidates": counts[i],
                "sampled": len(done),
                "off_topic": sum(p == [files.OFF_TOPIC] for p in done),
                "cumulative": sum(counts[i:]),
            }
        )
    return rows


def rate_text(row: dict) -> str:
    if not row["sampled"]:
        return "-"
    return f"{row['off_topic'] / row['sampled']:.0%} (n={row['sampled']})"


class ThresholdScreen(Screen):
    """Stage 7: off-topic rate per similarity band; the user chooses a band's lower bound as the cutoff."""

    BINDINGS: ClassVar = [
        ("enter", "noop", "Choose band"),
        ("f2", "save", "Save cutoff"),
        ("x", "stop", "Stop"),
        ("s", "start", "Resume"),
    ]
    AUTO_FOCUS = "#bands"
    DEFAULT_CSS = """
    ThresholdScreen #explain, ThresholdScreen #note { height: auto; }
    ThresholdScreen #bands-panel { height: auto; }
    ThresholdScreen #bands { height: auto; }
    ThresholdScreen #pick { height: 3; align: center middle; }
    ThresholdScreen #cutoff-line { width: auto; margin-right: 2; }
    ThresholdScreen #cutoff-line.-chosen { text-style: bold; }
    ThresholdScreen #cutoff-line.-none { color: $text-muted; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.ready = files.read_text("taxonomy.yaml") is not None
        self.cands = files.read_jsonl("candidates.jsonl")
        self.note = ""
        self.progress: tuple[int, int] | None = None  # (sampled, total) while running
        self.ids: list[list[str]] = []
        self.predictions: dict[str, list[str] | None] = {}
        self.running = self.stopped = False
        self.worker = None
        self.chosen: int | None = None  # index into candidates.BANDS
        self.saved: float | None = None  # threshold.json value that is not a band edge

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        if not self.ready:
            yield Static(
                "Finish stage 3 (taxonomy and prompt) first.",
                id="not-ready",
                classes="not-ready",
            )
            yield AppFooter()
            return
        yield StageBanner(self.banner_text)
        yield Static(
            "Off-topic = predicted exactly {off_topic}. Small samples are noisy; mind n. "
            "Enter on a row chooses its lower bound as the cutoff.",
            id="explain",
            classes="note",
            markup=False,
        )
        with panel(
            Vertical(id="bands-panel"),
            f"off-topic rate by band · {files.read_config().classifier_model}",
        ):
            yield DataTable(id="bands", cursor_type="row")
        with Horizontal(id="pick"):
            yield Static("", id="cutoff-line", markup=False)
            yield key_button("Save cutoff", "F2", id="save", variant="primary")
        yield Static("", id="note", markup=False)
        yield RunIndicator()
        yield AppFooter()

    def banner_text(self) -> str:
        kind, reason = current_status()[7]
        if self.running or self.stopped or kind != "stale":
            return ""
        return (
            f"STALE: {reason}. The rates below are for the current settings. "
            "Choose a band and save the cutoff again." + plan_hint()
        )

    def on_mount(self) -> None:
        if not self.ready:
            return
        table = self.query_one("#bands", DataTable)
        table.add_column("Band", width=8)
        for name in ("Candidates", "Sampled", "Off-topic rate"):
            table.add_column(Text(name, justify="right"))
        table.add_column(Text("Cumulative ≥ lower", justify="right"), width=20)
        indicator = self.query_one(RunIndicator)
        indicator.set_title("Sampling each similarity band")
        # a sample made under other inputs is classified again (the cache makes that cheap); one made
        # from other candidates is drawn again. Its file stays until the first new prediction.
        old = files.changed(
            json.loads(files.read_text(SAMPLE) or "{}").get("inputs", {})
        )
        self.ids = sample_bands(self.cands, fresh="candidates" in old)
        saved = json.loads(files.read_text(SAMPLE) or "{}")
        self.predictions = {} if old else saved.get("predictions", {})
        previous = json.loads(files.read_text("threshold.json") or "{}")
        if "threshold" in previous:
            if previous["threshold"] in candidates.BANDS:
                self.chosen = candidates.BANDS.index(previous["threshold"])
            else:
                self.saved = previous["threshold"]
        self.show()
        self.action_start()

    def show(self) -> None:
        self.query_one(StageBanner).refresh_text()
        table = self.query_one("#bands", DataTable)
        row = table.cursor_row
        table.clear()
        for i, r in enumerate(band_rows(self.cands, self.ids, self.predictions)):
            label = (
                f"{r['lower']:.3f}+"
                if r["lower"] == candidates.BANDS[-1]
                else f"{r['lower']:.3f}"
            )
            right = lambda v: Text(v, justify="right")
            table.add_row(
                ("● " if i == self.chosen else "  ") + label,
                right(f"{r['candidates']:,}"),
                right(f"{r['sampled']:,}"),
                right(rate_text(r)),
                right(f"{r['cumulative']:,}"),
            )
        table.move_cursor(row=row)
        busy = self.running or self.stopped
        self.query_one("#bands-panel").display = not busy
        self.query_one("#pick").display = not busy
        self.query_one(RunIndicator).display = busy
        if self.chosen is not None:
            line = f"Cutoff {candidates.BANDS[self.chosen]:.3f}"
            mode = "-chosen"
        elif self.saved is not None:
            line, mode = f"Saved cutoff {self.saved}", "-none"
        else:
            line, mode = "No cutoff chosen", "-none"
        cutoff = self.query_one("#cutoff-line", Static)
        cutoff.update(line)
        cutoff.set_classes(mode)
        self.query_one("#save", Button).disabled = self.chosen is None
        note = self.query_one("#note", Static)
        say(note, self.note)
        note.set_classes("error" if "failed:" in self.note else "note")

    def action_start(self) -> None:
        todo = [x for band in self.ids for x in band if x not in self.predictions]
        if not self.ready or self.running or not todo:
            return
        self.running, self.stopped = True, False
        self.note = ""
        self.worker = self.run_worker(self.run_sample(todo), exclusive=True)

    def action_stop(self) -> None:
        if self.worker is not None and self.running:
            self.worker.cancel()

    def action_noop(self) -> None:
        """Enter is handled by the table; the binding only labels it in the footer."""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.action_save()
        elif "Stop" in str(event.button.label):
            self.action_stop()
        else:
            self.action_start()

    async def run_sample(self, todo: list[str]) -> None:
        """Classify the sampled items that have no stored prediction; persist as they finish."""
        indicator = self.query_one(RunIndicator)
        taxonomy = files.read_taxonomy()
        prompt = files.read_text("prompt.md") or ""
        by_id = {c["id"]: c["text"] for c in self.cands}
        before = cost.total()[0]
        start = time.monotonic()
        total = sum(len(band) for band in self.ids)
        self.progress = (total - len(todo), total)
        live = 0
        finished = False
        indicator.set_button("stop")
        indicator.set_progress(
            self.progress[0], total, detail=f"{PER_BAND} items per band"
        )
        self.show()
        try:
            async for i, p in classify_many(
                [by_id[x] for x in todo],
                prompt,
                taxonomy,
                files.read_config().classifier_model,
            ):
                live += not p.cached
                if (
                    p.labels is not None
                ):  # failures stay unclassified and are retried next time
                    self.predictions[todo[i]] = p.labels
                    files.write_text(
                        SAMPLE,
                        json.dumps(
                            {
                                "ids": self.ids,
                                "predictions": self.predictions,
                                "inputs": files.current_inputs("threshold_chosen"),
                            }
                        ),
                    )
                    self.progress = (len(self.predictions), total)
                    indicator.set_progress(
                        len(self.predictions),
                        total,
                        eta_text(
                            len(self.predictions),
                            total,
                            live,
                            time.monotonic() - start,
                        ),
                        f"{PER_BAND} items per band",
                    )
            finished = True
            after, unknown = cost.total()
            spent = "?" if unknown else f"${after - before:.4f}"
            self.note = f"Sampled {len(todo)} items in {time.monotonic() - start:.1f}s, cost {spent}."
        except Exception as e:  # noqa: BLE001  auth/network errors must not kill the app
            finished = (
                True  # failed, not stopped: the panel shows with finished rows kept
            )
            self.note = f"Sampling failed: {e}"
        finally:
            self.running = False
            self.stopped = not finished
            self.progress = None
            if self.is_attached:  # a stage switch can remove the screen mid-run
                indicator.set_button("resume" if self.stopped else None)
                self.show()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.chosen = event.cursor_row
        self.show()

    def action_save(self) -> None:
        if not self.ready or self.chosen is None:
            return
        cutoff = candidates.BANDS[self.chosen]
        # the key is `threshold`, as files.first_incomplete_stage expects (the spec calls it cutoff)
        files.write_text(
            "threshold.json",
            json.dumps(
                {
                    "threshold": cutoff,
                    "bands": band_rows(self.cands, self.ids, self.predictions),
                    "n_candidates": sum(
                        c["max_similarity"] >= cutoff for c in self.cands
                    ),
                    "inputs": files.current_inputs("threshold_chosen"),
                },
                indent=2,
            ),
        )
        n = sum(c["max_similarity"] >= cutoff for c in self.cands)
        files.approve(
            "threshold_chosen", 7, f"Approved: Cutoff {cutoff:.3f} ({n} candidates)"
        )
        self.app.goto_stage(self.app.stage + 1)  # ty: ignore[unresolved-attribute]
