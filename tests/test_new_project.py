import json
import os
from pathlib import Path
from typing import ClassVar

import pytest
from test_projects import Host as ProjectsHost
from textual.widgets import Button, Input, Static

from hunches import files, system
from hunches.app import HunchesApp
from hunches.screens.new_project import NewProjectScreen
from hunches.screens.system import saved_stores
from hunches.theme import HUNCHES

ASSISTANT = "anthropic:claude-sonnet-5-5"
CLASSIFIER = "anthropic:claude-haiku-4-5"


class Host(HunchesApp):
    """HunchesApp that starts on the New project screen (the startup flow is task 09)."""

    def on_mount(self, event):  # ty: ignore[invalid-method-override]
        event.prevent_default()  # skip HunchesApp.on_mount
        self.register_theme(HUNCHES)
        self.theme = "hunches"
        self.push_screen(NewProjectScreen())


Host.CSS_PATH = ProjectsHost.CSS_PATH


@pytest.fixture(autouse=True)
def env(monkeypatch):
    """System settings exist (anthropic) and an Anthropic key is available."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    system.write_system(
        system.System(
            provider="anthropic",
            assistant_model=ASSISTANT,
            assistant_thinking="medium",
            classifier_model=CLASSIFIER,
            recommendation_seen=system.RECOMMENDED_REVISION,
        )
    )


def make_corpus(base: Path, model="openai:text-embedding-3-small") -> Path:
    corpus = base / "corpus"
    corpus.mkdir(parents=True)
    (corpus / "vectors.npy").write_text("x")
    (corpus / "items.jsonl").write_text("x")
    (corpus / "meta.json").write_text(json.dumps({"embedding_model": model}))
    return corpus


def text_of(screen) -> str:
    return " ".join(str(w.render()) for w in screen.query(Static))


async def test_local_happy_path_writes_config_registers_and_opens(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    corpus = make_corpus(tmp_path / "data")
    project = tmp_path / "work" / "proj"
    (tmp_path / "work").mkdir()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")  # the embedding provider
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#location", Input).value = str(project)
        app.screen.query_one("#corpus", Input).value = str(corpus)
        await pilot.pause()
        app.screen.query_one("#create", Button).press()
        await pilot.pause()
        assert app.stage == 1
        assert Path.cwd() == project
    config = files.read_config(project)
    assert config.backend == "local"
    assert config.corpus_dir == str(corpus)  # outside the project: absolute
    assert config.embedding_model == "openai:text-embedding-3-small"
    assert (config.assistant_model, config.assistant_thinking) == (ASSISTANT, "medium")
    assert config.classifier_model == CLASSIFIER
    assert [p.path for p in system.projects_by_recent()] == [str(project.resolve())]
    os.chdir(tmp_path)  # leave the project dir for tmp cleanup


async def test_corpus_inside_the_project_is_stored_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "proj"
    make_corpus(project)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await submit(app, pilot, location=project, corpus=project / "corpus")
    assert files.read_config(project).corpus_dir == "corpus"
    os.chdir(tmp_path)


async def submit(app, pilot, **values):
    for id_, value in values.items():
        app.screen.query_one(f"#{id_}", Input).value = str(value)
    await pilot.pause()
    app.screen.query_one("#create", Button).press()
    await pilot.pause()


async def test_create_is_disabled_until_the_corpus_is_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    corpus = make_corpus(tmp_path / "data")
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        create = app.screen.query_one("#create", Button)
        hint = app.screen.query_one("#error", Static)
        assert create.disabled
        assert str(hint.render()) == "Required: corpus"
        app.screen.create()  # ty: ignore[unresolved-attribute]
        await pilot.pause()
        assert "Required: corpus" in str(hint.render())
        assert not (tmp_path / ".hunches").exists()
        app.screen.query_one("#corpus", Input).value = str(corpus)
        await pilot.pause()
        assert not create.disabled
        assert str(hint.render()) == ""
        app.screen.query_one("#corpus", Input).value = str(tmp_path)  # no files
        await pilot.pause()
        assert create.disabled
        assert "missing items.jsonl" in str(hint.render())
        app.screen.query_one("#corpus", Input).value = ""
        await pilot.pause()
        assert create.disabled and str(hint.render()) == "Required: corpus"


async def test_corpus_missing_files_are_listed_live_and_block_create(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    corpus = make_corpus(tmp_path / "data")
    (corpus / "items.jsonl").unlink()
    (corpus / "vectors.npy").unlink()
    project = tmp_path / "proj"
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#corpus", Input).value = str(corpus)
        await pilot.pause()
        status = str(app.screen.query_one("#corpus-status", Static).render())
        assert "missing items.jsonl, vectors.npy" in status
        await pilot.pause()
        assert app.screen.query_one("#create", Button).disabled
        error = str(app.screen.query_one("#error", Static).render())
        assert error == "Corpus: missing items.jsonl, vectors.npy"
        app.screen.query_one("#location", Input).value = str(project)
        app.screen.create()  # ty: ignore[unresolved-attribute]
        assert str(app.screen.query_one("#error", Static).render()) == error
    assert not (project / ".hunches").exists()


async def test_meta_without_embedding_model_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    corpus = make_corpus(tmp_path / "data")
    (corpus / "meta.json").write_text("{}")
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#corpus", Input).value = str(corpus)
        await pilot.pause()
        assert app.screen.query_one("#create", Button).disabled
        assert "embedding_model" in str(app.screen.query_one("#error", Static).render())
    assert not (tmp_path / "proj" / ".hunches").exists()


async def test_location_whose_parent_is_missing_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")  # the corpus embedding
    corpus = make_corpus(tmp_path / "data")
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await submit(app, pilot, location=tmp_path / "nope" / "proj", corpus=corpus)
        error = str(app.screen.query_one("#error", Static).render())
        assert error.startswith("Location: parent folder does not exist")
    assert not (tmp_path / "nope").exists()


async def test_existing_project_is_refused_with_an_open_button(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")  # the corpus embedding
    corpus = make_corpus(tmp_path / "data")
    project = tmp_path / "proj"
    (project / ".hunches").mkdir(parents=True)
    files.write_config(
        files.Config(
            assistant_model="a",
            corpus_dir=str(corpus),
            embedding_model="m",
            classifier_model="keep",
        ),
        project,
    )
    before = (project / ".hunches" / "config.toml").read_text()
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        open_it = app.screen.query_one("#open-existing", Button)
        assert not open_it.display
        await submit(app, pilot, location=project, corpus=corpus)
        assert "already a project" in str(
            app.screen.query_one("#error", Static).render()
        )
        assert open_it.display
        assert (project / ".hunches" / "config.toml").read_text() == before
        open_it.press()
        await pilot.pause()
        assert Path.cwd() == project and app.stage == 1
    os.chdir(tmp_path)


async def test_models_are_summarised_with_prices(tmp_path, monkeypatch):
    from hunches import models

    monkeypatch.chdir(tmp_path)
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        text = str(app.screen.query_one("#models", Static).render()) + str(
            app.screen.query_one("#models-rest", Static).render()
        )
        assert f"assistant: {ASSISTANT}" in text
        assert models.price_label(ASSISTANT) in text
        assert "thinking: medium" in text
        assert f"classifier: {CLASSIFIER}" in text
        assert models.price_label(CLASSIFIER) in text
        assert "pinned for this project" in text


async def test_missing_key_blocks_create_and_system_settings_returns_intact(
    tmp_path, monkeypatch
):
    from hunches.screens.system import SystemSettingsScreen

    monkeypatch.chdir(tmp_path)
    corpus = make_corpus(
        tmp_path / "data"
    )  # embedding model is openai: -> needs OPENAI
    project = tmp_path / "proj"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await submit(app, pilot, location=project, corpus=corpus)
        form = app.screen
        assert form.query_one("#create", Button).disabled
        form.create()  # ty: ignore[unresolved-attribute]
        await pilot.pause()
        blocked = str(form.query_one("#keys", Static).render())
        assert "ANTHROPIC_API_KEY" in blocked and "OPENAI_API_KEY" in blocked
        assert "BLOCKED" in blocked
        assert "BLOCKED" in str(form.query_one("#error", Static).render())
        assert not project.exists()
        form.query_one("#open-system", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, SystemSettingsScreen)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        app.screen.query_one("#cancel", Button).press()
        await pilot.pause()
        assert app.screen is form
        assert form.query_one("#location", Input).value == str(project)
        assert form.query_one("#corpus", Input).value == str(corpus)
        assert not form.query_one("#keys", Static).display
        assert not form.query_one("#create", Button).disabled
        form.query_one("#create", Button).press()
        await pilot.pause()
        assert Path.cwd() == project
    os.chdir(tmp_path)


async def test_s3_happy_path_saves_the_store(tmp_path, monkeypatch):
    from textual.widgets import Checkbox, Select

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    project = tmp_path / "proj"
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        form = app.screen
        form.query_one("#backend", Select).value = "s3"
        await pilot.pause()
        assert not form.query_one("#local").display and form.query_one("#s3").display
        assert form.query_one("#save-store", Checkbox).value  # on by default
        await submit(
            app, pilot, location=project, bucket="b", index="i", region="eu-west-1"
        )
        assert form.query_one("#create", Button).disabled
        assert str(form.query_one("#error", Static).render()) == (
            "Required: embedding model"
        )
        form.query_one("#pick-embedding", Button).press()
        await pilot.pause()
        await pilot.press("down", "enter")  # the first listed openai embedding model
        await pilot.pause()
        assert isinstance(form, NewProjectScreen)
        chosen = form.embedding
        assert chosen.startswith("openai:")
        assert chosen in str(form.query_one("#embedding", Static).render())
        assert not form.query_one("#create", Button).disabled
        assert str(form.query_one("#error", Static).render()) == ""
        form.query_one("#create", Button).press()
        await pilot.pause()
        assert Path.cwd() == project
    config = files.read_config(project)
    assert (config.backend, config.s3_bucket, config.s3_index) == ("s3", "b", "i")
    assert (config.s3_region, config.embedding_model) == ("eu-west-1", chosen)
    assert config.corpus_dir is None
    [store] = saved_stores()
    assert (store.name, store.bucket, store.index) == ("b/i", "b", "i")
    assert (store.region, store.embedding_model) == ("eu-west-1", chosen)
    os.chdir(tmp_path)


async def test_saved_store_prefills_and_is_offered_again(tmp_path, monkeypatch):
    from textual.widgets import Checkbox, Select

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    system.add_store("wapo", "bk", "ix", "us-east-2", "openai:text-embedding-3-small")
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        form = app.screen
        form.query_one("#backend", Select).value = "s3"
        await pilot.pause()
        store = form.query_one("#store", Select)
        store.value = 0  # the saved store; -1 is "New store…"
        await pilot.pause()
        assert form.query_one("#bucket", Input).value == "bk"
        assert form.query_one("#index", Input).value == "ix"
        assert form.query_one("#region", Input).value == "us-east-2"
        assert "openai:text-embedding-3-small" in str(
            form.query_one("#embedding", Static).render()
        )
        assert not form.query_one("#save-store", Checkbox).value
        await submit(app, pilot, location=tmp_path / "proj")
        assert Path.cwd() == tmp_path / "proj"
    config = files.read_config(tmp_path / "proj")
    assert (config.s3_bucket, config.s3_index, config.s3_region) == (
        "bk",
        "ix",
        "us-east-2",
    )
    assert [s.name for s in saved_stores()] == ["wapo"]
    os.chdir(tmp_path)


class StubS3Vectors:
    calls: ClassVar[list] = []

    def __init__(self, metric):
        self.metric = metric

    def get_index(self, **params):
        self.calls.append(params)
        return {"index": {"dimension": 3, "distanceMetric": self.metric}}


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        ("cosine", "dimension 3, distance metric cosine"),
        ("euclidean", "WARNING: distance metric is euclidean, not cosine"),
    ],
)
async def test_check_store_reports_dimension_and_metric(
    tmp_path, monkeypatch, metric, expected
):
    import boto3
    from textual.widgets import Select

    monkeypatch.chdir(tmp_path)
    StubS3Vectors.calls = []
    made = []

    def client(service, **kwargs):
        made.append((service, kwargs))
        return StubS3Vectors(metric)

    monkeypatch.setattr(boto3, "client", client)
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        form = app.screen
        form.query_one("#backend", Select).value = "s3"
        await pilot.pause()
        form.query_one("#check-store", Button).press()
        await pilot.pause()
        assert "Required: bucket, index" in str(
            form.query_one("#store-status", Static).render()
        )
        assert not made  # no network call without a bucket and index
        form.query_one("#bucket", Input).value = "b"
        form.query_one("#index", Input).value = "i"
        form.query_one("#region", Input).value = "eu-west-1"
        form.query_one("#check-store", Button).press()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert expected in str(form.query_one("#store-status", Static).render())
    assert made == [("s3vectors", {"region_name": "eu-west-1"})]
    assert StubS3Vectors.calls == [{"vectorBucketName": "b", "indexName": "i"}]


async def test_n_on_projects_creates_registers_and_opens_a_project(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    corpus = make_corpus(tmp_path / "data")
    project = tmp_path / "proj"
    app = ProjectsHost()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, NewProjectScreen)
        await submit(app, pilot, location=project, corpus=corpus)
        assert Path.cwd() == project and app.stage == 1
        assert [p.path for p in system.projects_by_recent()] == [str(project.resolve())]
    os.chdir(tmp_path)


@pytest.mark.parametrize("backend", ["local", "s3"])
async def test_fits_80x24_with_create_and_messages_always_visible(
    tmp_path, monkeypatch, backend
):
    from textual.widgets import Select

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#backend", Select).value = backend
        await pilot.pause()
        for id_ in ("create", "open-system", "keys", "error"):
            assert app.screen.query_one(f"#{id_}").region.bottom <= 23, id_
        assert app.screen.query_one("#create", Button).disabled
        assert "Required" in str(app.screen.query_one("#error", Static).render())


async def test_browse_writes_the_chosen_folder_back(tmp_path, monkeypatch):
    from hunches.screens.paths import PathPicker

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        form = app.screen
        form.query_one("#corpus", Input).value = str(tmp_path)
        form.query_one("#browse-corpus", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, PathPicker)
        app.screen.query_one("#select", Button).press()  # no highlight: the root
        await pilot.pause()
        assert app.screen is form
        assert form.query_one("#corpus", Input).value == str(tmp_path)
        form.query_one("#location", Input).value = ""
        form.query_one("#browse-location", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, PathPicker)
        app.screen.query_one("#select", Button).press()
        await pilot.pause()
        assert form.query_one("#location", Input).value == str(tmp_path)


async def test_every_button_has_a_visible_label(tmp_path, monkeypatch):
    # a Button created without a label renders its repr, e.g. "Button#browse-corpus"
    monkeypatch.chdir(tmp_path)
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        for button in app.screen.query(Button):
            assert not str(button.label).startswith("Button#"), button.id
        assert str(app.screen.query_one("#browse-location", Button).label) == "Browse"
