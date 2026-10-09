import os
from pathlib import Path

import pytest
from test_new_project import make_corpus
from test_projects import Host as ProjectsHost
from test_projects import make_project
from textual.widgets import Button, Input, Label, OptionList, Select, Static

from hunches import files, system
from hunches.app import ConfirmScreen, HunchesApp
from hunches.screens.model_picker import ModelPicker
from hunches.screens.paths import PathPicker
from hunches.screens.project_settings import ProjectSettingsScreen
from hunches.theme import HUNCHES

ASSISTANT = "anthropic:claude-sonnet-5-5"
CLASSIFIER = "anthropic:claude-haiku-4-5"


class Host(HunchesApp):
    """HunchesApp that starts on Project settings of the current directory."""

    def on_mount(self, event):  # ty: ignore[invalid-method-override]
        event.prevent_default()  # skip HunchesApp.on_mount
        self.register_theme(HUNCHES)
        self.theme = "hunches"
        self.push_screen(ProjectSettingsScreen())


Host.CSS_PATH = ProjectsHost.CSS_PATH


@pytest.fixture(autouse=True)
def anthropic_key(monkeypatch):
    # the model picker lists only providers that have a key
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")


def project_in(tmp_path, monkeypatch, **config):
    """A project with a real local corpus, as the current directory."""
    project = make_project(tmp_path, corpus=False, **config)
    make_corpus(project, "openai:text-embedding-3-small")
    monkeypatch.chdir(project)
    return project


def text_of(screen) -> str:
    return " ".join(str(w.render()) for w in screen.query(Static))


async def test_shows_the_current_config(tmp_path, monkeypatch):
    project_in(
        tmp_path,
        monkeypatch,
        corpus_dir="corpus",
        assistant_model=ASSISTANT,
        assistant_thinking="high",
        classifier_model=CLASSIFIER,
    )
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#corpus", Input).value == "corpus"
        assert "openai:text-embedding-3-small" in text_of(screen)
        assert screen.query_one("#thinking", Select).value == "high"
        shown = text_of(screen)
        assert ASSISTANT in shown and CLASSIFIER in shown


def settings_config(**extra):
    return dict(
        corpus_dir="corpus",
        assistant_model=ASSISTANT,
        assistant_thinking="high",
        classifier_model=CLASSIFIER,
        **extra,
    )


async def save_and_confirm(app, pilot, approve=True):
    app.screen.query_one("#save", Button).press()
    await pilot.pause()
    assert isinstance(app.screen, ConfirmScreen)
    question = str(app.screen.query_one(Label).render())
    app.screen.query_one("#yes" if approve else "#no", Button).press()
    await pilot.pause()
    return question


async def test_changing_the_corpus_confirms_then_saves_with_its_embedding_model(
    tmp_path, monkeypatch
):
    project = project_in(tmp_path, monkeypatch, **settings_config())
    config = files.read_config()
    config.target_metric, config.target_score = "macro_f1", 0.8
    files.write_config(config)
    other = make_corpus(tmp_path / "other", "openai:text-embedding-3-large")
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#corpus", Input).value = str(other)
        await pilot.pause()
        assert "text-embedding-3-large" in text_of(app.screen)
        question = await save_and_confirm(app, pilot)
        assert "candidates.jsonl" in question and "Search" in question
        assert not isinstance(app.screen, ProjectSettingsScreen)
    saved = files.read_config(project)
    assert saved.corpus_dir == str(other)  # outside the project: absolute
    assert saved.embedding_model == "openai:text-embedding-3-large"
    assert (saved.target_metric, saved.target_score) == ("macro_f1", 0.8)
    assert (saved.assistant_model, saved.classifier_model) == (ASSISTANT, CLASSIFIER)


async def test_saving_without_changes_just_closes(tmp_path, monkeypatch):
    project = project_in(tmp_path, monkeypatch, **settings_config())
    before = (project / ".hunches" / "config.toml").read_bytes()
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#save", Button).press()
        await pilot.pause()
        assert not isinstance(app.screen, (ProjectSettingsScreen, ConfirmScreen))
    assert (project / ".hunches" / "config.toml").read_bytes() == before


async def test_cancelling_the_confirmation_leaves_the_file_unchanged(
    tmp_path, monkeypatch
):
    project = project_in(tmp_path, monkeypatch, **settings_config())
    other = make_corpus(tmp_path / "other", "openai:text-embedding-3-large")
    before = (project / ".hunches" / "config.toml").read_bytes()
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#corpus", Input).value = str(other)
        await pilot.pause()
        await save_and_confirm(app, pilot, approve=False)
        assert isinstance(app.screen, ProjectSettingsScreen)  # edits kept, retry ok
        assert app.screen.query_one("#corpus", Input).value == str(other)
    assert (project / ".hunches" / "config.toml").read_bytes() == before


