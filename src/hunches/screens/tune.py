import difflib
import time
from typing import ClassVar

from pydantic_ai import Agent
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.markup import escape
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Select, Static, TextArea

from hunches import cost, files, metrics
from hunches.app import (
    AppFooter,
    StatusHeader,
    confirm_approve,
    key_button,
    modal_box,
    panel,
    retitle,
    say,
)
from hunches.classifier import classify_many
from hunches.screens import report
from hunches.screens.progress import RunIndicator, eta_text
from hunches.theme import editor

MAX_SHOWN = 20  # disagreements the assistant sees
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
        width: 1fr; height: 1fr; margin: 1 2;
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
        with modal_box(Vertical(), "Proposed prompt change"):
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


class PromptEditScreen(ModalScreen[str | None]):
    """Edit prompt.md by hand. Dismisses with the new text (Save and re-run) or None."""

    AUTO_FOCUS = "#prompt"
    BINDINGS: ClassVar = [("escape", "cancel", "Cancel"), ("f2", "save", "Save")]
    DEFAULT_CSS = """
    PromptEditScreen { align: center middle; }
    PromptEditScreen > Vertical { width: 1fr; height: 1fr; margin: 1 2; }
    PromptEditScreen .panel { height: 1fr; }
    PromptEditScreen TextArea { height: 1fr; border: none; padding: 0; }
    PromptEditScreen #note-line { height: auto; }
    PromptEditScreen #buttons { height: auto; align-horizontal: right; }
    """

    def __init__(self, current: str) -> None:
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        with modal_box(Vertical(), "Edit prompt"):
            yield Static(
                "Edit the text. Nothing is saved until you choose Save and re-run.",
                classes="note",
            )
            with panel(Vertical(id="prompt-panel"), "prompt.md (editable)"):
                yield editor(
                    TextArea(
                        self.current,
                        language="markdown",
                        show_line_numbers=True,
                        id="prompt",
                    )
                )
            yield Static(
                "The dev set is classified again with the new prompt.",
                id="note-line",
                classes="note",
            )
            with Horizontal(id="buttons"):
                yield key_button("Cancel", "Esc", id="cancel")
                yield key_button(
                    "Save and re-run", "F2", id="save", variant="success", disabled=True
                )

    def changed(self) -> bool:
        text = self.query_one("#prompt", TextArea).text
        return bool(text.strip()) and text != self.current

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.query_one("#save", Button).disabled = not self.changed()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        if self.changed():
            self.dismiss(self.query_one("#prompt", TextArea).text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.action_save()
        else:
            self.action_cancel()


class TuneScreen(Screen):
    """Stage 5: dev-set metrics, disagreements, and assistant prompt edits."""

    BINDINGS: ClassVar = [
        ("e", "propose", "Propose"),
        ("o", "edit_prompt", "Prompt"),
        ("m", "next_metric", "Metric"),
        Binding("plus,equals_sign", "score(0.01)", "Target +", show=False),
        Binding("minus", "score(-0.01)", "Target -", show=False),
        ("f2", "done", "Done"),
        ("x", "stop", "Stop"),
        ("s", "start", "Resume"),
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
    TuneScreen #body.-stacked { layout: vertical; }
    TuneScreen #body.-stacked #dis-panel { width: 1fr; height: 5fr; }
    TuneScreen #body.-stacked #text-panel { width: 1fr; height: 4fr; }
    TuneScreen #detail-scroll { height: 1fr; }
    TuneScreen #detail, TuneScreen #reasoning-head, TuneScreen #reasoning { height: auto; }
    TuneScreen #reasoning-head { color: $accent; text-style: bold; margin-top: 1; }
    TuneScreen #controls { height: 3; align: center middle; }
    TuneScreen #controls Horizontal { height: 1; width: auto; }
    TuneScreen #action-row { margin-top: 1; }
    TuneScreen #controls Button { margin: 0 1; }
    TuneScreen #controls #score-down, TuneScreen #controls #score-up { margin: 0; }
    TuneScreen #target { width: 16; }
    TuneScreen #score { width: 6; text-align: center; text-style: bold; }
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
        self.model = self.config.classifier_model
        self.rows = [r for r in files.read_gold() if r.split == "dev" and r.labels]
        self.predicted: list[set[str]] = []
        self.errors: dict[int, str] = {}
        self.reasoning: dict[int, str] = {}
        self.metrics: metrics.Metrics | None = None
        self.running = self.stopped = False
        self.asking = False  # the one-shot proposal call is in flight
        self.worker = None
        self.history: list[float] = []  # target value after each prompt version
        self.note = ""
        self.agent = Agent(
            self.config.assistant_model,
            instructions=INSTRUCTIONS,
            output_type=str,
            model_settings=files.thinking_settings(self.config),
            defer_model_check=True,
        )

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
        with panel(Vertical(id="metrics-panel"), "dev set"):
            yield Static("", id="summary")
            yield DataTable(id="per-label")
            yield Static("", id="trend", classes="note")
        with Horizontal(id="body"):
            with panel(Vertical(id="dis-panel"), "disagreements"):
                yield DataTable(id="dis", cursor_type="row")
            with (
                panel(Vertical(id="text-panel"), "text · classifier reasoning"),
                VerticalScroll(id="detail-scroll"),
            ):
                yield Static("", id="detail")
                yield Static("classifier reasoning", id="reasoning-head")
                yield Static("", id="reasoning", markup=False)
        with Vertical(id="controls"):
            with Horizontal(id="target-row"):
                yield Select(
                    [(m, m) for m in METRICS],
                    value=self.config.target_metric,
                    allow_blank=False,
                    compact=True,
                    id="target",
                )
                yield Button("−", id="score-down", compact=True)
                yield Static("", id="score")
                yield Button("+", id="score-up", compact=True)
            with Horizontal(id="action-row"):
                yield key_button("Propose edit", "e", id="propose", compact=True)
                yield key_button("Edit prompt", "o", id="edit-prompt", compact=True)
                yield key_button("Done", "F2", id="done", compact=True)
        yield Static("", id="note", markup=False)
        yield RunIndicator()
        yield AppFooter()

    def on_mount(self) -> None:
        if not self.ready:
            return
        self.query_one(RunIndicator).set_title("Running the dev set")
        report.disagreement_columns(self.query_one("#dis", DataTable))
        report.per_label_columns(self.query_one("#per-label", DataTable))
        self.rerun()

    def on_resize(self) -> None:
        if self.ready:
            self.query_one("#body").set_class(self.size.width >= 120, "-stacked")
            self.call_after_refresh(self.show)  # needs the laid-out table width

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "stop":
            return self.running
        if action == "start":
            return self.stopped
        return True

    def rerun(self) -> None:
        """Classify the dev set with the current prompt; cached items are free."""
        self.running, self.stopped = True, False
        self.note = ""
        self.worker = self.run_worker(self.run_dev(), exclusive=True)

    def action_start(self) -> None:
        if self.stopped:
            self.rerun()  # finished items come back from the classifier cache

    def action_stop(self) -> None:
        if self.worker is not None and self.running:
            self.worker.cancel()

    async def run_dev(self) -> None:
        indicator = self.query_one(RunIndicator)
        total = len(self.rows)
        predicted: list[set[str]] = [set() for _ in self.rows]
        errors: dict[int, str] = {}
        reasoning: dict[int, str] = {}
        done = live = 0
        detail = (
            f"prompt version {len(self.history) + 1}"
            if self.history
            else f"classifier {self.config.classifier_model}"
        )
        start = time.monotonic()
        finished = False
        indicator.set_button("stop")
        indicator.set_progress(0, total, detail=detail)
        self.show()
        try:
            async for i, p in classify_many(
                [r.text for r in self.rows], self.prompt, self.taxonomy, self.model
            ):
                if p.labels is None:  # a failed call counts as a disagreement
                    errors[i] = p.error or "failed"
                else:
                    predicted[i] = set(p.labels)
                    if p.reasoning:
                        reasoning[i] = p.reasoning
                done += 1
                live += not p.cached
                indicator.set_progress(
                    done,
                    total,
                    eta_text(done, total, live, time.monotonic() - start),
                    detail,
                )
            finished = True
            self.predicted, self.errors, self.reasoning = predicted, errors, reasoning
            self.metrics = metrics.compute_metrics(
                [set(r.labels) for r in self.rows],
                predicted,
                files.all_labels(self.taxonomy),
            )
            self.history.append(self.target())
        except Exception as e:  # noqa: BLE001  auth/network errors must not kill the app
            finished = True  # failed, not stopped: the panels show again
            self.note = f"Dev run failed: {e}"
        finally:
            self.running = False
            self.stopped = not finished
            if self.is_attached:  # a stage switch can remove the screen mid-run
                indicator.set_button("resume" if self.stopped else None)
                self.show()
                if not self.stopped:
                    self.call_after_refresh(self.show)  # the table needs its width
                    if self.focused is None:
                        self.query_one("#dis").focus()

    def target(self) -> float:
        assert self.metrics
        return metrics.target_value(self.metrics, self.config.target_metric)

    def met(self) -> bool:
        return self.metrics is not None and self.target() >= self.config.target_score

    def show(self) -> None:
        m = self.metrics
        busy = self.running or self.stopped
        for id_ in ("metrics-panel", "body", "controls"):
            self.query_one(f"#{id_}").display = not busy
        self.query_one(RunIndicator).display = busy
        names = [lab.name for lab in self.taxonomy.labels]
        target = self.config.target_metric
        retitle(
            self.query_one("#metrics-panel"),
            subtitle=f"target {target} ≥ {self.config.target_score:.2f}",
        )
        self.query_one("#score", Static).update(f"{self.config.target_score:.2f}")
        select = self.query_one("#target", Select)
        if select.value != target:
            select.value = target
        wrong = m.disagreements if m else []
        idle = not busy and not self.asking
        self.query_one("#propose", Button).disabled = not (idle and wrong)
        self.query_one("#edit-prompt", Button).disabled = not (idle and m)
        done = self.query_one("#done", Button)
        done.disabled = busy or m is None
        done.variant = "success" if self.met() else "default"
        self.refresh_bindings()
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
        retitle(self.query_one("#dis-panel"), f"disagreements · {len(wrong)}")
        for i in wrong:
            predicted = "failed" if i in self.errors else self.predicted[i]
            table.add_row(
                report.clipped(self.rows[i].text),
                report.tags(names, self.rows[i].labels),
                report.tags(names, predicted),
                key=str(i),
            )
        note = self.query_one("#note", Static)
        say(note, self.note)
        note.set_classes(
            "note"
            if self.note.startswith("Proposing")
            else "error"
            if "failed:" in self.note
            else "warn"
        )
        self.show_detail()

    def show_detail(self) -> None:
        table = self.query_one("#dis", DataTable)
        text, reasoning = "", None
        if self.metrics and table.row_count:
            i = int(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)  # ty: ignore[invalid-argument-type]
            text = escape(self.rows[i].text)
            if i in self.errors:
                text += f"\n\n[$error]Model failed: {escape(self.errors[i])}[/]"
            else:
                reasoning = self.reasoning.get(i)
        self.query_one("#detail", Static).update(text)
        self.query_one("#reasoning-head").display = bool(reasoning)
        reason = self.query_one("#reasoning", Static)
        reason.update(reasoning or "")
        reason.display = bool(reasoning)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.show_detail()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value != self.config.target_metric:
            self.config.target_metric = event.value  # ty: ignore[invalid-assignment]
            files.write_config(self.config)
            self.show()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        id_ = event.button.id
        if id_ == "score-down":
            self.action_score(-0.01)
        elif id_ == "score-up":
            self.action_score(0.01)
        elif id_ == "propose":
            self.action_propose()
        elif id_ == "edit-prompt":
            self.action_edit_prompt()
        elif id_ == "done":
            self.action_done()
        elif "Stop" in str(event.button.label):
            self.action_stop()
        else:
            self.action_start()

    def action_next_metric(self) -> None:
        if not self.ready or self.running or self.stopped:
            return
        self.config.target_metric = METRICS[  # ty: ignore[invalid-assignment]
            (METRICS.index(self.config.target_metric) + 1) % len(METRICS)
        ]
        files.write_config(self.config)
        self.show()

    def action_score(self, step: float) -> None:
        if not self.ready or self.running or self.stopped:
            return
        self.config.target_score = min(
            1.0, max(0.0, round(self.config.target_score + step, 2))
        )
        files.write_config(self.config)
        self.show()

    def action_propose(self) -> None:
        if (
            not self.ready
            or self.running
            or self.stopped
            or self.asking
            or not self.metrics
        ):
            return
        if not self.metrics.disagreements:
            self.note = "No disagreements to learn from."
            self.show()
            return
        self.note = "Proposing a prompt edit..."
        self.asking = True
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
            self.asking = False
            self.show()
            return
        model = self.agent.model
        name = model if isinstance(model, str) else getattr(model, "model_name", "?")
        cost.record(name, result.usage, cost.messages_dollars(result.new_messages()))
        self.note = ""
        self.asking = False
        self.show()
        self.app.push_screen(ProposalScreen(self.prompt, result.output), self.accepted)

    def action_edit_prompt(self) -> None:
        if not self.ready or self.running or self.stopped or not self.metrics:
            return
        self.app.push_screen(PromptEditScreen(self.prompt), self.accepted)

    def accepted(self, new: str | None) -> None:
        if new is None or not new.strip() or new == self.prompt:
            return
        files.write_text("prompt.md", new)
        self.prompt = new
        self.rerun()

    def action_done(self) -> None:
        if not self.ready or self.running or self.stopped or not self.metrics:
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
