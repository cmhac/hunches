import asyncio
import dataclasses
import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import ClassVar, Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ToolCallPart
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.markup import escape
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Select, Static, TextArea

from hunches import files, history, metrics
from hunches.app import (
    AppFooter,
    ChatPanel,
    ConfirmScreen,
    StageBanner,
    StatusHeader,
    confirm_approve,
    current_status,
    key_button,
    modal_box,
    panel,
    plan_hint,
    retitle,
    say,
)
from hunches.classifier import classify_many
from hunches.screens import gold as gold_screen
from hunches.screens import report
from hunches.screens.progress import RunIndicator, eta_text
from hunches.screens.taxonomy import prompt_change, taxonomy_text
from hunches.theme import diff_markup, editor

MAX_SHOWN = 20  # disagreements the assistant sees
METRICS = ["accuracy", "macro_f1", "micro_f1", "exact_match"]

CANNED = "Propose a prompt edit based on the current disagreements."
NOT_AVAILABLE = "Not available while the dev set is running."
PENDING = "Pending: the user has not decided yet"
META = "chat/tuning.meta.json"
PROPOSALS = "chat/tuning.proposals.json"
EMPTY_CHAT = "The assistant gets the results when the dev run finishes."
METRIC_NAMES = {
    "accuracy": "accuracy",
    "exact_match": "exact-match",
    "macro_f1": "macro-F1",
    "micro_f1": "micro-F1",
}
INSTRUCTIONS = """\
You help the user improve the prompt of a text classifier. You see what they see: the current \
prompt, the taxonomy, the target metric and the disagreements (dev-set items where the \
classifier's labels differ from the gold labels). Reply in prose and never output the prompt \
as plain text. Each disagreement includes the classifier's own reasoning. Use it to explain \
why the classifier chose its label and to decide what the prompt is missing. Call \
get_disagreements to read more of them. Call propose_prompt only when the user asks for an \
edit or agrees to one, with the complete new prompt: keep what works, fix what causes the \
errors, and do not tailor the prompt to individual items. The user reviews the diff and \
decides; the tool tells you the outcome.
"""
FIRST_REPLY = (
    "Reply in two or three sentences: where the classifier stands against the target and the "
    "main pattern in the errors. Offer to propose a prompt edit. Call propose_prompt only "
    "when the user asks or agrees."
)
STATUS_REPLY = (
    "Reply in one or two sentences: what changed in the pipeline status or the gold coverage "
    "and what it means for tuning. Do not repeat the lists."
)
UPDATE_REPLY = (
    "Reply in two or three sentences: what changed since the last run and whether the target "
    "is met."
)


def status_digest() -> str:
    """What the assistant was last told about the pipeline: the two context sections."""
    return hashlib.sha256(files.assistant_context().encode()).hexdigest()


def removal_question(rows: list[files.GoldRow], reason: str) -> str:
    """The confirmation for the assistant's remove_gold; the held-out warning whenever a test row is in it."""
    counts = [
        (n, split)
        for split in ("dev", "test")
        if (n := sum(r.split == split for r in rows))
    ]
    what = " and ".join(
        f"{n} {split} row{'' if n == 1 else 's'}" for n, split in counts
    )
    text = (
        f"The assistant wants to remove {what}.\n\nReason: {reason}\n\n"
        "The rows and their labels are kept in gold_removed.jsonl and are never drawn again."
    )
    if any(r.split == "test" for r in rows):
        text += (
            "\n\nTest rows are held out so that the test result is an honest estimate. "
            "Replacing labelled test rows changes the items the result is measured on, and the "
            "test evaluation has to be run again."
        )
    return text


