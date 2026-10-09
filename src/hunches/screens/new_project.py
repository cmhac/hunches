"""New project: write .hunches/config.toml for a folder, register it and open it."""

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.markup import escape
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Input, Label, Rule, Select, Static

from hunches import files, keys, models, system
from hunches.app import AppFooter, StatusHeader, panel
from hunches.screens.model_picker import ModelPicker
from hunches.screens.paths import PathInput, browse
from hunches.screens.pg import (
    PG_CSS,
    compose_pg,
    pg_fields,
    pg_input_changed,
    pg_mount,
    pg_pressed,
    pg_select_changed,
    timeout_problem,
)
from hunches.screens.system import SystemSettingsScreen, saved_stores


def check_corpus(corpus: Path) -> tuple[str, str]:
    """(embedding model from meta.json, "") or ("", what is wrong)."""
    missing = [
        f
        for f in ("vectors.npy", "items.jsonl", "meta.json")
        if not (corpus / f).exists()
    ]
    if missing:
        return "", f"missing {', '.join(sorted(missing))}"
    try:
        model = json.loads((corpus / "meta.json").read_text())["embedding_model"]
    except (OSError, ValueError, KeyError, TypeError):
        return "", "meta.json has no embedding_model"
    return str(model), ""


def stored_corpus(corpus: Path, project: Path) -> str:
    """Relative to the project dir when the corpus is inside it (portable), else as typed."""
    try:
        return str(corpus.resolve().relative_to(project.resolve()))
    except ValueError:
        return str(corpus)


def check_index(bucket: str, index: str, region: str | None) -> str:
    """get_index on a store: dimension and metric, or the error text."""
    try:
        import boto3

        found = boto3.client("s3vectors", region_name=region).get_index(
            vectorBucketName=bucket, indexName=index
        )["index"]
        metric = found["distanceMetric"]
        text = f"dimension {found['dimension']}, distance metric {metric}"
        if metric != "cosine":
            text = f"WARNING: distance metric is {metric}, not cosine ({text})"
    except Exception as e:  # noqa: BLE001  credentials, network, missing index
        text = f"ERROR: {e}"
    return text


