import json
import random
import time
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Static

from hunches import candidates, cost, files
from hunches.app import StatusHeader, panel
from hunches.classifier import classify_many

SAMPLE = "threshold_sample.json"
PER_BAND = 30


def sample_bands(cands: list[dict], per_band: int = PER_BAND) -> list[list[str]]:
    """Candidate ids sampled from each band (all of them if the band is smaller).

    Reproducible (RNG seeded by project name and band) and persisted in SAMPLE, so reopening
    the screen reuses the same items. Task 12's gold.draw excludes gold ids, so it can't be used.
    """
    saved = files.read_text(SAMPLE)
    if saved:
        return json.loads(saved)["ids"]
    ids = []
    for band in range(len(candidates.BANDS)):
        pool = sorted(
            c["id"] for c in cands if candidates.band_of(c["max_similarity"]) == band
        )
        rng = random.Random(f"{Path.cwd().name}:threshold:{band}")
        ids.append(rng.sample(pool, min(per_band, len(pool))))
    files.write_text(SAMPLE, json.dumps({"ids": ids, "predictions": {}}))
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
    """Stage 7: off-topic rate per similarity band; the user picks the cutoff."""

    BINDINGS: ClassVar = [("f2", "save", "Save cutoff")]
    AUTO_FOCUS = "#bands"
    DEFAULT_CSS = """
    ThresholdScreen #explain, ThresholdScreen #note { height: auto; }
    ThresholdScreen #bands-panel { height: auto; }
    ThresholdScreen #bands { height: auto; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.ready = files.read_text("taxonomy.yaml") is not None
        self.cands = files.read_jsonl("candidates.jsonl")
        self.note = ""
        self.progress: tuple[int, int] | None = None  # (sampled, total) while running
        self.ids: list[list[str]] = []
        self.predictions: dict[str, list[str] | None] = {}

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        if not self.ready:
            yield Static(
                "Finish stage 3 (taxonomy and prompt) first.",
                id="not-ready",
                classes="warn",
            )
            yield Footer()
            return
        yield Static(
            "Off-topic = predicted exactly {off_topic}. Small samples are noisy; mind n. "
            "Enter on a row picks its lower bound.",
            id="explain",
            classes="note",
            markup=False,
        )
        with panel(
            Vertical(id="bands-panel"),
            f"off-topic rate by band · {files.read_config().classifier_model}",
        ):
            yield DataTable(id="bands", cursor_type="row")
        yield Input(placeholder="cutoff, e.g. 0.65 (F2 saves)", id="cutoff")
        yield Static("", id="note", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        if not self.ready:
            return
        table = self.query_one("#bands", DataTable)
        table.add_column("Band", width=8)
        for name in ("Candidates", "Sampled", "Off-topic rate"):
            table.add_column(Text(name, justify="right"))
        table.add_column(Text("Cumulative ≥ lower", justify="right"), width=20)
        self.ids = sample_bands(self.cands)
        saved = json.loads(files.read_text(SAMPLE) or "{}")
        self.predictions = saved.get("predictions", {})
        self.show()
        if any(x not in self.predictions for band in self.ids for x in band):
            self.run_worker(self.run_sample(), exclusive=True)

    def show(self) -> None:
        table = self.query_one("#bands", DataTable)
        table.clear()
        for r in band_rows(self.cands, self.ids, self.predictions):
            label = (
                f"{r['lower']:.3f}+"
                if r["lower"] == candidates.BANDS[-1]
                else f"{r['lower']:.3f}"
            )
            right = lambda v: Text(v, justify="right")
            table.add_row(
                label,
                right(f"{r['candidates']:,}"),
                right(f"{r['sampled']:,}"),
                right(rate_text(r)),
                right(f"{r['cumulative']:,}"),
            )
        self.query_one("#bands-panel").border_subtitle = (
            f"sampling {self.progress[0]}/{self.progress[1]}" if self.progress else ""
        )
        note = self.query_one("#note", Static)
        note.update(self.note)
        note.set_classes(
            "note"
            if self.note.startswith("Sampled")
            else "error"
            if "failed:" in self.note
            else "warn"
        )

    async def run_sample(self) -> None:
        """Classify the sampled items that have no stored prediction; persist as they finish."""
        taxonomy = files.read_taxonomy()
        prompt = files.read_text("prompt.md") or ""
        by_id = {c["id"]: c["text"] for c in self.cands}
        todo = [x for band in self.ids for x in band if x not in self.predictions]
        before = cost.total()[0]
        start = time.monotonic()
        total = sum(len(band) for band in self.ids)
        self.progress = (total - len(todo), total)
        try:
            async for i, p in classify_many(
                [by_id[x] for x in todo],
                prompt,
                taxonomy,
                files.read_config().classifier_model,
            ):
                if (
                    p.labels is not None
                ):  # failures stay unclassified and are retried next time
                    self.predictions[todo[i]] = p.labels
                    files.write_text(
                        SAMPLE,
                        json.dumps({"ids": self.ids, "predictions": self.predictions}),
                    )
                    self.progress = (len(self.predictions), total)
                self.show()
        except Exception as e:  # noqa: BLE001  auth/network errors must not kill the app
            self.note = f"Sampling failed: {e}"
            self.progress = None
            self.show()
            return
        after, unknown = cost.total()
        spent = "?" if unknown else f"${after - before:.4f}"
        self.note = f"Sampled {len(todo)} items in {time.monotonic() - start:.1f}s, cost {spent}."
        self.progress = None
        self.show()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.query_one("#cutoff", Input).value = str(candidates.BANDS[event.cursor_row])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_save()

    def action_save(self) -> None:
        if not self.ready:
            return
        try:
            cutoff = float(self.query_one("#cutoff", Input).value)
        except ValueError:
            self.note = "Enter a number or pick a band with Enter."
            self.show()
            return
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
                },
                indent=2,
            ),
        )
        state = files.read_state()
        state.threshold_chosen = True
        files.write_state(state)
        self.app.goto_stage(self.app.stage + 1)  # ty: ignore[unresolved-attribute]
