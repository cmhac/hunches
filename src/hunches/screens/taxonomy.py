import difflib
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from typing import ClassVar, Literal

import yaml
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import DescendantFocus
from textual.markup import escape
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, Markdown, Select, Static, TextArea

from hunches import candidates, files, history, metrics
from hunches.app import (
    AppFooter,
    ChatPanel,
    ConfirmScreen,
    StatusHeader,
    confirm_approve,
    key_button,
    modal_box,
    panel,
    retitle,
    say,
)
from hunches.screens.brief import numbered
from hunches.theme import editor, label_tag

INSTRUCTIONS = """\
You define how items are classified, by interviewing the user and then writing two files.
Ask short questions, one or two at a time. Find out what kinds of item the user wants to \
tell apart, and what separates each kind from the others.
Whether each item gets exactly one label (mode "single") or possibly several (mode "multi") \
is the user's choice in the Labels panel, not a question for you. If the current mode is \
stated below, use it and do not ask about it. Otherwise pick the mode that fits what the user \
describes (the user can change it).
Then call write_taxonomy with the mode and labels (each with a short description), and \
write_prompt with the classifier prompt. "off_topic" is built in, always available and always \
exclusive: never list it as a label. If a tool returns an error, fix it and call it again. If \
it says the user is editing, tell them in the chat and try again after they have saved or \
discarded.
The prompt must describe each label, describe the off_topic label (the item matches none of \
the labels), and, for mode "single", say that exactly one label is returned. For mode \
"multi", say that every label that applies is returned and that off_topic is never combined \
with another label. The prompt is the classifier's system prompt; it will be shown the item text.
"""

CONTEXT_INSTRUCTIONS = (
    "Reply in two or three sentences: where things stand (how many seeds, how many "
    "candidates, which seed found the most), and that you are ready to start building the "
    "taxonomy. Then begin the interview. Draft the prompt from the seeds and the best "
    "matches as the answers come in."
)
UPDATE_INSTRUCTIONS = (
    "Reply in one or two sentences: what changed and whether it affects the conversation "
    "so far. Then continue where you left off."
)
TRANSCRIPT_TURNS = 40
TOOL_ARGS_CHARS = 80
MODE_WORDS = {"single": "one label", "multi": "several labels"}
META = "chat/taxonomy.meta.json"
EMPTY_LABELS = "No labels yet. The assistant will propose them as you talk."
EMPTY_PROMPT = (
    "No prompt yet. The assistant writes the first draft once the labels are set."
)


# ---- the context turn ---------------------------------------------------------------


def brief_transcript(messages: list[ModelMessage]) -> list[str]:
    """The brief conversation as lines: user and assistant text, one line per tool call, last 40 turns."""
    lines = []
    for message in messages:
        if isinstance(message, ModelRequest) and (message.metadata or {}).get(
            "hunches"
        ):
            continue  # the screen's own edit lines are not conversation
        for part in message.parts:
            if isinstance(part, UserPromptPart):
                lines.append(f"user: {part.content}")
            elif isinstance(part, TextPart):
                lines.append(f"assistant: {part.content}")
            elif isinstance(part, ToolCallPart):
                args = json.dumps(part.args_as_dict(), ensure_ascii=False)
                if len(args) > TOOL_ARGS_CHARS:
                    args = args[:TOOL_ARGS_CHARS] + "…"
                lines.append(f"tool: {part.tool_name} {args}")
    if len(lines) > TRANSCRIPT_TURNS:
        lines = [f"… {len(lines) - TRANSCRIPT_TURNS} more", *lines[-TRANSCRIPT_TURNS:]]
    return lines


def snapshot(seeds: list[str], rows: list[dict]) -> dict:
    """What a context turn told the agent: the seeds, the candidate count and the items won per seed."""
    return {
        "seeds": seeds,
        "n_candidates": len(rows),
        "items_won": dict(Counter(r["best_seed"] for r in rows)),
    }


def context_digest(seeds: list[str], candidates_text: str) -> str:
    return hashlib.sha256(json.dumps([seeds, candidates_text]).encode()).hexdigest()


def won_lines(snap: dict) -> str:
    won = snap["items_won"]
    # seeds removed since the search still own some candidates: list them after the current seeds
    names = [*snap["seeds"], *sorted(set(won) - set(snap["seeds"]))]
    return "\n".join(f"{won.get(name, 0):>6,}  {name}" for name in names)


