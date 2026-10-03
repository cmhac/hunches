import random
from typing import ClassVar, Literal

import yaml
from pydantic import ValidationError
from pydantic_ai import Agent
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static, TextArea

from hunches import files, metrics
from hunches.app import ChatPanel, StatusHeader, confirm_approve, panel
from hunches.theme import editor

INSTRUCTIONS = """\
You define how items are classified, by interviewing the user and then writing two files.
Ask short questions, one or two at a time. You must find out:
1. whether there is one user label (binary: that label vs off_topic) or several labels (multi-class);
2. whether each item gets exactly one label (mode "single") or possibly several (mode "multi").
Then call write_taxonomy with the mode and labels (each with a short description), and \
write_prompt with the classifier prompt. "off_topic" is built in, always available and always \
exclusive: never list it as a label. If a tool returns an error, fix it and call it again.
The prompt must describe each label, describe the off_topic label (the item matches none of \
the labels), and, for mode "single", say that exactly one label is returned. For mode \
"multi", say that every label that applies is returned and that off_topic is never combined \
with another label. The prompt is the classifier's system prompt; it will be shown the item text.
"""


def build_instructions(sample_size: int = 10) -> str:
    """INSTRUCTIONS plus brief.md and a few random candidate texts, so the agent sees real data."""
    text = INSTRUCTIONS
    text += f"\nThe user's brief:\n{files.read_text('brief.md') or '(none yet)'}\n"
    rows = files.read_jsonl("candidates.jsonl")
    samples = random.sample(rows, min(sample_size, len(rows)))
    if samples:
        text += "\nSample candidate items:\n"
        text += "\n".join(f"- {r['text']}" for r in samples) + "\n"
    return text


class TaxonomyScreen(Screen):
    BINDINGS: ClassVar = [("f2", "approve", "Approve")]
    DEFAULT_CSS = """
    TaxonomyScreen Horizontal { height: 1fr; }
    TaxonomyScreen ChatPanel { width: 1fr; }
    TaxonomyScreen #panes { width: 1fr; }
    TaxonomyScreen #panes > .panel { height: 1fr; }
    TaxonomyScreen TextArea { height: 1fr; border: none; padding: 0; }
    TaxonomyScreen #status { height: auto; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.agent = Agent(
            files.read_config().smart_model,
            instructions=build_instructions(),
            defer_model_check=True,
        )

        @self.agent.tool_plain
        async def write_taxonomy(
            mode: Literal["single", "multi"], labels: list[files.Label]
        ) -> str:
            """Write taxonomy.yaml. Do not list off_topic; it is built in."""
            try:
                taxonomy = files.Taxonomy(mode=mode, labels=labels)
            except ValidationError as e:
                return f"Rejected, nothing written: {e}"
            if not labels:
                return "Rejected, nothing written: at least one label is required"
            files.write_taxonomy(taxonomy)
            self.query_one("#taxonomy", TextArea).text = (
                files.read_text("taxonomy.yaml") or ""
            )
            return "Taxonomy written."

        @self.agent.tool_plain
        async def write_prompt(prompt: str) -> str:
            """Write prompt.md, the classifier prompt."""
            files.write_text("prompt.md", prompt)
            self.query_one("#prompt", TextArea).text = prompt
            return "Prompt written."

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        with Horizontal():
            yield ChatPanel("taxonomy", self.agent)
            with Vertical(id="panes"):
                with panel(Vertical(id="taxonomy-panel"), "taxonomy.yaml (editable)"):
                    yield editor(
                        TextArea(
                            files.read_text("taxonomy.yaml") or "",
                            language="yaml",
                            id="taxonomy",
                        )
                    )
                with panel(Vertical(id="prompt-panel"), "prompt.md (editable)"):
                    yield editor(
                        TextArea(
                            files.read_text("prompt.md") or "",
                            language="markdown",
                            id="prompt",
                        )
                    )
        yield Static("", id="status", classes="warn")
        yield Footer()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        name = "taxonomy.yaml" if event.text_area.id == "taxonomy" else "prompt.md"
        text = event.text_area.text
        if text == (files.read_text(name) or ""):  # initial load or agent write
            return
        status = self.query_one("#status", Static)
        if name == "prompt.md":
            files.write_text(name, text)
            status.update("")
            return
        # a half-typed taxonomy must not overwrite the last valid file
        try:
            files.Taxonomy.model_validate(yaml.safe_load(text))
        except (ValidationError, yaml.YAMLError) as e:
            status.update(f"taxonomy.yaml not saved: {str(e).splitlines()[0]}")
            return
        files.write_text(name, text)
        status.update("")

    def action_approve(self) -> None:
        status = self.query_one("#status", Static)
        try:
            taxonomy = files.read_taxonomy()
        except (OSError, ValidationError, yaml.YAMLError, TypeError) as e:
            status.update(f"Cannot approve: no valid taxonomy.yaml ({e})")
            return
        if not taxonomy.labels or not (files.read_text("prompt.md") or "").strip():
            status.update("Cannot approve: need at least one label and a prompt.")
            return

        def save_target() -> None:
            # the spec default depends on mode; the user can change it later in the TUI
            config = files.read_config()
            config.target_metric = metrics.default_target_metric(taxonomy)  # ty: ignore[invalid-assignment]
            files.write_config(config)
            self.app.goto_stage(4)  # ty: ignore[unresolved-attribute]

        confirm_approve(
            self,
            "taxonomy_approved",
            f"Approve taxonomy ({taxonomy.mode}, {len(taxonomy.labels)} labels) and prompt?",
            then=save_target,
        )
