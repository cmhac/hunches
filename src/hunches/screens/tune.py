import difflib
from typing import ClassVar

from pydantic_ai import Agent
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Static, TextArea

from hunches import cost, files, metrics
from hunches.app import StatusHeader, confirm_approve, panel
from hunches.classifier import classify_many
from hunches.screens import report
from hunches.theme import editor

MAX_SHOWN = 20  # disagreements the smart model sees
METRICS = ["accuracy", "macro_f1", "micro_f1", "exact_match"]

INSTRUCTIONS = """\
You improve a text classifier's prompt. You are given the current prompt, the taxonomy and \
some items the classifier got wrong (gold label vs predicted label). Reply with the complete \
new prompt text and nothing else: no commentary, no code fences. Keep what works, fix what \
causes the errors, and do not tailor the prompt to individual items.
"""


def diff(old: str, new: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(), "current", "proposed", lineterm=""
        )
    )


def diff_markup(old: str, new: str) -> str:
    """The unified diff with + lines green, - lines red, @@ sand and the file headers muted."""
    out = []
    for line in diff(old, new).splitlines():
        text = escape(line)
        if line.startswith(("---", "+++")):
            out.append(f"[$text-muted]{text}[/]")
        elif line.startswith("+"):
            out.append(f"[$success on #1C3322]{text}[/]")
        elif line.startswith("-"):
            out.append(f"[$error on #3E1826]{text}[/]")
        elif line.startswith("@@"):
            out.append(f"[$secondary]{text}[/]")
        else:
            out.append(text)
    return "\n".join(out)


