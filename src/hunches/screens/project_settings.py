"""Project settings: edit the current project's .hunches/config.toml."""

import typing
from pathlib import Path

from pydantic_ai.settings import ThinkingEffort
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.markup import escape
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Select, Static

from hunches import files, models, system
from hunches.app import AppFooter, ConfirmScreen, StatusHeader, panel
from hunches.screens.model_picker import ModelPicker
from hunches.screens.new_project import (
    NewProjectScreen,
    check_corpus,
    check_index,
    stored_corpus,
)
from hunches.screens.paths import PathInput, browse
from hunches.screens.system import saved_stores

EFFORTS = typing.get_args(ThinkingEffort)


class ProjectSettingsScreen(Screen):
    stage_name = "Settings"
    DEFAULT_CSS = """
    ProjectSettingsScreen > VerticalScroll { height: 1fr; }
    ProjectSettingsScreen .panel { height: auto; }
    ProjectSettingsScreen .row { height: auto; }
    ProjectSettingsScreen .row Static { width: 1fr; }
    ProjectSettingsScreen .row Label { width: 11; color: $text-muted; }
    ProjectSettingsScreen .row Input, ProjectSettingsScreen .row Select { width: 1fr; }
    ProjectSettingsScreen #actions { height: 1; }
    ProjectSettingsScreen #actions Button { margin-right: 1; }
    ProjectSettingsScreen .row Button { margin-left: 1; width: auto; min-width: 8; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.saved = files.read_config()
        self.s3_embedding = self.local_embedding = ""
        if self.saved.backend == "s3":
            self.s3_embedding = self.saved.embedding_model
        else:  # for a local corpus meta.json is the truth, whatever config.toml says
            self.local_embedding = (
                check_corpus(Path(self.saved.corpus_dir or ""))[0]
                or self.saved.embedding_model
            )
            self.saved.embedding_model = self.local_embedding
        self.config = self.saved.model_copy()  # the edits
        self.problem = ""

    def compose(self) -> ComposeResult:
        config = self.config
        yield StatusHeader()
        with VerticalScroll():
            with panel(Vertical(), "corpus"):
                with Horizontal(classes="row"):
                    yield Label("backend")
                    yield Select(
                        [("Local (numpy)", "local"), ("S3 Vectors", "s3")],
                        value=config.backend,
                        allow_blank=False,
                        compact=True,
                        id="backend",
                    )
                with Horizontal(classes="row", id="local"):
                    yield Label("corpus")
                    yield PathInput(config.corpus_dir or "", id="corpus", compact=True)
                    yield Button("Browse", id="browse-corpus", compact=True)
                with Vertical(id="s3"):
                    with Horizontal(classes="row"):
                        yield Label("store")
                        yield Select(
                            NewProjectScreen.store_options(),
                            value=-1,
                            allow_blank=False,
                            compact=True,
                            id="store",
                        )
                    for id_, value in (
                        ("bucket", config.s3_bucket),
                        ("index", config.s3_index),
                        ("region", config.s3_region),
                    ):
                        with Horizontal(classes="row"):
                            yield Label(id_)
                            yield Input(value or "", id=id_, compact=True)
                    yield Button(
                        "Pick embedding model", id="pick-embedding", compact=True
                    )
                    yield Static("", id="store-status")
                    yield Button("Check store", id="check-store", compact=True)
                yield Static("", id="embedding")
            with panel(Vertical(), "models"):
                with Horizontal(classes="row"):
                    yield Static("", id="assistant")
                    yield Button("Change", id="pick-assistant", compact=True)
                with Horizontal(classes="row"):
                    yield Label("thinking")
                    yield Select(
                        [("provider default", "default"), *((e, e) for e in EFFORTS)],
                        value=config.assistant_thinking or "default",
                        allow_blank=False,
                        compact=True,
                        id="thinking",
                    )
                with Horizontal(classes="row"):
                    yield Static("", id="classifier")
                    yield Button("Change", id="pick-classifier", compact=True)
            yield Static(
                f"Prices from genai-prices as of {models.snapshot_date()}; "
                "the header shows actual spend. Changes here affect only this project.",
                classes="note",
            )
        yield Static("", id="pricewarn", classes="warn")
        yield Static("", id="error", classes="error")
        with Horizontal(id="actions"):
            yield Button("Save", id="save", variant="success", compact=True)
            yield Button("Cancel", id="cancel", compact=True)
        yield AppFooter()

    @property
    def embedding(self) -> str:
        return self.s3_embedding if self.backend == "s3" else self.local_embedding

    @property
    def backend(self) -> str:
        return str(self.query_one("#backend", Select).value)

    def on_mount(self) -> None:
        self.show_backend()
        self.refresh_models()

    def show_backend(self) -> None:
        s3 = self.backend == "s3"
        self.query_one("#local").display = not s3
        self.query_one("#s3").display = s3
        self.show_embedding()

    def show_embedding(self) -> None:
        if self.problem:
            text = f"ERROR: {self.problem}"
        elif self.embedding:
            text = f"{escape(self.embedding)}  [$text-muted]{models.price_label(self.embedding)}[/]"
        else:
            text = "[$warning]not chosen[/]"
        self.query_one("#embedding", Static).update(f"embedding: {text}")

    def refresh_models(self) -> None:
        unpriced = [
            m
            for m in (self.config.assistant_model, self.config.classifier_model)
            if models.price_label(m) == models.NO_PRICE
        ]
        warning = self.query_one("#pricewarn", Static)
        warning.update(
            f"WARNING: no price for {escape(', '.join(unpriced))}: cost will show ?"
        )
        warning.display = bool(unpriced)
        for name in ("assistant", "classifier"):
            model = getattr(self.config, f"{name}_model")
            recommended = model in (r[name] for r in system.RECOMMENDED.values())
            mark = "RECOMMENDED" if recommended else "[$warning]DIFFERS[/]"
            self.query_one(f"#{name}", Static).update(
                f"{name}: {escape(model)}  [$text-muted]{models.price_label(model)}[/]"
                f"  {mark}"
            )

    def pick(self, name: str) -> None:
        field = f"{name}_model"

        def done(model: str | None) -> None:
            if model:
                setattr(self.config, field, model)
                self.refresh_models()

        self.app.push_screen(ModelPicker(), done)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "backend":
            self.show_backend()
        elif event.select.id == "store" and event.value != -1:
            store = saved_stores()[int(event.value)]  # ty: ignore[invalid-argument-type]
            self.query_one("#bucket", Input).value = store.bucket
            self.query_one("#index", Input).value = store.index
            self.query_one("#region", Input).value = store.region or ""
            self.s3_embedding = store.embedding_model
            self.show_embedding()
        elif event.select.id == "thinking":
            value = None if event.value == "default" else str(event.value)
            self.config.assistant_thinking = value  # ty: ignore[invalid-assignment]

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "corpus":
            self.local_embedding, self.problem = check_corpus(
                Path(event.value.strip()).expanduser()
            )
            self.show_embedding()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id or ""
        if button == "save":
            self.save()
        elif button == "cancel":
            self.app.pop_screen()
        elif button == "browse-corpus":
            browse(self, self.query_one("#corpus", Input))
        elif button == "check-store":
            self.check_store()
        elif button == "pick-embedding":

            def picked(model: str | None) -> None:
                if model:
                    self.s3_embedding = model
                    self.show_embedding()

            self.app.push_screen(ModelPicker(embedding=True), picked)
        elif button.startswith("pick-"):
            self.pick(button.removeprefix("pick-"))

    def check_store(self) -> None:
        """get_index on the entered store: the only network call on this screen."""
        value = lambda i: self.query_one(f"#{i}", Input).value.strip()
        bucket, index, region = value("bucket"), value("index"), value("region")
        status = self.query_one("#store-status", Static)
        if not (bucket and index):
            status.update("Required: bucket, index")
            return
        status.update("checking…")

        def check() -> None:
            text = check_index(bucket, index, region or None)
            self.app.call_from_thread(status.update, escape(text))

        self.run_worker(check, thread=True)

    def save(self) -> None:
        if self.problem:
            self.query_one("#error", Static).update(escape(f"Corpus: {self.problem}"))
            return
        value = lambda i: self.query_one(f"#{i}", Input).value.strip()
        if self.backend == "s3":
            missing = [n for n in ("bucket", "index") if not value(n)]
            if not self.embedding:
                missing.append("embedding model")
            if missing:
                self.query_one("#error", Static).update(
                    f"Required: {', '.join(missing)}"
                )
                return
            fields: dict = {
                "backend": "s3",
                "s3_bucket": value("bucket"),
                "s3_index": value("index"),
                "s3_region": value("region") or None,
                "corpus_dir": None,
            }
        else:
            fields = {
                "backend": "local",
                "corpus_dir": stored_corpus(
                    Path(value("corpus")).expanduser(), Path.cwd()
                ),
                "s3_bucket": None,
                "s3_index": None,
                "s3_region": None,
            }
        new = self.config.model_copy(
            update={**fields, "embedding_model": self.embedding}
        )
        if new == self.saved:
            self.app.pop_screen()
            return
        consequences = []
        data = ("backend", "corpus_dir", "s3_bucket", "s3_index", "embedding_model")
        if any(getattr(new, f) != getattr(self.saved, f) for f in data):
            consequences.append(
                "Candidates were generated from the old corpus (candidates.jsonl): "
                "re-run Search (stage 2). Gold labels refer to ids."
            )
        if (new.assistant_model, new.assistant_thinking) != (
            self.saved.assistant_model,
            self.saved.assistant_thinking,
        ):
            consequences.append(
                "Assistant changed: only future chat turns use the new model or "
                "thinking setting."
            )
        if new.classifier_model != self.saved.classifier_model:
            consequences.append(
                "Classifier changed: the classifier cache is keyed on the model, so "
                "nothing stale is reused; dev, test and threshold numbers are "
                "recomputed with the new cost; the test result becomes STALE; "
                "results.jsonl (if present) was produced by the old model and is "
                "not rewritten."
            )

        def done(approved: bool | None) -> None:
            if approved:
                files.write_config(new)
                # stage screens read the config once: rebuild the one underneath
                self.app.pop_screen()
                self.app.goto_stage(self.app.stage)  # ty: ignore[unresolved-attribute]

        self.app.push_screen(
            ConfirmScreen("\n\n".join([*consequences, "Nothing is deleted."])), done
        )