def initial_context(transcript: list[str], seeds: list[str], rows: list[dict]) -> str:
    counts = candidates.band_counts(rows)
    bands = []
    for i, edge in enumerate(candidates.BANDS):
        last = i == len(candidates.BANDS) - 1
        name = f"{edge:g}+" if last else f"{edge:g}-{candidates.BANDS[i + 1]:g}"
        bands.append(f"{name}: {counts[i]:,}")
    return "\n".join(
        [
            "# Brief conversation",
            *transcript,
            "",
            "# Seeds and results (items won)",
            won_lines(snapshot(seeds, rows)),
            "",
            "# Search",
            f"{sum(counts):,} candidates at or above {candidates.FLOOR:.2f}",
            " · ".join(bands),
            "",
            "# Instructions",
            CONTEXT_INSTRUCTIONS,
        ]
    )


def context_summary(seeds: list[str], rows: list[dict]) -> str:
    return f"Context · {len(seeds)} seeds · {len(rows):,} candidates"


def update_context(old: dict, new: dict) -> str:
    added = [s for s in new["seeds"] if s not in old["seeds"]]
    removed = [s for s in old["seeds"] if s not in new["seeds"]]
    counts = [
        f"{len(added)} added" if added else "",
        f"{len(removed)} removed" if removed else "",
    ]
    lines = ["# What changed"]
    if added or removed:
        lines.append("seeds: " + ", ".join(c for c in counts if c))
        lines += [f"  + {s}" for s in added] + [f"  - {s}" for s in removed]
    before, after = old["n_candidates"], new["n_candidates"]
    lines.append(
        f"candidates: {before:,} → {after:,}"
        if before != after
        else f"candidates: {after:,} (unchanged)"
    )
    return "\n".join(
        [
            *lines,
            "",
            "# Seeds and results (items won)",
            won_lines(new),
            "",
            "# Instructions",
            UPDATE_INSTRUCTIONS,
        ]
    )


def update_summary(old: dict, new: dict) -> str:
    what = "Seeds changed" if old["seeds"] != new["seeds"] else "Search changed"
    delta = new["n_candidates"] - old["n_candidates"]
    return f"{what} · {new['n_candidates']:,} candidates ({delta:+,})"


def read_meta() -> dict | None:
    text = files.read_text(META)
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def write_meta(digest: str, snap: dict) -> None:
    meta = {"context_digest": digest, "sent_at": datetime.now(UTC).isoformat(), **snap}
    path = files.root() / META
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta))


# ---- taxonomy text and edit records -------------------------------------------------


def taxonomy_text(mode: str, labels: list[tuple[str, str]]) -> str:
    return f"mode: {mode}\nlabels:\n" + "\n".join(
        f"  - {name}: {desc}" if desc else f"  - {name}" for name, desc in labels
    )


def labels_problem(
    mode: str | None, rows: list[list[str]]
) -> tuple[str | None, set[int]]:
    """Why a labels draft cannot be saved (None if it can), and the indexes of the offending rows."""
    names = [name.strip() for name, _ in rows]
    if not rows:
        return "at least one label is required", set()
    if mode is None:
        return "choose a mode: one label or several labels per item", set()
    if blank := {i for i, n in enumerate(names) if not n}:
        return "label names cannot be blank", blank
    if dup := {i for i, n in enumerate(names) if names.index(n) != i}:
        return f"duplicate label name: {names[min(dup)]}", dup
    try:
        files.Taxonomy.model_validate(
            {
                "mode": mode,
                "labels": [
                    {"name": n, "description": d} for n, (_, d) in zip(names, rows)
                ],
            }
        )
    except ValidationError as e:
        message = e.errors()[0]["msg"].removeprefix("Value error, ")
        return message, {i for i, n in enumerate(names) if n == files.OFF_TOPIC}
    return None, set()


def labels_change(
    old: files.Taxonomy | None, new: files.Taxonomy
) -> tuple[str, str] | None:
    """(summary, detail) of the label names and descriptions that changed; None if they did not."""
    was = {label.name: label.description for label in old.labels} if old else {}
    now = {label.name: label.description for label in new.labels}
    edited = [n for n in now if n in was and now[n] != was[n]]
    added = [n for n in now if n not in was]
    deleted = [n for n in was if n not in now]
    if not (edited or added or deleted):
        return None
    summary = ", ".join(
        [f"{n} description" for n in edited]
        + [f"+{n}" for n in added]
        + [f"-{n}" for n in deleted]
    )
    counts = ", ".join(
        f"{len(group)} {word}"
        for group, word in ((edited, "edited"), (added, "added"), (deleted, "deleted"))
        if group
    )
    lines = [f"labels: {counts}"]
    for n in edited:
        lines += [f"  ~ {n}", f"    was: {was[n]}", f"    now: {now[n]}"]
    for n in added:
        lines += [f"  + {n}"] + ([f"    {now[n]}"] if now[n] else [])
    lines += [f"  - {n}" for n in deleted]
    return f"Labels: {summary}", "\n".join(lines)


