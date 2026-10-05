"""System settings: first-run setup and later edits, plus the recommendation-changed modal."""

import typing

from pydantic_ai.settings import ThinkingEffort
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.markup import escape
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Input, Label, Select, Static

from hunches import keys, models, system
from hunches.app import StatusHeader, modal_box, panel
from hunches.screens.model_picker import ModelPicker

# What the thinking Select offers: exactly the values files.Config accepts, plus "default" (None)
EFFORTS = typing.get_args(ThinkingEffort)
NAMES = {"ANTHROPIC_API_KEY": "Anthropic", "OPENAI_API_KEY": "OpenAI"}


def saved_stores() -> list[system.Store]:
    current = system.read_system()
    return current.s3_stores if current else []


class SystemSettingsScreen(Screen[bool]):
    """Dismisses True when saved, False when cancelled (never on first run)."""

    DEFAULT_CSS = """
    SystemSettingsScreen > VerticalScroll { height: 1fr; }
    SystemSettingsScreen .panel { height: auto; }
    SystemSettingsScreen #title { text-style: bold; }
    SystemSettingsScreen .row { height: auto; }
    SystemSettingsScreen .row Label { width: 11; color: $text-muted; }
    SystemSettingsScreen .row Static { width: 1fr; }
    SystemSettingsScreen .row Input { width: 1fr; border: none; }
    SystemSettingsScreen .row Button { margin-left: 1; width: auto; min-width: 8; }
    SystemSettingsScreen #status-ANTHROPIC_API_KEY, SystemSettingsScreen #status-OPENAI_API_KEY { width: 9; }
    SystemSettingsScreen .row Select { width: 1fr; }
    SystemSettingsScreen #storelist { height: auto; }
    SystemSettingsScreen #actions { height: 1; }
    SystemSettingsScreen #actions Button { margin-right: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.current = system.read_system()
        self.edited = False  # the user changed a model or thinking by hand
        if self.current:
            self.provider = self.current.provider
            self.assistant = self.current.assistant_model
            self.thinking = self.current.assistant_thinking
            self.classifier = self.current.classifier_model
        else:
            # the provider that has a key; Anthropic if both (or neither)
            have = [v for v in keys.VARS if keys.status(v) != "missing"]
            self.provider = "openai" if have == ["OPENAI_API_KEY"] else "anthropic"
            self.fill_recommended()

    def fill_recommended(self) -> None:
        rec = system.RECOMMENDED[self.provider]
        self.assistant = str(rec["assistant"])
        self.thinking = rec["thinking"]
        self.classifier = str(rec["classifier"])

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        with VerticalScroll():
            yield Static(
                "Settings" if self.current else "Welcome — set up hunches", id="title"
            )
            with panel(Vertical(id="keys"), "API keys"):
                if not keys.available():
                    yield Static(
                        "WARNING: No system keyring available: set ANTHROPIC_API_KEY / "
                        "OPENAI_API_KEY in the environment or a git-ignored .env",
                        classes="warn",
                    )
                for var in keys.VARS:
                    with Horizontal(classes="row"):
                        yield Label(NAMES[var])
                        yield Static("", id=f"status-{var}")
                        if keys.available():
                            yield Input(
                                password=True,
                                placeholder="paste key",
                                id=f"key-{var}",
                                compact=True,
                            )
                            yield Button("Save", id=f"savekey-{var}", compact=True)
                            yield Button("Remove", id=f"removekey-{var}", compact=True)
            with Horizontal(classes="row"):
                yield Label("Provider")
                yield Select(
                    [("Anthropic", "anthropic"), ("OpenAI", "openai")],
                    value=self.provider,
                    allow_blank=False,
                    compact=True,
                    id="provider",
                )
            with panel(Vertical(id="models"), "Models"):
                with Horizontal(classes="row"):
                    yield Static("", id="assistant")
                    yield Button("Change", id="pick-assistant", compact=True)
                with Horizontal(classes="row"):
                    yield Label("thinking")
                    yield Select(
                        [("provider default", "default"), *((e, e) for e in EFFORTS)],
                        value=self.thinking or "default",
                        allow_blank=False,
                        compact=True,
                        id="thinking",
                    )
                with Horizontal(classes="row"):
                    yield Static("", id="classifier")
                    yield Button("Change", id="pick-classifier", compact=True)
                yield Static("", id="differs", classes="warn")
                yield Static("", id="pricewarn", classes="warn")
                yield Button("Reset to recommended", id="reset", compact=True)
            with panel(Vertical(id="stores"), "Saved S3 stores"):
                yield Vertical(id="storelist")
            yield Static(
                "Changes here apply to new projects. Existing projects keep their models.",
                classes="note",
            )
            yield Static(
                f"Prices from genai-prices as of {models.snapshot_date()}; "
                "the header shows actual spend.",
                classes="note",
            )
            yield Static("", id="error", classes="error")
        with Horizontal(id="actions"):
            yield Button("Save", id="save", variant="success", compact=True)
            if self.current:
                yield Button("Cancel", id="cancel", compact=True)
        yield Footer()

    async def on_mount(self) -> None:
        self.refresh_keys()
        self.refresh_models()
        self.show("#error", "")
        await self.refresh_stores()

    async def refresh_stores(self) -> None:
        """Stores are edited live (not on Save): they are not part of the models form."""
        stores = saved_stores()
        box = self.query_one("#storelist", Vertical)
        await box.remove_children()
        if not stores:
            await box.mount(
                Static(
                    "No saved stores. They are created from New project.",
                    classes="note",
                )
            )
        for i, store in enumerate(stores):
            region = f" {store.region}" if store.region else ""
            await box.mount(
                Horizontal(
                    Input(store.name, id=f"store-{i}", compact=True),
                    Static(
                        escape(f"{store.bucket}/{store.index}{region}"), classes="note"
                    ),
                    Button("Delete", id=f"delstore-{i}", compact=True),
                    classes="row",
                )
            )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        box_id = event.input.id or ""
        if not box_id.startswith("store-"):
            return
        old = saved_stores()[int(box_id.removeprefix("store-"))].name
        new = event.value.strip()
        try:
            if new and new != old:
                system.rename_store(old, new)
            self.show("#error", "")
        except ValueError as e:
            self.show("#error", f"ERROR: {escape(str(e))}")
        await self.refresh_stores()

    def refresh_models(self) -> None:
        for name, model in (
            ("assistant", self.assistant),
            ("classifier", self.classifier),
        ):
            self.query_one(f"#{name}", Static).update(
                f"{name}: {escape(model)}  [$text-muted]{models.price_label(model)}[/]"
            )
        rec = system.RECOMMENDED[self.provider]
        differs = (self.assistant, self.thinking, self.classifier) != (
            rec["assistant"],
            rec["thinking"],
            rec["classifier"],
        )
        self.show("#differs", "DIFFERS from recommended" if differs else "")
        unpriced = [
            m
            for m in (self.assistant, self.classifier)
            if models.price_label(m) == models.NO_PRICE
        ]
        self.show(
            "#pricewarn",
            f"WARNING: no price for {escape(', '.join(unpriced))}: cost will show ?"
            if unpriced
            else "",
        )

    def show(self, selector: str, text: str) -> None:
        """Set a message line; an empty one takes no room (80x24 is tight)."""
        line = self.query_one(selector, Static)
        line.update(text)
        line.display = bool(text)

    def pick(self, field: str) -> None:
        def done(model: str | None) -> None:
            if model:
                setattr(self, field, model)
                self.edited = True
                self.refresh_models()

        self.app.push_screen(ModelPicker(), done)

    def refresh_keys(self) -> None:
        for var in keys.VARS:
            self.query_one(f"#status-{var}", Static).update(keys.status(var).upper())

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "provider" and event.value != self.provider:
            self.provider = str(event.value)
            if not self.edited:
                self.fill_recommended()
                self.query_one("#thinking", Select).value = self.thinking or "default"
                self.refresh_models()
        elif event.select.id == "thinking":
            value = None if event.value == "default" else str(event.value)
            if value != self.thinking:
                self.thinking = value
                self.edited = True
                self.refresh_models()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id or ""
        if button.startswith("savekey-"):
            var = button.removeprefix("savekey-")
            box = self.query_one(f"#key-{var}", Input)
            if box.value:
                keys.save(var, box.value)
                box.value = ""
            self.refresh_keys()
        elif button.startswith("removekey-"):
            keys.remove(button.removeprefix("removekey-"))
            self.refresh_keys()
        elif button.startswith("delstore-"):
            system.delete_store(
                saved_stores()[int(button.removeprefix("delstore-"))].name
            )
            await self.refresh_stores()
        elif button in ("pick-assistant", "pick-classifier"):
            self.pick(button.removeprefix("pick-"))
        elif button == "reset":
            self.fill_recommended()
            self.edited = False
            self.query_one("#thinking", Select).value = self.thinking or "default"
            self.refresh_models()
        elif button == "cancel":
            self.dismiss(False)
        elif button == "save":
            self.save()

    def save(self) -> None:
        if all(keys.status(v) == "missing" for v in keys.VARS):
            self.show("#error", "ERROR: save at least one API key first")
            return
        # re-read: stores and projects are edited elsewhere while this screen is open
        base = system.read_system()
        fields = {
            "provider": self.provider,
            "assistant_model": self.assistant,
            "assistant_thinking": self.thinking,
            "classifier_model": self.classifier,
        }
        if base:
            new = base.model_copy(update=fields)
        else:
            new = system.System(
                **fields,  # ty: ignore[invalid-argument-type]
                recommendation_seen=system.RECOMMENDED_REVISION,
            )
        system.write_system(new)
        self.dismiss(True)


class RecommendationModal(ModalScreen[None]):
    """Shown when RECOMMENDED_REVISION is newer than the user's recommendation_seen."""

    DEFAULT_CSS = """
    RecommendationModal > Vertical {
        width: 100%; max-width: 78; height: auto; max-height: 100%;
    }
    """

    def __init__(self, current: system.System) -> None:
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        rec = system.RECOMMENDED[self.current.provider]
        old = (
            self.current.assistant_model,
            self.current.classifier_model,
        )
        new = (str(rec["assistant"]), str(rec["classifier"]))
        with modal_box(Vertical(id="modal-box"), "Recommended models changed"):
            for name, was, now in zip(("assistant", "classifier"), old, new):
                yield Static(
                    f"{name}: {escape(was)}  [$text-muted]{models.price_label(was)}[/]\n"
                    f"  -> {escape(now)}  [$text-muted]{models.price_label(now)}[/]"
                )
            yield Static(
                f"thinking: {self.current.assistant_thinking or 'provider default'}"
                f" -> {rec['thinking'] or 'provider default'}"
            )
            yield Static("Existing projects keep their models.", classes="note")
            with Horizontal(classes="buttons"):
                yield Button("Keep mine", id="keep-mine")
                yield Button("Use new", id="use-new", variant="success")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "use-new":
            system.use_new()
        elif event.button.id == "keep-mine":
            system.keep_mine()
        else:
            return
        event.stop()
        self.dismiss()