class NewProjectScreen(Screen):
    stage_name = "New project"
    DEFAULT_CSS = (
        """
    NewProjectScreen > VerticalScroll { height: 1fr; }
    NewProjectScreen .panel { height: auto; }
    NewProjectScreen .row { height: auto; }
    NewProjectScreen .row Static { width: 1fr; }
    NewProjectScreen .row Label { width: 11; color: $text-muted; }
    NewProjectScreen .row Input, NewProjectScreen .row Select { width: 1fr; }
    NewProjectScreen .row Button { margin-left: 1; width: auto; min-width: 8; }
    NewProjectScreen #local, NewProjectScreen #s3 { height: auto; }
    NewProjectScreen #actions { height: 1; }
    NewProjectScreen #actions Button { margin-right: 1; }
    NewProjectScreen #actions #error { width: 1fr; height: 1; }
    NewProjectScreen Rule { margin: 0; }
    """
        + PG_CSS
    )

    embedding = ""  # the embedding model the project will use

    def __init__(self) -> None:
        super().__init__()
        self.missing_keys: list[str] = []

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        with VerticalScroll():
            with panel(Vertical(), "location"), Horizontal(classes="row"):
                yield Label("folder")
                yield PathInput(str(Path.cwd()), id="location", compact=True)
                yield Button("Browse", id="browse-location", compact=True)
            with panel(Vertical(), "corpus"):
                with Horizontal(classes="row"):
                    yield Label("backend")
                    yield Select(
                        [
                            ("Local (numpy)", "local"),
                            ("S3 Vectors", "s3"),
                            ("PostgreSQL (pgvector)", "pgvector"),
                        ],
                        value="local",
                        allow_blank=False,
                        compact=True,
                        id="backend",
                    )
                with Vertical(id="local"):
                    with Horizontal(classes="row"):
                        yield Label("corpus")
                        yield PathInput(id="corpus", compact=True)
                        yield Button("Browse", id="browse-corpus", compact=True)
                    yield Static("", id="corpus-status")
                with Vertical(id="s3"):
                    with Horizontal(classes="row"):
                        yield Label("store")
                        yield Select(
                            self.store_options(),
                            value=-1,
                            allow_blank=False,
                            compact=True,
                            id="store",
                        )
                    for id_ in ("bucket", "index", "region"):
                        with Horizontal(classes="row"):
                            yield Label(id_)
                            yield Input(
                                placeholder="optional" if id_ == "region" else "",
                                id=id_,
                                compact=True,
                            )
                    yield Checkbox(
                        "Save this store for other projects",
                        True,
                        id="save-store",
                        compact=True,
                    )
                    yield Static("", id="store-status")
                    yield Button("Check store", id="check-store", compact=True)
                yield from compose_pg()
                with Horizontal(classes="row", id="embedding-row"):  # s3 and pgvector
                    yield Label("embedding")
                    yield Static("", id="embedding")
                    yield Button("Pick", id="pick-embedding", compact=True)
            with panel(Vertical(), "models"):
                yield Static("", id="models")
                yield Rule()
                yield Static("", id="models-rest")
        # outside the scroll area so Create and its messages stay visible at 80x24
        yield Static("", id="keys", classes="warn")
        with Horizontal(id="actions"):
            yield Button("System settings", id="open-system", compact=True)
            yield Button(
                "Create", id="create", variant="primary", compact=True, disabled=True
            )
            yield Button("Open it", id="open-existing", compact=True)
            yield Static("", id="error", classes="note")
        yield AppFooter()

    @staticmethod
    def store_options() -> list[tuple[str, int]]:
        return [
            ("New store…", -1),
            *((s.name, i) for i, s in enumerate(saved_stores())),
        ]

    def on_mount(self) -> None:
        self.query_one("#open-existing").display = False
        self.query_one("#s3").display = False
        self.query_one("#embedding-row").display = False
        pg_mount(self)
        self.refresh_summary()

    def refresh_summary(self) -> None:
        """Pinned models with prices, and the blocking message for missing keys."""
        current = system.read_system()
        assert current
        lines = [
            f"assistant: {escape(current.assistant_model)}  [$text-muted]{models.price_label(current.assistant_model)}[/]",
            f"thinking: {current.assistant_thinking or 'provider default'}",
        ]
        self.query_one("#models", Static).update("\n".join(lines))
        self.query_one("#models-rest", Static).update(
            f"classifier: {escape(current.classifier_model)}  [$text-muted]{models.price_label(current.classifier_model)}[/]\n"
            "[$text-muted]pinned for this project; change later in Project settings[/]"
        )
        needed = {
            keys.provider_var(m)
            for m in (current.assistant_model, current.classifier_model, self.embedding)
        }
        missing = [
            v for v in sorted(v for v in needed if v) if keys.status(v) == "missing"
        ]
        box = self.query_one("#keys", Static)
        box.update(f"BLOCKED: missing API key {', '.join(map(str, missing))}")
        box.display = bool(missing)
        self.query_one("#open-system").display = bool(missing)
        self.missing_keys = missing
        self.query_one("#embedding", Static).update(
            escape(self.embedding) if self.embedding else "[$warning]not chosen[/]"
        )
        self.refresh_create()

    def refresh_create(self) -> None:
        """Create is enabled only for a valid form; the reason sits beside it (create() keeps the guards)."""
        value = lambda i: self.query_one(f"#{i}", Input).value.strip()
        backend = self.query_one("#backend", Select).value
        s3 = backend == "s3"
        pg = backend == "pgvector"
        missing = [
            n
            for n in ("location", *(("bucket", "index") if s3 else ()))
            if not value(n)
        ]
        problem = ""
        if pg:
            if not value("pg-table"):
                missing.append("table")
            if not self.embedding:
                missing.append("embedding model")
            problem = timeout_problem(self)
        elif s3:
            if not self.embedding:
                missing.append("embedding model")
        elif not value("corpus"):
            missing.append("corpus")
        else:
            problem = check_corpus(Path(value("corpus")).expanduser())[1]
        hint = f"Required: {', '.join(missing)}" if missing else ""
        hint = hint or (f"{'Corpus: ' * (not pg)}{problem}" if problem else "")
        line = self.query_one("#error", Static)
        line.set_classes("error" if problem else "note")
        line.update(escape(hint))
        self.query_one("#create", Button).disabled = bool(hint or self.missing_keys)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "backend":
            local = event.value == "local"
            self.query_one("#local").display = local
            self.query_one("#s3").display = event.value == "s3"
            self.query_one("#pg").display = event.value == "pgvector"
            self.query_one("#embedding-row").display = not local
            self.embedding = self.corpus_embedding() if local else self.s3_embedding
            self.refresh_summary()
        elif event.select.id in ("pg-auth", "pg-search"):
            pg_select_changed(self, event)
            self.refresh_create()
        elif event.select.id == "store" and event.value != -1:
            store = saved_stores()[int(event.value)]  # ty: ignore[invalid-argument-type]
            self.query_one("#bucket", Input).value = store.bucket
            self.query_one("#index", Input).value = store.index
            self.query_one("#region", Input).value = store.region or ""
            self.s3_embedding = self.embedding = store.embedding_model
            self.query_one("#save-store", Checkbox).value = False
            self.refresh_summary()

    s3_embedding = ""

    def corpus_embedding(self) -> str:
        corpus = self.query_one("#corpus", Input).value.strip()
        return check_corpus(Path(corpus).expanduser())[0] if corpus else ""

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "corpus":
            value = event.value.strip()
            model, problem = (
                check_corpus(Path(value).expanduser()) if value else ("", "")
            )
            self.query_one("#corpus-status", Static).update(
                ""
                if not value
                else f"ERROR: {problem}"
                if problem
                else f"embedding model: {model} (from meta.json)"
            )
            self.embedding = model
            self.refresh_summary()
        else:
            pg_input_changed(self, event)
            self.refresh_create()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button == "open-existing":
            self.open(Path(self.query_one("#location", PathInput).value).expanduser())
        elif button == "open-system":
            self.app.push_screen(
                SystemSettingsScreen(), lambda _: self.refresh_summary()
            )
        elif button in ("browse-location", "browse-corpus"):
            browse(self, self.query_one(f"#{button.removeprefix('browse-')}", Input))
        elif button == "pick-embedding":

            def picked(model: str | None) -> None:
                if model:
                    self.s3_embedding = self.embedding = model
                    self.refresh_summary()

            self.app.push_screen(ModelPicker(embedding=True), picked)
        elif button == "check-store":
            self.check_store()
        elif pg_pressed(self, button, self.embedding):
            pass
        elif button == "create":
            self.create()

    def check_store(self) -> None:
        """get_index on the entered store: the only network call on this screen."""
        bucket = self.query_one("#bucket", Input).value.strip()
        index = self.query_one("#index", Input).value.strip()
        region = self.query_one("#region", Input).value.strip() or None
        if not (bucket and index):
            self.show_store("Required: bucket, index")
            return
        self.show_store("checking…")

        def check() -> None:
            text = check_index(bucket, index, region)
            self.app.call_from_thread(self.show_store, text)

        self.run_worker(check, thread=True)

    def show_store(self, text: str) -> None:
        self.query_one("#store-status", Static).update(escape(text))

    def open(self, location: Path) -> None:
        system.add_project(location)
        self.app.open_project(location)  # ty: ignore[unresolved-attribute]

    def fail(self, text: str, existing: bool = False) -> None:
        line = self.query_one("#error", Static)
        line.set_classes("error")
        line.update(text)
        self.query_one("#open-existing").display = existing

    def create(self) -> None:
        current = system.read_system()
        assert current
        value = lambda i: self.query_one(f"#{i}", Input).value.strip()
        backend = self.query_one("#backend", Select).value
        s3 = backend == "s3"
        pg = backend == "pgvector"
        needed = ["location", *(["bucket", "index"] if s3 else ["corpus"])]
        if pg:
            needed = ["location", "pg-table"]
        missing = [name.removeprefix("pg-") for name in needed if not value(name)]
        if (s3 or pg) and not self.embedding:
            missing.append("embedding model")
        if pg and (problem := timeout_problem(self)):
            self.fail(problem)
            return
        if missing:
            self.fail(f"Required: {', '.join(missing)}")
            return
        location = Path(value("location")).expanduser()
        if (location / ".hunches" / "config.toml").exists():
            self.fail("Location: already a project - open it instead", existing=True)
            return
        if not location.parent.is_dir():
            self.fail("Location: parent folder does not exist")
            return
        fields: dict = {"backend": backend} if backend != "local" else {}
        if pg:
            fields |= pg_fields(self) | {"embedding_model": self.embedding}
        elif s3:
            fields |= {
                "s3_bucket": value("bucket"),
                "s3_index": value("index"),
                "s3_region": value("region") or None,
                "embedding_model": self.embedding,
            }
        else:
            corpus = Path(value("corpus")).expanduser()
            embedding, problem = check_corpus(corpus)
            if problem:
                self.fail(f"Corpus: {problem}")
                return
            fields |= {
                "corpus_dir": stored_corpus(corpus, location),
                "embedding_model": embedding,
            }
        if self.missing_keys:
            self.fail("BLOCKED: add the missing API key in System settings")
            return
        location.mkdir(parents=True, exist_ok=True)
        (location / ".hunches").mkdir(exist_ok=True)
        files.write_config(
            files.Config(
                **fields,
                assistant_model=current.assistant_model,
                assistant_thinking=current.assistant_thinking,  # ty: ignore[invalid-argument-type]
                classifier_model=current.classifier_model,
            ),
            location,
        )
        if s3 and self.query_one("#save-store", Checkbox).value:
            system.add_store(
                f"{fields['s3_bucket']}/{fields['s3_index']}",
                fields["s3_bucket"],
                fields["s3_index"],
                fields["s3_region"],
                self.embedding,
            )
        self.open(location)