class ProposalScreen(ModalScreen[str | None]):
    """Shows a diff against the current prompt; the proposal is editable. Dismisses with the text or None."""

    AUTO_FOCUS = "#accept"
    DEFAULT_CSS = """
    ProposalScreen { align: center middle; }
    ProposalScreen > Vertical {
        width: 1fr; height: 1fr; margin: 1 2; border: round $primary; background: $surface; padding: 0 1;
    }
    ProposalScreen .panel { height: 1fr; }
    ProposalScreen #diff-panel { overflow-y: auto; }
    ProposalScreen TextArea { height: 1fr; border: none; padding: 0; }
    ProposalScreen #buttons { height: auto; align-horizontal: right; }
    """

    def __init__(self, current: str, proposed: str) -> None:
        super().__init__()
        self.current = current
        self.proposed = proposed

    def compose(self) -> ComposeResult:
        with Vertical() as box:
            box.border_title = "Proposed prompt change"
            yield Static(
                "Review the diff, edit the proposal if needed, then accept or reject.",
                classes="note",
            )
            with panel(Vertical(id="diff-panel"), "diff · current → proposed"):
                yield Static(diff_markup(self.current, self.proposed), id="diff")
            with panel(Vertical(id="proposal-panel"), "proposal (editable)"):
                yield editor(
                    TextArea(self.proposed, language="markdown", id="proposal")
                )
            with Horizontal(id="buttons"):
                yield Button("Reject", id="reject")
                yield Button("Accept", id="accept", variant="success")

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.query_one("#diff", Static).update(
            diff_markup(self.current, event.text_area.text)
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(
            self.query_one("#proposal", TextArea).text
            if event.button.id == "accept"
            else None
        )


class TuneScreen(Screen):
    """Stage 5: dev-set metrics, disagreements, and smart-model prompt edits."""

    BINDINGS: ClassVar = [
        ("e", "propose", "Propose prompt edit"),
        ("m", "next_metric", "Target metric"),
        ("plus,equals_sign", "score(0.01)", "Target +"),
        ("minus", "score(-0.01)", "Target -"),
        ("f2", "done", "Done"),
    ]
    AUTO_FOCUS = "#dis"
    DEFAULT_CSS = """
    TuneScreen #metrics-panel { height: auto; }
    TuneScreen #metrics-panel DataTable { height: auto; }
    TuneScreen #summary, TuneScreen #trend, TuneScreen #note { height: auto; }
    TuneScreen #body { height: 1fr; }
    TuneScreen #dis-panel { width: 3fr; }
    TuneScreen #text-panel { width: 2fr; }
    TuneScreen #dis { height: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.ready = (
            files.read_text("taxonomy.yaml") is not None
            and files.read_text("prompt.md") is not None
        )
        self.taxonomy = (
            files.read_taxonomy()
            if self.ready
            else files.Taxonomy(mode="single", labels=[])
        )
        self.prompt = files.read_text("prompt.md") or ""
        self.config = files.read_config()
        self.model = self.config.cheap_model
        self.rows = [r for r in files.read_gold() if r.split == "dev" and r.labels]
        self.predicted: list[set[str]] = []
        self.errors: dict[int, str] = {}
        self.metrics: metrics.Metrics | None = None
        self.running = False
        self.run_note = ""
        self.history: list[float] = []  # target value after each prompt version
        self.note = ""
        self.agent = Agent(
            self.config.smart_model,
            instructions=INSTRUCTIONS,
            output_type=str,
            defer_model_check=True,
        )

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
        with panel(Vertical(id="metrics-panel"), "dev set"):
            yield Static("", id="summary")
            yield DataTable(id="per-label")
            yield Static("", id="trend", classes="note")
        with Horizontal(id="body"):
            with panel(Vertical(id="dis-panel"), "disagreements"):
                yield DataTable(id="dis", cursor_type="row")
            with panel(Vertical(id="text-panel"), "text"):
                yield Static("", id="detail")
        yield Static("", id="note", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        if not self.ready:
            return
        report.disagreement_columns(self.query_one("#dis", DataTable))
        report.per_label_columns(self.query_one("#per-label", DataTable))
        self.rerun()

    def on_resize(self) -> None:
        if self.ready:
            self.call_after_refresh(self.show)  # needs the laid-out table width

    def rerun(self) -> None:
        """Classify the dev set with the current prompt; cached items are free."""
        self.running = True
        self.run_note = f"Running dev set 0/{len(self.rows)}..."
        self.show()
        self.run_worker(self.run_dev(), exclusive=True)

    async def run_dev(self) -> None:
        before = cost.total()[0]
        predicted: list[set[str]] = [set() for _ in self.rows]
        self.errors = {}
        done = 0
        try:
            async for i, p in classify_many(
                [r.text for r in self.rows], self.prompt, self.taxonomy, self.model
            ):
                if p.labels is None:  # a failed call counts as a disagreement
                    self.errors[i] = p.error or "failed"
                else:
                    predicted[i] = set(p.labels)
                done += 1
                self.run_note = f"Running dev set {done}/{len(self.rows)}..."
                self.query_one("#note", Static).update(self.run_note)
        except Exception as e:  # noqa: BLE001  auth/network errors must not kill the app
            self.note = f"Dev run failed: {e}"
            self.running = False
            self.show()
            return
        self.predicted = predicted
        self.metrics = metrics.compute_metrics(
            [set(r.labels) for r in self.rows],
            predicted,
            files.all_labels(self.taxonomy),
        )
        self.history.append(self.target())
        after, unknown = cost.total()
        spent = "?" if unknown else f"${after - before:.4f}"
        self.run_note = f"Dev run finished, cost {spent}."
        self.running = False
        self.show()

    def target(self) -> float:
        assert self.metrics
        return metrics.target_value(self.metrics, self.config.target_metric)

    def met(self) -> bool:
        return self.metrics is not None and self.target() >= self.config.target_score

    def show(self) -> None:
        m = self.metrics
        names = [lab.name for lab in self.taxonomy.labels]
        target = self.config.target_metric
        self.query_one(
            "#metrics-panel"
        ).border_subtitle = (
            f"target {target} ≥ {self.config.target_score:.2f} · m metric · +/- score"
        )
        self.query_one("#summary", Static).update(
            report.summary(m, target, self.config.target_score) if m else ""
        )
        per_label = self.query_one("#per-label", DataTable)
        per_label.display = m is not None
        if m:
            report.fill_per_label(per_label, names, m)
        self.query_one("#trend", Static).update(
            "trend " + " → ".join(f"{v:.3f}" for v in self.history)
            if len(self.history) > 1
            else ""
        )
        table = self.query_one("#dis", DataTable)
        report.fit_text_column(table)
        table.clear()
        wrong = m.disagreements if m else []
        self.query_one("#dis-panel").border_title = f"disagreements · {len(wrong)}"
        for i in wrong:
            predicted = "failed" if i in self.errors else self.predicted[i]
            table.add_row(
                report.clipped(self.rows[i].text),
                report.tags(names, self.rows[i].labels),
                report.tags(names, predicted),
                key=str(i),
            )
        note = self.query_one("#note", Static)
        text = self.run_note or self.note
        note.update(text)
        note.set_classes(
            "note"
            if text.startswith(("Running", "Dev run finished"))
            else "error"
            if "failed:" in text
            else "warn"
        )
        self.show_detail()

    def show_detail(self) -> None:
        table = self.query_one("#dis", DataTable)
        text = ""
        if self.metrics and table.row_count:
            i = int(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)  # ty: ignore[invalid-argument-type]
            text = escape(self.rows[i].text)
            if i in self.errors:
                text += f"\n\n[$error]Model failed: {escape(self.errors[i])}[/]"
        self.query_one("#detail", Static).update(text)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.show_detail()

    def action_next_metric(self) -> None:
        if not self.ready:
            return
        self.config.target_metric = METRICS[  # ty: ignore[invalid-assignment]
            (METRICS.index(self.config.target_metric) + 1) % len(METRICS)
        ]
        files.write_config(self.config)
        self.show()

    def action_score(self, step: float) -> None:
        if not self.ready:
            return
        self.config.target_score = min(
            1.0, max(0.0, round(self.config.target_score + step, 2))
        )
        files.write_config(self.config)
        self.show()

    def action_propose(self) -> None:
        if not self.ready or self.running or not self.metrics:
            return
        if not self.metrics.disagreements:
            self.note = "No disagreements to learn from."
            self.show()
            return
        self.note = "Asking the smart model..."
        self.show()
        self.run_worker(self.propose(), exclusive=True)

    async def propose(self) -> None:
        assert self.metrics
        shown = self.metrics.disagreements[:MAX_SHOWN]
        text = f"Current prompt:\n{self.prompt}\n\nTaxonomy:\n{self.taxonomy.model_dump_json(indent=2)}\n\n"
        text += f"Disagreements ({len(shown)} of {len(self.metrics.disagreements)}"
        text += (
            ", truncated):\n"
            if len(shown) < len(self.metrics.disagreements)
            else "):\n"
        )
        for i in shown:
            got = "failed" if i in self.errors else sorted(self.predicted[i])
            text += f"- text: {self.rows[i].text}\n  gold: {self.rows[i].labels}\n  predicted: {got}\n"
        try:
            result = await self.agent.run(text)
        except Exception as e:  # noqa: BLE001
            self.note = f"Proposal failed: {e}"
            self.show()
            return
        model = self.agent.model
        name = model if isinstance(model, str) else getattr(model, "model_name", "?")
        cost.record(name, result.usage, cost.messages_dollars(result.new_messages()))
        self.note = ""
        self.show()
        self.app.push_screen(ProposalScreen(self.prompt, result.output), self.accepted)

    def accepted(self, new: str | None) -> None:
        if new is None or not new.strip() or new == self.prompt:
            return
        files.write_text("prompt.md", new)
        self.prompt = new
        self.rerun()

    def action_done(self) -> None:
        if not self.ready or self.running or not self.metrics:
            return
        goto = lambda: self.app.goto_stage(self.app.stage + 1)  # ty: ignore[unresolved-attribute]
        if self.met():
            state = files.read_state()
            state.dev_done = True
            files.write_state(state)
            goto()
            return
        confirm_approve(
            self,
            "dev_done",
            f"{self.config.target_metric} {self.target():.3f} is below the target "
            f"{self.config.target_score:.2f}. Accept tuning anyway?",
            then=goto,
        )