def prompt_change(old: str, new: str) -> tuple[str, str]:
    """(summary, unified diff without file headers) of a prompt edit."""
    diff = [
        line
        for line in difflib.unified_diff(
            old.splitlines(), new.splitlines(), lineterm="", n=1
        )
        if not line.startswith(("---", "+++"))
    ]
    adds = sum(line.startswith("+") for line in diff)
    dels = sum(line.startswith("-") for line in diff)
    n = max(adds, dels)
    return f"Prompt: {n} line{'' if n == 1 else 's'} changed", "\n".join(diff)


def pad(name: str) -> str:
    """Spaces after a label tag (square, space, name) so the descriptions line up."""
    return " " * max(2, 18 - len(name) - 2)


def badge(text: str, tone: str = "warning") -> str:
    return f"[b reverse ${tone}] {text} [/]"


class LabelEditRow(Horizontal):
    """One label in the Labels editor: name, description, delete."""

    def __init__(self, entry: list[str]) -> None:
        super().__init__(classes="label-edit-row")
        self.entry = entry  # the screen's draft entry [name, description]; a row of a rebuilt list shares it

    def compose(self) -> ComposeResult:
        yield Input(self.entry[0], placeholder="name", classes="label-name")
        yield Input(self.entry[1], placeholder="description", classes="label-desc")
        yield Button("✕", classes="label-delete")


def version_question(n: int) -> str:
    return (
        "Gold labels were made with the current labels. Saving starts a new taxonomy version: "
        "dev and test labelling restart on the same items (your current labels, prompt and "
        f"results are kept as version {n} and can be restored). Continue?"
    )


class VersionsScreen(ModalScreen[int | None]):
    """The archived taxonomy versions; dismisses with the number to restore, or None."""

    BINDINGS: ClassVar = [("escape", "close", "Close")]
    DEFAULT_CSS = """
    VersionsScreen > Vertical { width: 76; height: auto; max-height: 90%; }
    VersionsScreen VerticalScroll { height: auto; max-height: 14; }
    VersionsScreen .version-row { height: auto; }
    VersionsScreen .version-text { width: 1fr; }
    VersionsScreen .version-row Button { margin-left: 1; }
    """

    def compose(self) -> ComposeResult:
        with modal_box(Vertical(), "Taxonomy versions"):
            with VerticalScroll():
                for v in files.list_versions():
                    names = ", ".join(v["labels"])
                    with Horizontal(classes="version-row"):
                        yield Static(
                            f"[b]version {v['version']}[/]  {v['created_at'][:10]}  "
                            f"{v['mode']}  {escape(names)}\n"
                            f"[$text-muted]labelled: dev {v['dev_labelled']} · "
                            f"test {v['test_labelled']}[/]",
                            classes="version-text",
                        )
                        yield Button("Restore", id=f"restore-{v['version']}")
            with Horizontal(classes="buttons"):
                yield key_button("Close", "Esc", id="close")

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        self.dismiss(
            int(button_id.removeprefix("restore-"))
            if button_id.startswith("restore-")
            else None
        )