async def test_a_bad_corpus_is_listed_live_and_disables_save(tmp_path, monkeypatch):
    project = project_in(tmp_path, monkeypatch, **settings_config())
    bad = make_corpus(tmp_path / "bad")
    (bad / "items.jsonl").unlink()
    good = make_corpus(tmp_path / "good")
    before = (project / ".hunches" / "config.toml").read_bytes()
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        save = app.screen.query_one("#save", Button)
        assert not save.disabled
        app.screen.query_one("#corpus", Input).value = str(bad)
        await pilot.pause()
        assert "ERROR: missing items.jsonl" in text_of(app.screen)
        assert save.disabled
        assert "Corpus: missing items.jsonl" in str(
            app.screen.query_one("#error", Static).render()
        )
        app.screen.save()  # the guard stays behind the disabled button
        await pilot.pause()
        assert isinstance(app.screen, ProjectSettingsScreen)  # no confirmation
        app.screen.query_one("#corpus", Input).value = str(good)
        await pilot.pause()
        assert not save.disabled
        assert str(app.screen.query_one("#error", Static).render()) == ""
    assert (project / ".hunches" / "config.toml").read_bytes() == before


async def pick(app, pilot, button, model):
    """Press a Change button and choose `model` in the model picker."""
    app.screen.query_one(button, Button).press()
    await pilot.pause()
    assert isinstance(app.screen, ModelPicker)
    picker = app.screen
    picker.query_one(OptionList).highlighted = [r.model for r in picker.rows].index(
        model
    )
    await pilot.press("enter")
    await pilot.pause()
    assert isinstance(app.screen, ProjectSettingsScreen)


async def test_changing_the_classifier_states_consequences_and_marks_the_test_stale(
    tmp_path, monkeypatch
):
    project = project_in(tmp_path, monkeypatch, **settings_config())
    (project / ".hunches" / "prompt.md").write_text("p")
    result = {"inputs": files.current_inputs("test_done")}
    assert files.result_changes(result) == []
    other = "anthropic:claude-sonnet-5-5"
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pick(app, pilot, "#pick-classifier", other)
        assert other in text_of(app.screen)
        assert "$2.00 in" in text_of(app.screen)  # price beside the new model
        question = await save_and_confirm(app, pilot)
    for words in ("classifier", "cache", "recomputed", "STALE", "results.jsonl"):
        assert words in question, words
    assert "assistant" not in question
    saved = files.read_config(project)
    assert saved.classifier_model == other
    assert saved.assistant_model == ASSISTANT
    assert files.result_changes(result) == ["classifier_model"]  # FinalScreen sees it


async def test_changing_assistant_and_thinking_affects_only_future_chat_turns(
    tmp_path, monkeypatch
):
    project = project_in(tmp_path, monkeypatch, **settings_config())
    other = "anthropic:claude-opus-4-5"
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pick(app, pilot, "#pick-assistant", other)
        app.screen.query_one("#thinking", Select).value = "default"
        await pilot.pause()
        question = await save_and_confirm(app, pilot)
    assert "future chat turns" in question
    assert "classifier cache" not in question and "candidates" not in question
    saved = files.read_config(project)
    assert saved.assistant_model == other
    assert saved.assistant_thinking is None
    assert saved.classifier_model == CLASSIFIER
    assert "assistant_thinking" not in (project / ".hunches/config.toml").read_text()


async def test_models_are_marked_recommended_or_differs(tmp_path, monkeypatch):
    project_in(
        tmp_path,
        monkeypatch,
        **settings_config() | {"classifier_model": "anthropic:claude-opus-4-5"},
    )
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assistant = str(app.screen.query_one("#assistant", Static).render())
        classifier = str(app.screen.query_one("#classifier", Static).render())
        assert assistant.rstrip().endswith("RECOMMENDED")
        assert "DIFFERS" not in assistant
        assert "DIFFERS FROM RECOMMENDED" in classifier
        await pick(app, pilot, "#pick-classifier", CLASSIFIER)  # live update
        assert (
            str(app.screen.query_one("#classifier", Static).render())
            .rstrip()
            .endswith("RECOMMENDED")
        )


