"""Modal list of known models for every provider that has an API key, with prices, plus Other… for any string."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.markup import escape
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static

from hunches import keys, models
from hunches.app import modal_box
from hunches.models import NO_PRICE


class ModelPicker(ModalScreen[str | None]):
    DEFAULT_CSS = """
    ModelPicker > Vertical { width: 100%; max-width: 78; height: 100%; max-height: 22; }
    ModelPicker OptionList { height: 1fr; }
    ModelPicker #other { display: none; }
    ModelPicker #other.-shown { display: block; }
    """
    BINDINGS: ClassVar = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, embedding: bool = False) -> None:
        super().__init__()
        self.embedding = embedding
        self.rows = [
            row
            for provider in keys.providers()
            for row in models.model_rows(provider, embedding)
        ]

    def compose(self) -> ComposeResult:
        with modal_box(Vertical(), "Choose a model"):
            yield OptionList(
                *(self.option(r) for r in self.rows), "Other… (type any provider:model)"
            )
            yield Input(placeholder="provider:model", id="other")
            yield Static(
                "" if self.rows else "No API key set: add one in System settings (F5)",
                id="note",
                classes="warn",
            )

    @staticmethod
    def option(row: models.ModelRow) -> str:
        marks = (" ★ recommended" if row.recommended else "") + (
            " DEPRECATED" if row.deprecated else ""
        )
        price = (
            f"[$warning]{row.price}[/]"
            if row.price == NO_PRICE
            else f"[$text-muted]{row.price}[/]"
        )
        return f"{escape(row.model)}{marks}\n  {price}"

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index < len(self.rows):
            self.dismiss(self.rows[event.option_index].model)
        else:
            box = self.query_one("#other", Input)
            box.add_class("-shown")
            box.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        known = event.value in models.known_models(self.embedding)
        text = (
            ""
            if known or not event.value
            else "WARNING: not in known list (may still be valid)"
        )
        self.query_one("#note", Static).update(text)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip():
            self.dismiss(event.value.strip())