class TaxonomyScreen(Screen):
    BINDINGS: ClassVar = [
        ("e", "edit", "Edit"),
        ("m", "mode", "Mode"),
        ("f2", "approve", "Approve"),
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "discard", "Discard"),
        Binding("a", "add_label", "Add label", show=False),
    ]
    DEFAULT_CSS = """
    TaxonomyScreen Horizontal#main { height: 1fr; }
    TaxonomyScreen ChatPanel { width: 1fr; }
    TaxonomyScreen #panes { width: 1fr; }
    TaxonomyScreen #labels-panel { height: auto; max-height: 60%; }
    TaxonomyScreen #labels-panel.-editing { height: 1fr; max-height: 100%; }
    TaxonomyScreen #prompt-panel { height: 1fr; }
    TaxonomyScreen #mode-row { height: 1; }
    TaxonomyScreen #mode-row Static { width: 7; color: $text-muted; }
    TaxonomyScreen #mode { width: 28; }
    TaxonomyScreen #labels-body { height: auto; max-height: 10; }
    TaxonomyScreen .-editing #labels-body { height: 1fr; max-height: 100%; }
    TaxonomyScreen .label-row-view { height: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    TaxonomyScreen .empty { height: 1fr; color: $text-muted; content-align: center middle; text-align: center; }
    TaxonomyScreen .label-edit-row { height: 1; border-left: outer $surface; }
    TaxonomyScreen .label-edit-row.-bad { border-left: outer $error; }
    TaxonomyScreen .label-name { width: 16; margin-right: 1; }
    TaxonomyScreen .label-desc { width: 1fr; margin-right: 1; }
    TaxonomyScreen .label-delete { width: 3; }
    TaxonomyScreen .buttons-row { height: auto; }
    TaxonomyScreen .buttons-row Button { margin-right: 1; }
    TaxonomyScreen .edit-error { width: 1fr; height: auto; color: $error; }
    TaxonomyScreen #prompt-scroll { height: 1fr; }
    TaxonomyScreen #prompt-text { height: 1fr; border: none; padding: 0; }
    TaxonomyScreen #approve-row { height: 1; margin-top: 1; align-horizontal: center; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.taxonomy: files.Taxonomy | None = None
        try:
            self.taxonomy = files.read_taxonomy()
        except (OSError, ValidationError, yaml.YAMLError, TypeError):
            pass
        self.prompt = files.read_text("prompt.md") or ""
        self.edit: Literal["labels", "prompt"] | None = None
        self.draft_mode: str | None = None
        self.draft: list[list[str]] = []  # [name, description] per label
        self.updated: set[str] = set()  # panels the assistant has just written
        config = files.read_config()
        self.agent = Agent(
            config.assistant_model,
            instructions=INSTRUCTIONS,
            model_settings=files.thinking_settings(config),
            defer_model_check=True,
        )

        @self.agent.instructions
        def current_state() -> str:
            mode = self.mode
            labels = (
                [(x.name, x.description) for x in self.taxonomy.labels]
                if self.taxonomy
                else []
            )
            text = "# Current seeds\n" + (
                numbered(candidates.read_seeds()) or "None yet."
            )
            text += "\n\n# Current taxonomy\n" + (
                taxonomy_text(self.taxonomy.mode, labels)
                if self.taxonomy
                else "None yet."
            )
            text += "\n\n# Current prompt\n" + (self.prompt or "None yet.")
            if mode:
                text += f"\n\nThe user chose mode {mode}; do not ask about it again."
            return text

        @self.agent.tool_plain
        async def write_taxonomy(
            mode: Literal["single", "multi"], labels: list[files.Label]
        ) -> str:
            """Write taxonomy.yaml. Do not list off_topic; it is built in."""
            if self.edit == "labels":
                return "Not written: the user is editing the taxonomy. Ask them to save or discard first."
            try:
                taxonomy = files.Taxonomy(mode=mode, labels=labels)
            except ValidationError as e:
                return f"Rejected, nothing written: {e}"
            if not labels:
                return "Rejected, nothing written: at least one label is required"
            versioned = self.needs_version(taxonomy)
            if versioned:
                n = len(files.list_versions()) + 1
                if not await self.app.push_screen_wait(
                    ConfirmScreen(version_question(n))
                ):
                    return "Not written: the user declined starting a new taxonomy version."
                if (
                    self.edit == "labels"
                ):  # the user began editing while the question was open
                    return "Not written: the user is editing the taxonomy. Ask them to save or discard first."
            self.commit_taxonomy(taxonomy, by_user=False)
            self.updated.add("labels")
            self.show_labels()
            self.sync()
            if versioned:
                return f"Written as version {n + 1}; gold labels were cleared and will need relabelling."
            return "Taxonomy written."

        @self.agent.tool_plain
        async def write_prompt(prompt: str) -> str:
            """Write prompt.md, the classifier prompt."""
            if self.edit == "prompt":
                return "Not written: the user is editing the prompt. Ask them to save or discard first."
            history.save("prompt", prompt, "assistant", "Prompt written by assistant")
            self.prompt = prompt
            self.updated.add("prompt")
            self.show_prompt()
            self.sync()
            return "Prompt written."

    @property
    def mode(self) -> str | None:
        """The mode the user has chosen: the draft's while the labels are being edited, else the file's."""
        if self.edit == "labels":
            return self.draft_mode
        return self.taxonomy.mode if self.taxonomy else None

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        with Horizontal(id="main"):
            yield ChatPanel("taxonomy", self.agent)
            with Vertical(id="panes"):
                with panel(Vertical(id="labels-panel"), "Labels"):
                    with Horizontal(id="mode-row"):
                        yield Static("mode")
                        yield Select(
                            [
                                ("One label per item", "single"),
                                ("Several labels per item", "multi"),
                            ],
                            prompt="Choose…",
                            id="mode",
                            compact=True,
                        )
                    yield VerticalScroll(id="labels-body")
                    yield Static(EMPTY_LABELS, id="empty-labels", classes="empty")
                    with Horizontal(id="labels-view-buttons", classes="buttons-row"):
                        yield key_button("Edit labels", "e", id="edit-labels")
                        yield Button("Versions", id="versions")
                    with Vertical(id="labels-edit-buttons"):
                        with Horizontal(classes="buttons-row"):
                            yield key_button("Add label", "a", id="add-label")
                        with Horizontal(classes="buttons-row"):
                            yield key_button(
                                "Save", "^s", id="save-labels", variant="success"
                            )
                            yield key_button("Discard", "Esc", id="discard-labels")
                            yield Static("", id="labels-error", classes="edit-error")
                with panel(Vertical(id="prompt-panel"), "Prompt"):
                    with VerticalScroll(id="prompt-scroll"):
                        yield Markdown("", id="prompt-view")
                    yield Static(EMPTY_PROMPT, id="empty-prompt", classes="empty")
                    with Horizontal(id="prompt-view-buttons", classes="buttons-row"):
                        yield key_button("Edit prompt", "e", id="edit-prompt")
                    with Horizontal(id="prompt-edit-buttons", classes="buttons-row"):
                        yield key_button(
                            "Save", "^s", id="save-prompt", variant="success"
                        )
                        yield key_button("Discard", "Esc", id="discard-prompt")
                yield Static("", id="note", classes="note")
                with Horizontal(id="approve-row"):
                    yield key_button(
                        "Approve taxonomy and prompt",
                        "F2",
                        id="approve",
                        variant="success",
                    )
        yield AppFooter()

    def on_mount(self) -> None:
        say(self.query_one("#note", Static), "")
        self.show_labels()
        self.show_prompt()
        self.sync()
        self.run_worker(self.sync_context())

    # ---- the context turn

    async def sync_context(self) -> None:
        """Send the initial context, or an UPDATED one when seeds or candidates changed since the last."""
        chat = self.query_one(ChatPanel)
        seeds = candidates.read_seeds()
        rows = files.read_jsonl("candidates.jsonl")
        if not seeds or not rows:
            return
        digest = context_digest(seeds, files.read_text("candidates.jsonl") or "")
        new = snapshot(seeds, rows)
        old = read_meta()
        if chat.history and old and old.get("context_digest") == digest:
            return
        if chat.history and old:
            kind, body, summary = (
                "update",
                update_context(old, new),
                update_summary(old, new),
            )
        else:
            transcript = brief_transcript(files.load_chat("brief"))
            kind = "context"
            body, summary = (
                initial_context(transcript, seeds, rows),
                context_summary(seeds, rows),
            )
        sent = len(chat.history)
        await chat.send_context(body, kind, summary)
        if (
            len(chat.history) > sent
        ):  # a failed turn leaves the history alone and must not claim to be sent
            write_meta(digest, new)

    # ---- state to widgets

    def labels_dirty(self) -> bool:
        was_mode = self.taxonomy.mode if self.taxonomy else None
        was = (
            [[x.name, x.description] for x in self.taxonomy.labels]
            if self.taxonomy
            else []
        )
        return (self.draft_mode, self.draft) != (was_mode, was)

    def prompt_dirty(self) -> bool:
        areas = self.query("#prompt-text")
        return bool(areas) and areas.first(TextArea).text != self.prompt

    def can_approve(self) -> bool:
        return bool(
            self.edit is None
            and self.taxonomy
            and self.taxonomy.labels
            and self.prompt.strip()
        )

    def show_labels(self) -> None:
        """Rebuild the label rows (read or edit) for the current state."""
        body = self.query_one("#labels-body", VerticalScroll)
        body.remove_children()
        if self.edit == "labels":
            body.mount(*(LabelEditRow(entry) for entry in self.draft))
        elif self.taxonomy:
            names = [x.name for x in self.taxonomy.labels]
            rows = [
                Static(
                    f"{label_tag(names, x.name)}{pad(x.name)}[$text-muted]{escape(x.description)}[/]",
                    classes="label-row-view",
                )
                for x in self.taxonomy.labels
            ]
            rows.append(
                Static(
                    f"{label_tag(names, files.OFF_TOPIC)}{pad(files.OFF_TOPIC)}[$text-disabled]built in · matches none of the labels[/]",
                    classes="label-row-view",
                )
            )
            body.mount(*rows)
        select = self.query_one("#mode", Select)
        mode = self.mode
        if mode is None and not select.is_blank():
            select.clear()
        elif mode is not None and select.value != mode:
            select.value = mode

    def show_prompt(self) -> None:
        self.query_one("#prompt-view", Markdown).update(self.prompt)
        if self.edit != "prompt":
            self.query("#prompt-text").remove()

    def sync(self) -> None:
        """Titles, badges, buttons and the disabled panels for the current state."""
        editing = self.edit
        labels, prompt = editing == "labels", editing == "prompt"
        has_labels = self.taxonomy is not None or labels
        self.query_one("#labels-body").display = has_labels
        self.query_one("#empty-labels").display = not has_labels
        self.query_one("#labels-view-buttons").display = not labels
        self.query_one("#labels-edit-buttons").display = labels
        has_prompt = bool(self.prompt) or prompt
        self.query_one("#prompt-scroll").display = bool(self.prompt) and not prompt
        self.query_one("#empty-prompt").display = not has_prompt
        self.query_one("#prompt-view-buttons").display = not prompt
        self.query_one("#prompt-edit-buttons").display = prompt
        self.query_one("#labels-panel").set_class(labels, "-editing")
        self.query_one("#labels-panel").disabled = prompt
        self.query_one("#prompt-panel").disabled = labels
        problem, bad = (
            labels_problem(self.draft_mode, self.draft) if labels else (None, set())
        )
        error = self.query_one("#labels-error", Static)
        error.update(problem or "")
        error.display = bool(problem)
        for row in self.query(LabelEditRow):
            row.set_class(any(e is row.entry for e in self.draft_at(bad)), "-bad")
        self.query_one("#save-labels", Button).disabled = (
            bool(problem) or not self.labels_dirty()
        )
        self.query_one("#save-prompt", Button).disabled = not self.prompt_dirty()
        self.query_one("#approve", Button).disabled = not self.can_approve()
        t = self.taxonomy
        n = len(t.labels) if t else 0
        if labels:
            sub = badge("UNSAVED" if self.labels_dirty() else "EDITING")
        elif "labels" in self.updated:
            sub = badge("UPDATED BY ASSISTANT", "secondary")
        else:
            sub = f"{t.mode} · {n} label{'' if n == 1 else 's'}" if t else ""
            sub += f" · version {len(files.list_versions()) + 1}" if t else ""
        retitle(self.query_one("#labels-panel"), subtitle=sub)
        self.query_one("#versions", Button).disabled = not files.version_numbers()
        if prompt:
            sub = badge("UNSAVED" if self.prompt_dirty() else "EDITING")
        elif "prompt" in self.updated:
            sub = badge("UPDATED BY ASSISTANT", "secondary")
        else:
            sub = "classifier prompt" if self.prompt else ""
        retitle(self.query_one("#prompt-panel"), subtitle=sub)
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ("save", "discard"):
            return self.edit is not None
        if action == "add_label":
            return self.edit == "labels"
        if action in ("edit", "mode", "approve"):
            return self.edit is None
        return True

    # ---- labels

    def start_labels(self, mode: str | None = None) -> None:
        t = self.taxonomy
        self.edit = "labels"
        self.draft_mode = mode or (t.mode if t else None)
        self.draft = [[x.name, x.description] for x in t.labels] if t else []
        self.updated.discard("labels")
        self.show_labels()
        self.sync()
        self.focus_labels()

    def focus_labels(self, last: bool = False) -> None:
        def focus() -> None:
            inputs = self.query(".label-name")
            if inputs:
                (inputs.last() if last else inputs.first()).focus()
            else:
                self.query_one("#add-label").focus()

        self.call_after_refresh(focus)

    def end_edit(self, button: str) -> None:
        self.edit = None
        self.show_labels()
        self.show_prompt()
        self.sync()
        self.call_after_refresh(self.query_one(button).focus)

    def action_add_label(self) -> None:
        if self.edit == "labels":
            self.draft.append(["", ""])
            self.show_labels()
            self.sync()
            self.focus_labels(last=True)

    def action_mode(self) -> None:
        select = self.query_one("#mode", Select)
        select.focus()
        select.action_show_overlay()

    def on_select_changed(self, event: Select.Changed) -> None:
        value = event.value
        if event.select.id != "mode" or value is Select.NULL or value == self.mode:
            return
        if self.edit == "prompt":
            self.show_labels()  # put the select back
            return
        if self.edit == "labels":
            self.draft_mode = str(value)
            self.sync()
        else:
            self.start_labels(mode=str(value))

    def draft_at(self, indexes: set[int]) -> list[list[str]]:
        return [entry for i, entry in enumerate(self.draft) if i in indexes]

    def on_input_changed(self, event: Input.Changed) -> None:
        row = event.input.parent
        if self.edit == "labels" and isinstance(row, LabelEditRow):
            row.entry[event.input.has_class("label-desc")] = event.value
            self.sync()

    def commit_taxonomy(self, new: files.Taxonomy, by_user: bool = True) -> None:
        """The one place a taxonomy is written: the Labels Save and the agent's tool both come here."""
        old = self.taxonomy
        if self.needs_version(
            new
        ):  # the callers have asked the user (version_question)
            archived = history.start_new_version(
                new,
                f"Taxonomy version {len(files.list_versions()) + 2} started",
                "user" if by_user else "assistant",
            )
            self.taxonomy = new
            if by_user:
                summary = f"Taxonomy version {archived + 1} started"
                detail = labels_change(old, new)
                current = "# Current taxonomy\n" + taxonomy_text(
                    new.mode, [(x.name, x.description) for x in new.labels]
                )
                self.query_one(ChatPanel).record(
                    summary,
                    f"Taxonomy version {archived + 1} started: label set/mode changed; gold labels "
                    f"cleared on the same items; version {archived} archived\n"
                    + (f"{detail[1]}\n" if detail else "")
                    + f"\n{current}",
                )
            say(
                self.query_one("#note", Static),
                f"Version {archived} archived. Approve to relabel the dev set.",
            )
            return
        mode = old and old.mode != new.mode
        change = labels_change(old, new)
        summary = (
            f"Mode: {MODE_WORDS[old.mode]} → {MODE_WORDS[new.mode]}"
            if mode
            else change[0]
            if change
            else "Taxonomy written"
        )
        history.save(
            "taxonomy",
            files.taxonomy_yaml(new),
            "user" if by_user else "assistant",
            summary,
        )
        self.taxonomy = new
        if by_user:
            self.record_taxonomy(old, new)

    def needs_version(self, new: files.Taxonomy) -> bool:
        """Saving `new` would invalidate labelled gold rows: it needs a new taxonomy version."""
        old = self.taxonomy
        return bool(old and files.taxonomy_in_use() and files.labels_changed(old, new))

    def record_taxonomy(self, old: files.Taxonomy | None, new: files.Taxonomy) -> None:
        chat = self.query_one(ChatPanel)
        current = "# Current taxonomy\n" + taxonomy_text(
            new.mode, [(x.name, x.description) for x in new.labels]
        )
        if old and old.mode != new.mode:
            chat.record(
                f"Mode: {MODE_WORDS[old.mode]} → {MODE_WORDS[new.mode]}",
                f"mode: {old.mode} → {new.mode}\n\n{current}",
            )
        if change := labels_change(old, new):
            chat.record(change[0], f"{change[1]}\n\n{current}")

    def save_labels(self) -> None:
        problem, _ = labels_problem(self.draft_mode, self.draft)
        if self.edit != "labels" or problem or not self.labels_dirty():
            return
        new = files.Taxonomy(
            mode=self.draft_mode,  # ty: ignore[invalid-argument-type]
            labels=[
                files.Label(name=n.strip(), description=d.strip())
                for n, d in self.draft
            ],
        )
        if self.needs_version(new):  # the draft stays open until the user decides

            def decided(yes: bool | None) -> None:
                if yes:
                    self.edit = None
                    self.commit_taxonomy(new)
                    self.end_edit("#edit-labels")

            self.app.push_screen(
                ConfirmScreen(version_question(len(files.list_versions()) + 1)), decided
            )
            return
        self.edit = None
        self.commit_taxonomy(new)
        self.end_edit("#edit-labels")

    # ---- versions

    def action_versions(self) -> None:
        if self.edit is not None or not files.version_numbers():
            return
        self.app.push_screen(VersionsScreen(), self.restore_chosen)

    def restore_chosen(self, n: int | None) -> None:
        if n is None or self.edit is not None:
            return
        made = len(files.list_versions()) + 1

        def decided(yes: bool | None) -> None:
            if yes:
                self.restore(n, made)

        self.app.push_screen(
            ConfirmScreen(
                f"Restore taxonomy version {n}? The current state is archived first as version "
                f"{made}, so nothing is lost."
            ),
            decided,
        )

    def restore(self, n: int, made: int) -> None:
        history.restore_version(n, f"Restored taxonomy version {n}")
        self.taxonomy = None
        try:
            self.taxonomy = files.read_taxonomy()
        except (OSError, ValidationError, yaml.YAMLError, TypeError):
            pass
        self.prompt = files.read_text("prompt.md") or ""
        self.updated.clear()
        self.show_labels()
        self.show_prompt()
        self.sync()
        current = "# Current taxonomy\n" + (
            taxonomy_text(
                self.taxonomy.mode,
                [(x.name, x.description) for x in self.taxonomy.labels],
            )
            if self.taxonomy
            else "None yet."
        )
        self.query_one(ChatPanel).record(
            f"Restored taxonomy version {n}",
            f"Restored taxonomy version {n}; the previous state is archived as version {made}\n\n"
            f"{current}\n\n# Current prompt\n{self.prompt or 'None yet.'}",
        )
        say(
            self.query_one("#note", Static),
            f"Restored version {n}; the previous state is version {made}.",
        )

    # ---- prompt

    def start_prompt(self) -> None:
        self.edit = "prompt"
        self.updated.discard("prompt")
        area = editor(
            TextArea(
                self.prompt,
                language="markdown",
                show_line_numbers=True,
                id="prompt-text",
            )
        )
        self.query_one("#prompt-panel").mount(area, before="#prompt-edit-buttons")
        self.sync()
        self.call_after_refresh(area.focus)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.sync()  # only the badge and Save: nothing is written until Save

    def save_prompt(self) -> None:
        if self.edit != "prompt" or not self.prompt_dirty():
            return
        new = self.query_one("#prompt-text", TextArea).text
        summary, diff = prompt_change(self.prompt, new)
        history.save("prompt", new, "user", summary)
        self.prompt = new
        self.query_one(ChatPanel).record(summary, f"{diff}\n\n# Current prompt\n{new}")
        self.end_edit("#edit-prompt")

    # ---- keys and buttons

    def action_edit(self) -> None:
        if self.edit is not None:
            return
        focused = self.focused
        panel_ = self.query_one("#prompt-panel")
        if focused is not None and panel_ in focused.ancestors_with_self:
            self.start_prompt()
        else:
            self.start_labels()

    def action_save(self) -> None:
        if self.edit == "labels":
            self.save_labels()
        elif self.edit == "prompt":
            self.save_prompt()

    def action_discard(self) -> None:
        if self.edit is not None:
            button = "#edit-labels" if self.edit == "labels" else "#edit-prompt"
            self.end_edit(button)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button
        if button.has_class("label-delete"):
            row = button.parent
            if self.edit == "labels" and isinstance(row, LabelEditRow):
                self.draft = [e for e in self.draft if e is not row.entry]
                self.show_labels()
                self.sync()
                self.focus_labels()
            return
        action = {
            "edit-labels": self.start_labels,
            "add-label": self.action_add_label,
            "save-labels": self.save_labels,
            "discard-labels": self.action_discard,
            "edit-prompt": self.start_prompt,
            "save-prompt": self.save_prompt,
            "discard-prompt": self.action_discard,
            "approve": self.action_approve,
            "versions": self.action_versions,
        }.get(button.id or "")
        if action:
            action()

    def on_chat_panel_submitted(self, event: ChatPanel.Submitted) -> None:
        self.updated.clear()  # the next agent turn starts
        self.sync()

    def on_descendant_focus(self, event: DescendantFocus) -> None:
        for name in ("labels", "prompt"):
            if (
                name in self.updated
                and self.query_one(f"#{name}-panel") in event.widget.ancestors_with_self
            ):
                self.updated.discard(name)  # the user is back at it
                self.sync()

    def action_approve(self) -> None:
        if not self.can_approve():
            return
        taxonomy = self.taxonomy
        assert taxonomy is not None

        def save_target() -> None:
            # the spec default depends on mode; the user can change it later in the TUI
            config = files.read_config()
            config.target_metric = metrics.default_target_metric(taxonomy)  # ty: ignore[invalid-assignment]
            files.write_config(config)
            self.app.goto_stage(4)  # ty: ignore[unresolved-attribute]

        confirm_approve(
            self,
            "taxonomy_approved",
            3,
            f"Approve taxonomy ({taxonomy.mode}, {len(taxonomy.labels)} labels) and prompt, and start labelling?",
            f"Approved: Taxonomy and prompt ({taxonomy.mode}, {len(taxonomy.labels)} labels)",
            then=save_target,
        )