def s3_project(tmp_path, monkeypatch, **extra):
    project = tmp_path / "s3proj"
    (project / ".hunches").mkdir(parents=True)
    monkeypatch.chdir(project)
    files.write_config(
        files.Config(
            backend="s3",
            s3_bucket="b",
            s3_index="i",
            s3_region="eu-west-1",
            embedding_model="openai:text-embedding-3-small",
            assistant_model=ASSISTANT,
            classifier_model=CLASSIFIER,
            **extra,
        )
    )
    return project


async def test_s3_fields_are_shown_and_edited(tmp_path, monkeypatch):
    project = s3_project(tmp_path, monkeypatch)
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#backend", Select).value == "s3"
        assert not screen.query_one("#local").display
        assert screen.query_one("#bucket", Input).value == "b"
        assert screen.query_one("#index", Input).value == "i"
        assert screen.query_one("#region", Input).value == "eu-west-1"
        assert "openai:text-embedding-3-small" in text_of(screen)
        screen.query_one("#bucket", Input).value = "b2"
        screen.query_one("#region", Input).value = ""
        question = await save_and_confirm(app, pilot)
        assert "candidates.jsonl" in question
    saved = files.read_config(project)
    assert (saved.s3_bucket, saved.s3_index, saved.s3_region) == ("b2", "i", None)
    assert saved.backend == "s3" and saved.corpus_dir is None


async def test_s3_requires_bucket_index_and_an_embedding_model(tmp_path, monkeypatch):
    project = s3_project(tmp_path, monkeypatch)
    before = (project / ".hunches" / "config.toml").read_bytes()
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#bucket", Input).value = ""
        app.screen.query_one("#index", Input).value = ""
        app.screen.s3_embedding = ""  # ty: ignore[unresolved-attribute]
        app.screen.query_one("#save", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, ProjectSettingsScreen)
        assert "Required: bucket, index, embedding model" in str(
            app.screen.query_one("#error", Static).render()
        )
    assert (project / ".hunches" / "config.toml").read_bytes() == before


async def test_switching_to_s3_with_a_saved_store(tmp_path, monkeypatch):
    system.write_system(
        system.System(provider="anthropic", assistant_model="a", classifier_model="c")
    )
    system.add_store("main", "sb", "si", "us-east-1", "openai:text-embedding-3-large")
    project = project_in(tmp_path, monkeypatch, **settings_config())
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#backend", Select).value = "s3"
        await pilot.pause()
        assert not screen.query_one("#local").display
        screen.query_one("#store", Select).value = 0  # the saved store
        await pilot.pause()
        assert screen.query_one("#bucket", Input).value == "sb"
        assert screen.query_one("#region", Input).value == "us-east-1"
        assert "openai:text-embedding-3-large" in text_of(screen)
        question = await save_and_confirm(app, pilot)
        assert "candidates.jsonl" in question
    saved = files.read_config(project)
    assert (saved.backend, saved.s3_bucket, saved.s3_index) == ("s3", "sb", "si")
    assert saved.s3_region == "us-east-1" and saved.corpus_dir is None
    assert saved.embedding_model == "openai:text-embedding-3-large"
    assert (project / "corpus" / "meta.json").exists()  # nothing deleted