def digest_of(prompt: str, model: str, rows: list, m: metrics.Metrics) -> str:
    """What makes a run worth telling the assistant about: prompt, classifier, gold dev rows, result."""
    gold = [(r.id, r.text, sorted(r.labels)) for r in rows]
    raw = json.dumps([prompt, model, gold, dataclasses.asdict(m)], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def read_meta() -> dict | None:
    text = files.read_text(META)
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def write_meta(meta: dict) -> None:
    path = files.root() / META
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = (
        read_meta() or {}
    )  # the dev-run digest and the status digest are written separately
    path.write_text(
        json.dumps({**kept, **meta, "sent_at": datetime.now(UTC).isoformat()})
    )


def prompt_record(intro: str, old: str, new: str) -> str:
    """Body of a YOU EDITED line for a prompt change: what changed, then the whole new prompt."""
    return f"{intro}\n{prompt_change(old, new)[1]}\n\n# Current prompt\n{new}"


def diff_size(old: str, new: str) -> tuple[int, int]:
    lines = prompt_change(old, new)[1].splitlines()
    return (
        sum(ln.startswith("+") for ln in lines),
        sum(ln.startswith("-") for ln in lines),
    )


class ProposalScreen(ModalScreen[str | None]):
    """Shows a diff against the current prompt; the proposal is editable.

    Dismisses with the accepted text, None (rejected) or "" (Esc: not decided yet).
    """

    AUTO_FOCUS = "#accept"
    BINDINGS: ClassVar = [("escape", "later", "Decide later")]
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

    def action_later(self) -> None:
        self.dismiss("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        text = self.query_one("#proposal", TextArea).text
        self.dismiss(text if event.button.id == "accept" and text.strip() else None)


class PromptEditScreen(ModalScreen[str | None]):
    """Edit prompt.md by hand. Dismisses with the new text (Save and re-run) or None."""

    AUTO_FOCUS = "#prompt"
    # F6/F7 are priority bindings: a focused TextArea binds them itself (select line, select all)
    BINDINGS: ClassVar = [
        ("escape", "cancel", "Cancel"),
        ("f2", "save", "Save"),
        Binding("f6", "undo", "Undo", priority=True),
        Binding("f7", "redo", "Redo", priority=True),
    ]
    DEFAULT_CSS = """
    PromptEditScreen { align: center middle; }
    PromptEditScreen > Vertical { width: 1fr; height: 1fr; margin: 1 2; }
    PromptEditScreen .panel { height: 1fr; }
    PromptEditScreen TextArea { height: 1fr; border: none; padding: 0; }
    PromptEditScreen #note-line { height: auto; }
    PromptEditScreen #history-row { height: 1; }
    PromptEditScreen #history-row Button { margin-right: 1; }
    PromptEditScreen #hist-note { width: 1fr; color: $text-muted; text-wrap: nowrap; text-overflow: ellipsis; }
    PromptEditScreen #buttons { height: auto; align-horizontal: right; }
    """

    def __init__(self, current: str) -> None:
        super().__init__()
        self.current = (
            current  # the text of prompt.md: what the box shows when nothing is typed
        )
        self.moved = False  # undo or redo changed prompt.md while the box was open
        self.last = ""  # the summary of the last undo or redo

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
            with Horizontal(id="history-row"):
                yield key_button("Undo", "F6", id="undo")
                yield key_button("Redo", "F7", id="redo")
                yield Static("", id="hist-note")
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

    def on_mount(self) -> None:
        self.sync()

    def typed(self) -> bool:
        """The box differs from prompt.md: a draft, which is not in the history."""
        return self.query_one("#prompt", TextArea).text != self.current

    def changed(self) -> bool:
        return bool(self.query_one("#prompt", TextArea).text.strip()) and self.typed()

    def sync(self) -> None:
        typed = self.typed()
        rerun = (
            self.moved and not typed
        )  # prompt.md already holds the text: only re-run
        save = self.query_one("#save", Button)
        save.label = "Re-run  F2" if rerun else "Save and re-run  F2"
        save.disabled = not (self.changed() or rerun)
        self.query_one("#undo", Button).disabled = typed or not history.can_undo(
            "prompt"
        )
        self.query_one("#redo", Button).disabled = typed or not history.can_redo(
            "prompt"
        )
        self.query_one("#hist-note", Static).update(
            "Typing is undone with ctrl+z. Undo F6 is off until you save or discard."
            if typed
            else self.last or "F6 steps back through saved versions of prompt.md."
        )
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in (
            "undo",
            "redo",
        ):  # False: the text area gets the key (select line, select all)
            can = history.can_undo if action == "undo" else history.can_redo
            return not self.typed() and can("prompt")
        return True

    def step(self, redo: bool) -> None:
        entry = (history.redo if redo else history.undo)("prompt")
        if entry is None:
            return
        self.current = files.read_text("prompt.md") or ""
        self.moved = True
        self.last = entry["summary"]
        self.query_one("#prompt", TextArea).text = self.current
        self.sync()

    def action_undo(self) -> None:
        if not self.typed():
            self.step(False)

    def action_redo(self) -> None:
        if not self.typed():
            self.step(True)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.sync()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        if self.changed() or (self.moved and not self.typed()):
            self.dismiss(self.query_one("#prompt", TextArea).text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "save":
                self.action_save()
            case "undo":
                self.action_undo()
            case "redo":
                self.action_redo()
            case _:
                self.action_cancel()


KEY_LABELS = [  # (key, label under 120 columns, label from 120)
    ("e", "Propose", "Propose edit"),
    ("o", "Prompt", "Edit prompt"),
    ("m", "Metric", "Target metric"),
]


class ProposalCard(Vertical):
    """A proposal in the chat: pending (Review, Reject), accepted, rejected or superseded.

    `entry` is the screen's dict (id, status, plus, minus, edited); the card draws whatever it says.
    """

    DEFAULT_CSS = """
    ProposalCard { height: auto; margin-top: 1; padding: 0 1; background: $boost; border-left: outer $accent; }
    ProposalCard Static { height: auto; }
    ProposalCard .size { color: $text-muted; }
    ProposalCard .buttons { height: 1; margin-top: 1; }
    ProposalCard Button { margin-right: 1; }
    """

    def __init__(
        self,
        entry: dict,
        review: Callable[[], None],
        reject: Callable[[], None],
    ) -> None:
        super().__init__(classes="turn card")
        self.entry = entry
        self.review, self.reject = review, reject

    @property
    def text(self) -> str:
        e = self.entry
        status = {
            "pending": "",
            "accepted": "Accepted" + (" · edited" if e.get("edited") else ""),
            "rejected": "Rejected. The assistant keeps the current prompt.",
            "superseded": "Superseded by your own edit.",
        }[e["status"]]
        return f"Proposed prompt change  +{e['plus']} −{e['minus']}\n{status}".strip()

    def compose(self) -> ComposeResult:
        head, _, status = self.text.partition("\n")
        yield Static(head, classes="size", markup=False)
        if status:
            yield Static(status, markup=False)
        if self.entry["status"] == "pending":
            with Horizontal(classes="buttons"):
                yield Button("Review", id="review", compact=True)
                yield Button("Reject", id="reject-card", compact=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        (self.review if event.button.id == "review" else self.reject)()


class Tab(Static):
    """One label of the Chat | Results strip."""

    class Picked(Message):
        def __init__(self, key: str) -> None:
            super().__init__()
            self.key = key

    def __init__(self, label: str, key: str) -> None:
        super().__init__(label, id=f"tab-{key}", classes="tab")
        self.label_text = label
        self.key = key

    def on_click(self) -> None:
        self.post_message(self.Picked(self.key))


class TuneScreen(Screen):
    """Stage 5: dev-set metrics, disagreements, and assistant prompt edits."""

    BINDINGS: ClassVar = [
        ("c", "chat", "Chat"),
        ("e", "propose", "Propose"),
        ("o", "edit_prompt", "Prompt"),
        ("m", "next_metric", "Metric"),
        Binding("plus,equals_sign", "score(0.01)", "Target +", show=False),
        Binding("minus", "score(-0.01)", "Target -", show=False),
        ("f2", "done", "Done"),
        ("r", "rerun", "Re-run"),
        ("x", "stop", "Stop"),
        ("s", "start", "Resume"),
    ]
    AUTO_FOCUS = "#dis"
    DEFAULT_CSS = """
    TuneScreen #cols { height: 1fr; }
    TuneScreen ChatPanel { width: 42; }
    TuneScreen.-narrow ChatPanel { width: 1fr; }
    TuneScreen #results { width: 1fr; height: 1fr; }
    TuneScreen #tabs { height: 1; margin-bottom: 1; background: $surface; }
    TuneScreen .tab { width: auto; padding: 0 1 0 2; color: $text-muted; }
    TuneScreen .tab.-active { background: $panel; color: #EEF1F5; text-style: bold; border-left: outer $primary; }
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
        # the components the last finished dev run was made under; Done waits until they are current
        self.ran: dict[str, str] | None = None
        self.running = self.stopped = False
        self.worker = None
        self.tab = "results"  # under 120 columns: "chat" or "results"
        self.unread = False  # the assistant spoke while Results was showing
        self.pending: list[
            tuple[str, str]
        ] = []  # YOU EDITED lines waiting for a quiet chat
        self.proposals: list[dict] = self.read_proposals()
        self.cards: dict[str, ProposalCard] = {}
        self.history: list[float] = []  # target value after each prompt version
        self.note = ""
        self.agent = Agent(
            self.config.assistant_model,
            instructions=INSTRUCTIONS,
            model_settings=files.thinking_settings(self.config),
            defer_model_check=True,
        )

        @self.agent.instructions
        def current_state() -> str:
            m = self.metrics
            target = f"{self.config.target_metric} >= {self.config.target_score:.2f}"
            if m:
                value = metrics.target_value(m, self.config.target_metric)
                target += f" (dev set now: {value:.3f})"
            return (
                f"# Current prompt\n{self.prompt or 'None yet.'}\n\n"
                f"# Current taxonomy\n{self.taxonomy_text()}\n\n# Target\n{target}\n\n"
                f"{files.assistant_context()}"
            )

        @self.agent.tool_plain
        async def get_disagreements(label: str | None = None, limit: int = 10) -> str:
            """Read dev-set disagreements (text, gold, predicted, the classifier's reasoning), optionally only those whose gold or predicted labels include `label`."""
            if self.running or self.stopped:
                return NOT_AVAILABLE
            return self.disagreements_text(label, limit)

        @self.agent.tool_plain
        async def get_gold_coverage(split: Literal["dev", "test"] | None = None) -> str:
            """Read the gold coverage: rows, labelled rows and the rows no longer in the candidate pool (id, text, labels), optionally for one split."""
            return files.gold_coverage_text(split)

        @self.agent.tool_plain
        async def remove_gold(ids: list[str], reason: str) -> str:
            """Remove gold rows by id, for example rows that are no longer in the candidate pool. The user confirms; nothing is removed until they do. Their labels are kept in a log."""
            wanted = set(ids)
            rows = [r for r in files.read_gold() if r.id in wanted]
            if not rows:
                return "No gold row has those ids. Nothing removed."
            if not await self.app.push_screen_wait(
                ConfirmScreen(removal_question(rows, reason))
            ):
                return "The user rejected the removal."
            n = gold_screen.remove(ids, reason)
            self.run_worker(self.sync_status(), group="status")
            return f"Removed {n} rows."

        @self.agent.tool_plain
        async def draw_gold(split: Literal["dev", "test"], n: int) -> str:
            """Draw n more candidates into a gold split, for example after rows were removed. They start unlabelled; the user labels them, you cannot."""
            if n < 1:
                return "Nothing drawn: n must be at least 1."
            rows = gold_screen.draw(split, n)
            self.run_worker(self.sync_status(), group="status")
            return (
                f"Drew {len(rows)} unlabelled {split} rows. They are not labelled yet: "
                "the user labels them on the gold screen."
            )

        @self.agent.tool
        async def propose_prompt(
            ctx: RunContext[object], prompt: str, rationale: str
        ) -> str:
            """Propose the complete new classifier prompt. The user reviews the diff and decides; you are told the outcome."""
            if self.running or self.stopped:
                return NOT_AVAILABLE
            plus, minus = diff_size(self.prompt, prompt)
            entry = {
                "id": ctx.tool_call_id or "",
                "status": "pending",
                "plus": plus,
                "minus": minus,
            }
            self.proposals.append(entry)
            self.save_proposals()
            card = self.make_card(entry, prompt)
            await self.query_one(ChatPanel).add(card)
            self.unread = self.unread or self.tab == "results"
            result = await self.app.push_screen_wait(
                ProposalScreen(self.prompt, prompt)
            )
            return self.decide(entry, prompt, result)

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
        yield StageBanner(self.banner_text, id="stale-banner")
        with Horizontal(id="tabs"):
            yield Tab("Chat", "chat")
            yield Tab("Results", "results")
        with Horizontal(id="cols"):
            chat = ChatPanel("tuning", self.agent, empty=EMPTY_CHAT)
            chat.card_for = self.card_for
            yield chat
            with Vertical(id="results"):
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
                        yield key_button("Re-run", "r", id="rerun", compact=True)
                    with Horizontal(id="action-row"):
                        yield key_button(
                            "Propose edit", "e", id="propose", compact=True
                        )
                        yield key_button(
                            "Edit prompt", "o", id="edit-prompt", compact=True
                        )
                        yield key_button("Done", "F2", id="done", compact=True)
                yield Static("", id="note", markup=False)
                yield RunIndicator()
        yield AppFooter()

    def banner_text(self) -> str:
        """The STALE banner: what changed and what to do about it."""
        if self.running or self.stopped or self.metrics is None:
            return ""
        kind, reason = current_status()[5]
        if not self.current:
            if changed := files.changed(self.ran or {}):
                reason = files.REASONS[changed[0]]
            return (
                f"STALE: {reason or 'inputs changed'}. These results are from before the "
                "change. Press r to re-run, then approve again." + plan_hint()
            )
        if kind != "stale":
            return ""
        return (
            f"STALE: {reason}. The results below are current. Approve again with F2."
            + plan_hint()
        )

    @property
    def current(self) -> bool:
        """The metrics on screen were made with the prompt, taxonomy, model and gold rows as they are now."""
        return self.ran is not None and not files.changed(self.ran)

    def on_mount(self) -> None:
        if not self.ready:
            return
        self.query_one(RunIndicator).set_title("Running the dev set")
        report.disagreement_columns(self.query_one("#dis", DataTable))
        report.per_label_columns(self.query_one("#per-label", DataTable))
        self.rerun()

    def on_resize(self) -> None:
        if self.ready:
            wide = self.size.width >= 120
            self.query_one("#body").set_class(wide, "-stacked")
            self.set_class(not wide, "-narrow")
            for key, short, long in KEY_LABELS:
                bindings = self._bindings.key_to_bindings[key]
                self._bindings.key_to_bindings[key] = [
                    dataclasses.replace(b, description=long if wide else short)
                    for b in bindings
                ]
            self.place_panels()
            self.call_after_refresh(self.show)  # needs the laid-out table width

    def place_panels(self) -> None:
        """Chat and tabs vs results: side by side from 120 columns, one tab at a time below, none during a run."""
        if not self.ready:
            return
        narrow = self.size.width < 120
        busy = self.running or self.stopped
        chat = self.query_one(ChatPanel)
        chat.display = not busy and (not narrow or self.tab == "chat")
        self.query_one("#results").display = busy or not (narrow and self.tab == "chat")
        self.query_one("#tabs").display = narrow and not busy
        for tab in self.query(Tab):
            tab.set_class(tab.key == self.tab, "-active")
            unread = tab.key == "chat" and self.unread and self.tab == "results"
            tab.update(tab.label_text + (" ●" if unread else ""))
        self.refresh_bindings()

    def action_chat(self) -> None:
        self.tab = "results" if self.tab == "chat" else "chat"
        self.unread = self.unread and self.tab != "chat"
        self.place_panels()

    def on_tab_picked(self, event: Tab.Picked) -> None:
        if event.key != self.tab:
            self.action_chat()

    def on_chat_panel_changed(self, event: ChatPanel.Changed) -> None:
        if not self.query_one(ChatPanel).running:  # a reply just finished
            self.unread = self.unread or self.tab == "results"
        self.sync_controls()
        self.place_panels()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "chat":
            return self.size.width < 120
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

    def action_rerun(self) -> None:
        """r: classify the dev set again with the files as they are now (cached items are free)."""
        if not self.ready or self.running or self.stopped:
            return
        rows = [r for r in files.read_gold() if r.split == "dev" and r.labels]
        if [(r.id, r.labels) for r in rows] != [(r.id, r.labels) for r in self.rows]:
            # other rows than the results on screen were made with: those results go
            self.rows = rows
            self.metrics, self.predicted = None, []
            self.errors, self.reasoning = {}, {}
        self.rerun()

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
        finished = completed = False
        snapshot = files.current_inputs("dev_done")
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
            self.ran = snapshot
            completed = True
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
                if completed:
                    self.run_worker(
                        self.sync_context_and_status(), group="context", exclusive=True
                    )

    def target(self) -> float:
        assert self.metrics
        return metrics.target_value(self.metrics, self.config.target_metric)

    def met(self) -> bool:
        return self.metrics is not None and self.target() >= self.config.target_score

    def show(self) -> None:
        m = self.metrics
        busy = self.running or self.stopped
        self.query_one(StageBanner).refresh_text()
        for id_ in ("metrics-panel", "body", "controls"):
            self.query_one(f"#{id_}").display = not busy
        self.query_one(RunIndicator).display = busy
        self.place_panels()
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
        self.sync_controls()
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
        note.set_classes("error" if "failed:" in self.note else "warn")
        self.show_detail()

    def sync_controls(self) -> None:
        m = self.metrics
        busy = self.running or self.stopped
        idle = not busy and not self.query_one(ChatPanel).running
        self.query_one("#propose", Button).disabled = not (
            idle and m and m.disagreements
        )
        self.query_one("#edit-prompt", Button).disabled = not (not busy and m)
        self.query_one("#rerun", Button).disabled = busy
        done = self.query_one("#done", Button)
        done.disabled = busy or m is None or not self.current
        done.variant = "success" if self.met() else "default"
        self.refresh_bindings()

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

    def set_target(self, metric: str | None = None, score: float | None = None) -> None:
        """Change the target, and tell the assistant with a YOU EDITED line (no model call)."""
        config = self.config
        lines = []
        if metric is not None and metric != config.target_metric:
            lines.append(f"target metric: {config.target_metric} → {metric}")
            config.target_metric = metric  # ty: ignore[invalid-assignment]
        if score is not None and score != config.target_score:
            lines.append(f"target score: {config.target_score:.2f} → {score:.2f}")
            config.target_score = score
        files.write_config(config)
        if lines:
            self.note_edit(
                f"Target: {config.target_metric} ≥ {config.target_score:.2f}",
                "\n".join(lines),
            )
            self.show()

    def on_select_changed(self, event: Select.Changed) -> None:
        self.set_target(metric=str(event.value))

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
        elif id_ == "rerun":
            self.action_rerun()
        elif id_ == "done":
            self.action_done()
        elif "Stop" in str(event.button.label):
            self.action_stop()
        else:
            self.action_start()

    def action_next_metric(self) -> None:
        if not self.ready or self.running or self.stopped:
            return
        self.set_target(
            metric=METRICS[
                (METRICS.index(self.config.target_metric) + 1) % len(METRICS)
            ]
        )

    def action_score(self, step: float) -> None:
        if not self.ready or self.running or self.stopped:
            return
        self.set_target(
            score=min(1.0, max(0.0, round(self.config.target_score + step, 2)))
        )

    def action_propose(self) -> None:
        chat = self.query_one(ChatPanel)
        if (
            not self.ready
            or self.running
            or self.stopped
            or chat.running
            or not self.metrics
        ):
            return
        if not self.metrics.disagreements:
            self.note = "No disagreements to learn from."
            self.show()
            return
        self.tab = "chat"  # under 120 columns, show the answer
        self.place_panels()
        chat.send(CANNED)

    def action_edit_prompt(self) -> None:
        if not self.ready or self.running or self.stopped or not self.metrics:
            return
        modal = PromptEditScreen(self.prompt)
        self.app.push_screen(modal, lambda new: self.manual(new, modal.moved))

    def manual(self, new: str | None, moved: bool = False) -> None:
        """The Edit prompt modal closed: tell the assistant what the user changed, then re-run.

        `moved`: undo or redo changed prompt.md inside the modal. The screen follows the file even if the
        user cancelled, and re-runs only when they chose Re-run.
        """
        if moved:
            self.history_changed(history.entries("prompt")[-1])
        if new is None or not new.strip():
            return
        if new == self.prompt:
            if moved:
                self.rerun()
            return
        self.note_edit(
            "Prompt: edited by the user",
            prompt_record(
                "You edited the prompt yourself (no proposal):", self.prompt, new
            ),
        )
        self.accepted(new)

    def history_changed(self, entry: dict, note: str | None = None) -> None:
        """prompt.md moved (undo, redo, restore, an outside edit): follow it. Nothing is re-run."""
        disk = files.read_text("prompt.md") or ""
        if disk == self.prompt:
            return
        for pending in self.proposals:
            if pending["status"] == "pending":  # its diff no longer applies
                self.set_status(pending, "superseded")
        old, self.prompt = self.prompt, disk
        if entry["source"] in ("undo", "redo", "restore"):
            self.note = note or entry["summary"]
            self.note_edit(entry["summary"], prompt_record(entry["summary"], old, disk))
        self.show()

    def accepted(self, new: str | None) -> None:
        """A new prompt text (accepted proposal or manual edit): write it, drop stale proposals, re-run."""
        if new is None or not new.strip() or new == self.prompt:
            return
        for entry in self.proposals:
            if entry["status"] == "pending":  # its diff no longer applies
                self.set_status(entry, "superseded")
        history.save("prompt", new, "user", "Prompt: accepted")
        self.prompt = new
        self.rerun()

    def action_done(self) -> None:
        if (
            not self.ready
            or self.running
            or self.stopped
            or not self.metrics
            or not self.current
        ):
            return
        goto = lambda: self.app.goto_stage(self.app.stage + 1)  # ty: ignore[unresolved-attribute]
        score = f"dev {self.config.target_metric} {self.target():.3f}"
        if self.met():
            files.approve("dev_done", 5, f"Approved: Tuning loop ({score})")
            goto()
            return
        confirm_approve(
            self,
            "dev_done",
            5,
            f"{self.config.target_metric} {self.target():.3f} is below the target "
            f"{self.config.target_score:.2f}. Accept tuning anyway?",
            f"Approved: Tuning loop ({score}, below target)",
            then=goto,
        )

    # ---- what the assistant is told

    def taxonomy_text(self) -> str:
        return taxonomy_text(
            self.taxonomy.mode, [(x.name, x.description) for x in self.taxonomy.labels]
        )

    def describe(self, indexes: list[int], label: str | None = None) -> str:
        """Numbered disagreements (rank among all of them), with the classifier's reasoning."""
        assert self.metrics
        out = []
        for rank, i in enumerate(self.metrics.disagreements, 1):
            gold = set(self.rows[i].labels)
            got = None if i in self.errors else self.predicted[i]
            if i not in indexes or (label and label not in gold | (got or set())):
                continue
            predicted = "failed" if got is None else ",".join(sorted(got))
            text = " ".join(self.rows[i].text.split())
            out.append(f"{rank}. gold {','.join(sorted(gold))} → {predicted}  {text}")
            if i in self.reasoning:
                out.append(f"     reasoning: {self.reasoning[i]}")
        return "\n".join(out)

    def disagreements_text(self, label: str | None, limit: int) -> str:
        if not self.metrics:
            return "No dev-set result yet."
        wrong = [
            i
            for i in self.metrics.disagreements
            if not label
            or label in self.rows[i].labels
            or (i not in self.errors and label in self.predicted[i])
        ]
        if not wrong:
            return (
                f"No disagreements for label {label}." if label else "No disagreements."
            )
        shown = wrong[: max(1, limit)]
        for_label = f" for label {label}" if label else ""
        head = f"{len(shown)} of {len(wrong)} disagreements{for_label}"
        return f"{head}\n{self.describe(shown)}"

    def run_context(self, first: bool) -> tuple[str, str]:
        """(message, one-line summary) telling the assistant about the finished dev run."""
        m = self.metrics
        assert m
        config = self.config
        value = self.target()
        names = [lab.name for lab in self.taxonomy.labels]
        shown = m.disagreements[:MAX_SHOWN]
        label = METRIC_NAMES[config.target_metric]
        line = f"{label} {value:.3f} (target {config.target_score:.2f})"
        if self.met():
            line += ": target met"
        for name, other in (
            ("accuracy", m.exact_match),
            ("macro-F1", m.macro_f1),
            ("micro-F1", m.micro_f1),
        ):
            if name != label and not (name == "accuracy" and label == "exact-match"):
                line += f" · {name} {other:.3f}"
        title = (
            "# Dev set" if first else f"# Dev set (prompt version {len(self.history)})"
        )
        text = f"{title}\n{line} · n={m.n}\n\n# Per label\n"
        text += "\n".join(
            f"{n.ljust(14)} P {x.precision:.2f}  R {x.recall:.2f}  F1 {x.f1:.2f}  gold {x.gold_count}"
            for n, x in m.per_label.items()
            if n in names or x.gold_count or x.predicted_count
        )
        more = (
            f"{len(m.disagreements)}, first {len(shown)} shown; call get_disagreements for the rest"
            if len(shown) < len(m.disagreements)
            else str(len(shown))
        )
        text += f"\n\n# Disagreements ({more})\n{self.describe(shown)}\n\n"
        if first:
            text += f"# Current prompt\n{self.prompt}\n\n# Taxonomy\n{self.taxonomy_text()}\n\n"
        text += f"{files.assistant_context()}\n\n"
        text += f"# Instructions\n{FIRST_REPLY if first else UPDATE_REPLY}"
        n = len(m.disagreements)
        plural = "" if n == 1 else "s"
        if first:
            return text, f"Context · dev {value:.3f} · {n} disagreement{plural}"
        return text, f"Dev run · {label} {value:.3f} · {n} disagreement{plural}"

    async def sync_context(self) -> None:
        """After a dev run: the first context turn, or an UPDATED one when the run is not what the assistant last saw."""
        if not self.ready or not self.metrics:
            return
        chat = self.query_one(ChatPanel)
        while chat.running:  # a reply may still be streaming
            await asyncio.sleep(0.05)
        await self.flush_records()
        digest = digest_of(
            self.prompt, self.config.classifier_model, self.rows, self.metrics
        )
        old = read_meta()
        if chat.history and old and old.get("context_digest") == digest:
            return
        first = not (chat.history and old)
        told = status_digest()
        text, summary = self.run_context(first)
        if not first and old and old.get("metric") == self.config.target_metric:
            summary = (
                f"Dev run · {METRIC_NAMES[self.config.target_metric]} "
                f"{old['value']:.3f} → {self.target():.3f}"
            )
        sent = len(chat.history)
        await chat.send_context(text, "context" if first else "update", summary)
        if len(chat.history) > sent:  # a failed turn must not claim to be sent
            write_meta(
                {
                    "context_digest": digest,
                    "status_digest": told,
                    "metric": self.config.target_metric,
                    "value": self.target(),
                }
            )

    async def sync_context_and_status(self) -> None:
        await self.sync_context()
        await self.sync_status()

    async def sync_status(self) -> None:
        """Add an UPDATED line when the pipeline status or gold coverage is not what the assistant last
        saw (spec 004 D9). Nothing is sent before a first context turn recorded what it saw."""
        if not self.ready:
            return
        chat = self.query_one(ChatPanel)
        while chat.running:
            await asyncio.sleep(0.05)
        await self.flush_records()
        old = read_meta()
        digest = status_digest()
        if not (chat.history and old and old.get("status_digest")):
            return
        if old["status_digest"] == digest:
            return
        text = f"{files.assistant_context()}\n\n# Instructions\n{STATUS_REPLY}"
        sent = len(chat.history)
        await chat.send_context(
            text, "update", "Pipeline status or gold coverage changed"
        )
        if len(chat.history) > sent:  # a failed turn must not claim to be sent
            write_meta({"status_digest": digest})

    def note_edit(self, summary: str, body: str) -> None:
        """Queue a YOU EDITED line; it is written once no reply is streaming (a turn would overwrite it)."""
        self.pending.append((summary, body))
        self.run_worker(self.flush_records(), group="records")

    async def flush_records(self) -> None:
        chat = self.query_one(ChatPanel)
        while chat.running:
            await asyncio.sleep(0.05)
        while self.pending:
            chat.record(*self.pending.pop(0))

    # ---- proposals

    def read_proposals(self) -> list[dict]:
        text = files.read_text(PROPOSALS)
        try:
            return json.loads(text) if text else []
        except ValueError:
            return []

    def save_proposals(self) -> None:
        path = files.root() / PROPOSALS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.proposals))

    def set_status(self, entry: dict, status: str, edited: bool = False) -> None:
        entry["status"] = status
        if edited:
            entry["edited"] = True
        self.save_proposals()
        if card := self.cards.get(entry["id"]):
            card.refresh(recompose=True)

    def make_card(self, entry: dict, proposed: str) -> ProposalCard:
        card = ProposalCard(
            entry,
            review=lambda: self.review(entry, proposed),
            reject=lambda: self.late(entry, proposed, None),
        )
        self.cards[entry["id"]] = card
        return card

    def card_for(self, call: ToolCallPart) -> ProposalCard | None:
        """The card that goes under a propose_prompt tool line (also when a resumed chat is redrawn)."""
        entry = next((e for e in self.proposals if e["id"] == call.tool_call_id), None)
        if call.tool_name != "propose_prompt" or entry is None:
            return None
        if old := self.cards.get(entry["id"]):
            old.remove()  # the live card; the tool line was redrawn after it
        return self.make_card(entry, str(call.args_as_dict().get("prompt", "")))

    def review(self, entry: dict, proposed: str) -> None:
        """Reopen a proposal whose modal was dismissed (or from an earlier session)."""
        if entry["status"] == "pending" and not self.running and not self.stopped:
            self.app.push_screen(
                ProposalScreen(self.prompt, proposed),
                lambda result: self.late(entry, proposed, result),
            )

    def late(self, entry: dict, proposed: str, result: str | None) -> None:
        """A decision on a card the assistant is no longer waiting for."""
        if result == "" or entry["status"] != "pending":
            return
        self.decide(entry, proposed, result)
        if result is None:
            self.note_edit(
                "Prompt: proposal rejected",
                "You rejected the proposal after closing it; the prompt is unchanged.\n\n"
                f"# Current prompt\n{self.prompt}",
            )

    def decide(self, entry: dict, proposed: str, result: str | None) -> str:
        """Apply the proposal modal's result; the return value is what the assistant is told."""
        if result == "":
            return PENDING
        if result is None:
            self.set_status(entry, "rejected")
            return "Rejected"
        edited = result != proposed
        self.set_status(entry, "accepted", edited)
        self.accepted(result)
        if not edited:
            return "Accepted"
        self.note_edit(
            "Prompt: proposal accepted with edits",
            prompt_record("You accepted the proposal and edited it:", proposed, result),
        )
        return f"Accepted with edits: {prompt_change(proposed, result)[1]}"