async def test_s3_embedding_model_is_picked_with_the_embedding_picker(
    tmp_path, monkeypatch
):
    project = s3_project(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    new = "openai:text-embedding-3-large"
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#pick-embedding", Button).press()
        await pilot.pause()
        picker = app.screen
        assert isinstance(picker, ModelPicker) and picker.embedding
        picker.query_one(OptionList).highlighted = [r.model for r in picker.rows].index(
            new
        )
        await pilot.press("enter")
        await pilot.pause()
        assert new in text_of(app.screen) and "$0.13 in" in text_of(app.screen)
        question = await save_and_confirm(app, pilot)
        assert "candidates.jsonl" in question
    assert files.read_config(project).embedding_model == new


async def test_check_store_reports_dimension_and_metric(tmp_path, monkeypatch):
    import boto3
    from test_new_project import StubS3Vectors

    s3_project(tmp_path, monkeypatch)
    StubS3Vectors.calls = []
    made = []

    def client(service, **kwargs):
        made.append((service, kwargs))
        return StubS3Vectors("euclidean")

    monkeypatch.setattr(boto3, "client", client)
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#check-store", Button).press()
        await app.workers.wait_for_complete()
        await pilot.pause()
        status = str(app.screen.query_one("#store-status", Static).render())
        assert "WARNING: distance metric is euclidean, not cosine" in status
        assert "dimension 3" in status
    assert made == [("s3vectors", {"region_name": "eu-west-1"})]
    assert StubS3Vectors.calls == [{"vectorBucketName": "b", "indexName": "i"}]


async def test_a_corpus_inside_the_project_is_stored_relative(tmp_path, monkeypatch):
    project = project_in(tmp_path, monkeypatch, **settings_config())
    inside = make_corpus(project / "more", "openai:text-embedding-3-large")
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#corpus", Input).value = str(inside)
        await pilot.pause()
        await save_and_confirm(app, pilot)
    assert files.read_config(project).corpus_dir == "more/corpus"


async def test_browse_writes_the_chosen_folder_back(tmp_path, monkeypatch):
    project_in(tmp_path, monkeypatch, **settings_config())
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#corpus", Input).value = str(tmp_path)
        screen.query_one("#browse-corpus", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, PathPicker)
        app.screen.query_one("#select", Button).press()  # no highlight: the root
        await pilot.pause()
        assert app.screen is screen
        assert screen.query_one("#corpus", Input).value == str(tmp_path)


@pytest.mark.parametrize("backend", ["local", "s3"])
async def test_fits_80x24_with_save_cancel_and_error_always_visible(
    tmp_path, monkeypatch, backend
):
    project_in(tmp_path, monkeypatch, **settings_config())
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#backend", Select).value = backend
        await pilot.pause()
        app.screen.query_one("#error", Static).update("Required: x")
        for id_ in ("save", "cancel", "error"):
            assert app.screen.query_one(f"#{id_}").region.bottom <= 23, id_
        await pilot.click("#cancel")  # reachable without scrolling
        await pilot.pause()
        assert not isinstance(app.screen, ProjectSettingsScreen)


async def test_footnote_and_unpriced_model_row(tmp_path, monkeypatch):
    project_in(
        tmp_path,
        monkeypatch,
        **settings_config() | {"classifier_model": "openai:made-up-model"},
    )
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        shown = text_of(app.screen)
        assert "Prices from genai-prices as of 20" in shown
        assert "the header shows actual spend" in shown
        assert not app.screen.query("#pricewarn")
        first, second = str(
            app.screen.query_one("#classifier", Static).render()
        ).splitlines()
        assert "openai:made-up-model" in first and "no price" not in first
        assert second.strip() == "no price: cost will show ?"


async def test_footnote_says_sidebar_in_rail_mode(tmp_path, monkeypatch):
    project_in(tmp_path, monkeypatch, **settings_config())
    app = Host()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert "the sidebar shows actual spend" in text_of(app.screen)


async def test_e_on_projects_opens_the_project_then_its_settings(tmp_path, monkeypatch):
    from test_projects import register

    monkeypatch.chdir(tmp_path)
    project = make_project(tmp_path, "edited")
    register(project)
    app = ProjectsHost()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, ProjectSettingsScreen)
        assert Path.cwd() == project.resolve()
        assert app.stage >= 1  # the project's stage is underneath
        app.screen.query_one("#cancel", Button).press()
        await pilot.pause()
        assert app.stage >= 1 and not isinstance(app.screen, ProjectSettingsScreen)
    os.chdir(tmp_path)


async def test_e_on_an_unhealthy_project_does_not_open_settings(tmp_path, monkeypatch):
    from test_projects import register

    monkeypatch.chdir(tmp_path)
    register(tmp_path / "gone")
    app = ProjectsHost()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert not isinstance(app.screen, ProjectSettingsScreen)
        assert Path.cwd() == tmp_path


async def test_f3_opens_settings_from_a_stage_and_saving_reloads_the_stage(
    tmp_path, monkeypatch
):
    from test_projects import register

    project = project_in(tmp_path, monkeypatch, **settings_config())
    register(project)
    app = ProjectsHost()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.open_project(project)
        await pilot.pause()
        stage_screen = app.screen
        await pilot.press("f3")
        await pilot.pause()
        assert isinstance(app.screen, ProjectSettingsScreen)
        await pilot.press("f3")  # already open: not stacked
        await pilot.pause()
        assert len(app.screen_stack) == 3
        await pick(app, pilot, "#pick-classifier", "anthropic:claude-opus-4-5")
        await save_and_confirm(app, pilot)
        assert not isinstance(app.screen, ProjectSettingsScreen)
        assert type(app.screen) is type(stage_screen)
        assert app.screen is not stage_screen  # rebuilt with the new config
        assert len(app.screen_stack) == 2
    os.chdir(tmp_path)
