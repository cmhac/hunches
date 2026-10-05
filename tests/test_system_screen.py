from pathlib import Path
from typing import Any

import pytest
from conftest import panel_title
from textual.app import App
from textual.widgets import Button, Input, Select, Static

from hunches import keys, system
from hunches.screens.system import (
    RecommendationModal,
    SystemSettingsScreen,
    saved_stores,
)
from hunches.theme import HUNCHES

SENTINEL = "sk-SENTINEL-do-not-render"


class Host(App):
    result = "unset"

    def on_mount(self):
        self.register_theme(HUNCHES)
        self.theme = "hunches"
        self.push_screen(SystemSettingsScreen(), self.got)

    def got(self, saved):
        self.result = saved


Host.CSS_PATH = str(Path(__file__).parent.parent / "src" / "hunches" / "hunches.tcss")


def stored() -> system.System:
    current = system.read_system()
    assert current is not None
    return current


def text_of(screen) -> str:
    return " ".join(str(w.render()) for w in screen.query(Static))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in keys.VARS:
        monkeypatch.delenv(var, raising=False)


async def test_first_run_has_no_cancel_and_save_is_disabled_until_a_key():
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert "Welcome" in text_of(screen)
        assert not screen.query("#cancel")
        save = screen.query_one("#save", Button)
        assert save.disabled
        assert "Add at least one API key to save" in str(
            screen.query_one("#error", Static).render()
        )
        screen.save()  # ty: ignore[unresolved-attribute]
        await pilot.pause()
        assert system.read_system() is None
        assert app.result == "unset"
        box = screen.query_one("#key-ANTHROPIC_API_KEY", Input)
        box.value = SENTINEL
        screen.query_one("#savekey-ANTHROPIC_API_KEY", Button).press()
        await pilot.pause()
        assert not save.disabled
        assert str(screen.query_one("#error", Static).render()) == ""
        screen.query_one("#removekey-ANTHROPIC_API_KEY", Button).press()
        await pilot.pause()
        assert save.disabled
        assert "Add at least one API key" in str(
            screen.query_one("#error", Static).render()
        )


async def test_env_key_enables_save(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert not app.screen.query_one("#save", Button).disabled


async def test_save_and_remove_key_updates_status_and_never_shows_key():
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        status = screen.query_one("#status-ANTHROPIC_API_KEY", Static)
        assert "MISSING" in str(status.render())
        box = screen.query_one("#key-ANTHROPIC_API_KEY", Input)
        assert box.password
        box.value = SENTINEL
        screen.query_one("#savekey-ANTHROPIC_API_KEY", Button).press()
        await pilot.pause()
        assert keys.status("ANTHROPIC_API_KEY") == "keyring"
        assert "KEYRING" in str(status.render())
        assert box.value == ""
        assert SENTINEL not in text_of(screen)
        screen.query_one("#removekey-ANTHROPIC_API_KEY", Button).press()
        await pilot.pause()
        assert keys.status("ANTHROPIC_API_KEY") == "missing"
        assert "MISSING" in str(status.render())


async def test_no_keyring_shows_message_and_offers_no_key_save(no_keyring):
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert "No system keyring available" in text_of(screen)
        assert "ANTHROPIC_API_KEY" in text_of(screen)
        assert not screen.query("#savekey-ANTHROPIC_API_KEY")
        assert not screen.query("#key-OPENAI_API_KEY")


async def test_first_run_preselects_provider_with_key_and_saves(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#provider", Select).value == "openai"
        shown = str(screen.query_one("#assistant", Static).render())
        assert "openai:gpt-6-sol" in shown
        assert "$2.00 in / $10.00 out per 1M tokens" in shown
        assert "openai:gpt-6-luna" in str(
            screen.query_one("#classifier", Static).render()
        )
        assert SENTINEL not in text_of(screen)
        screen.query_one("#save", Button).press()
        await pilot.pause()
    saved = system.read_system()
    assert saved is not None
    assert saved.provider == "openai"
    assert saved.assistant_model == "openai:gpt-6-sol"
    assert saved.assistant_thinking is None
    assert saved.classifier_model == "openai:gpt-6-luna"
    assert saved.recommendation_seen == system.RECOMMENDED_REVISION
    assert app.result is True


async def test_provider_change_refills_only_unedited_fields(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#thinking", Select).value == "medium"
        screen.query_one("#provider", Select).value = "openai"
        await pilot.pause()
        assert "openai:gpt-6-sol" in str(
            screen.query_one("#assistant", Static).render()
        )
        assert screen.query_one("#thinking", Select).value == "default"
        # an edit (thinking set by the user) is kept when the provider changes again
        screen.query_one("#thinking", Select).value = "high"
        await pilot.pause()
        screen.query_one("#provider", Select).value = "anthropic"
        await pilot.pause()
        assert screen.query_one("#thinking", Select).value == "high"
        screen.query_one("#save", Button).press()
        await pilot.pause()
    saved = system.read_system()
    assert saved is not None
    assert (saved.provider, saved.assistant_thinking) == ("anthropic", "high")
    assert saved.assistant_model == "openai:gpt-6-sol"  # edited screen keeps old fields


def test_thinking_choices_match_what_a_project_config_accepts():
    from hunches import files
    from hunches.screens.system import EFFORTS

    for effort in EFFORTS:
        assert (
            files.Config(
                assistant_model="anthropic:claude-sonnet-5-5",
                classifier_model="anthropic:claude-haiku-4-5",
                assistant_thinking=effort,
            ).assistant_thinking
            == effort
        )
    for rec in system.RECOMMENDED.values():
        assert rec["thinking"] is None or rec["thinking"] in EFFORTS


async def test_model_rows_end_with_recommended_or_differs_and_unpriced_row(
    monkeypatch,
):
    from hunches import models

    monkeypatch.setattr(models, "known_models", lambda embedding=False: ["anthropic:x"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert not screen.query("#differs") and not screen.query("#pricewarn")

        def row(name):
            return str(screen.query_one(f"#{name}", Static).render())

        assert row("assistant").rstrip().endswith("RECOMMENDED")
        assert "DIFFERS" not in row("assistant")
        assert row("classifier").rstrip().endswith("RECOMMENDED")
        screen.query_one("#pick-classifier", Button).press()
        await pilot.pause()
        await pilot.press("down", "enter")  # Other...
        await pilot.pause()
        app.screen.query_one("#other", Input).value = "anthropic:mystery-9"
        await pilot.press("enter")
        await pilot.pause()
        assert "anthropic:mystery-9" in row("classifier")
        assert "DIFFERS FROM RECOMMENDED" in row("classifier")
        # the unpriced warning is its own line in that row, not a separate widget
        first, second = row("classifier").splitlines()
        assert "no price" not in first
        assert second.strip() == "no price: cost will show ?"
        assert row("assistant").rstrip().endswith("RECOMMENDED")
        # thinking differing from the recommendation makes the assistant row differ
        screen.query_one("#thinking", Select).value = "high"
        await pilot.pause()
        assert "DIFFERS FROM RECOMMENDED" in row("assistant")
        screen.query_one("#reset", Button).press()
        await pilot.pause()
        assert row("classifier").rstrip().endswith("RECOMMENDED")
        assert row("assistant").rstrip().endswith("RECOMMENDED")
        assert "no price" not in row("classifier")


async def test_price_note_says_sidebar_only_in_rail_mode(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    for width, word in ((80, "the header shows"), (120, "the sidebar shows")):
        app = Host()
        async with app.run_test(size=(width, 30)) as pilot:
            await pilot.pause()
            assert word in text_of(app.screen)


def existing(**kw) -> system.System:
    base: dict[str, Any] = {
        "provider": "anthropic",
        "assistant_model": "anthropic:claude-sonnet-5-5",
        "assistant_thinking": "medium",
        "classifier_model": "anthropic:claude-haiku-4-5",
        "recommendation_seen": 1,
    }
    return system.System(**{**base, **kw})


async def test_edit_shows_settings_keeps_projects_and_stores_and_cancel_writes_nothing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    project = tmp_path / "proj"
    (project / ".hunches").mkdir(parents=True)
    config = project / ".hunches" / "config.toml"
    config.write_text('classifier_model = "keep:me"\n')
    system.write_system(
        existing(
            classifier_model="anthropic:claude-opus-4-5",
            recommendation_seen=0,
            projects=[
                system.Project(path=str(project), last_opened="2026-01-01T00:00:00Z")
            ],
            s3_stores=[
                system.Store(name="s", bucket="b", index="i", embedding_model="e")
            ],
        )
    )
    before = system._path().read_text()
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert "Welcome" not in text_of(screen)
        assert "anthropic:claude-opus-4-5" in str(
            screen.query_one("#classifier", Static).render()
        )
        assert "DIFFERS FROM RECOMMENDED" in str(
            screen.query_one("#classifier", Static).render()
        )
        assert "Existing projects keep their models" in text_of(screen)
        screen.query_one("#cancel", Button).press()
        await pilot.pause()
        assert app.result is False
    assert system._path().read_text() == before

    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#reset", Button).press()
        await pilot.pause()
        app.screen.query_one("#save", Button).press()
        await pilot.pause()
        assert app.result is True
    saved = system.read_system()
    assert saved is not None
    assert saved.classifier_model == "anthropic:claude-haiku-4-5"
    assert (
        saved.recommendation_seen == 0
    )  # only the modal acknowledges a recommendation
    assert [p.path for p in saved.projects] == [str(project)]
    assert [s.name for s in saved.s3_stores] == ["s"]
    assert config.read_text() == 'classifier_model = "keep:me"\n'


async def test_stores_panel_renames_and_deletes_stores_immediately(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    system.write_system(existing())
    system.add_store("one", "bucket1", "idx1", None, "openai:text-embedding-3-small")
    system.add_store(
        "two", "bucket2", "idx2", "eu-west-1", "openai:text-embedding-3-small"
    )
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert "bucket1" in text_of(screen) and "idx2" in text_of(screen)
        box = screen.query_one("#store-0", Input)
        assert box.value == "one"
        box.value = "uno"
        box.focus()
        await pilot.press("enter")
        await pilot.pause()
        stores = saved_stores()
        assert [s.name for s in stores] == ["uno", "two"]
        # a taken name is refused with a message and nothing changes
        screen.query_one("#store-1", Input).value = "uno"
        screen.query_one("#store-1", Input).focus()
        await pilot.press("enter")
        await pilot.pause()
        assert "already exists" in text_of(screen)
        screen.query_one("#delstore-0", Button).press()
        await pilot.pause()
        assert [s.name for s in saved_stores()] == ["two"]
        assert not screen.query("#store-1")
        assert screen.query_one("#store-0", Input).value == "two"


class ModalHost(App):
    CSS_PATH = Host.CSS_PATH
    result = "unset"

    def got(self, saved):
        self.result = saved

    def on_mount(self):
        self.register_theme(HUNCHES)
        self.theme = "hunches"
        self.push_screen(RecommendationModal(stored()), self.got)


@pytest.fixture
def old_system(tmp_path, monkeypatch):
    project = tmp_path / "proj" / ".hunches"
    project.mkdir(parents=True)
    (project / "config.toml").write_text('classifier_model = "keep:me"\n')
    monkeypatch.chdir(tmp_path / "proj")
    system.write_system(
        existing(
            assistant_model="anthropic:claude-opus-4-5",
            assistant_thinking=None,
            recommendation_seen=0,
        )
    )
    return project / "config.toml"


async def test_modal_shows_old_to_new_with_prices_and_use_new_adopts_recommendation(
    old_system,
):
    app = ModalHost()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        shown = text_of(app.screen)
        assert (
            panel_title(app.screen.query_one("#modal-box"))[0]
            == "Recommended models changed"
        )
        assert "anthropic:claude-opus-4-5" in shown
        assert "$5.00 in / $25.00 out per 1M tokens" in shown
        assert "anthropic:claude-sonnet-5-5" in shown
        assert "$2.00 in / $10.00 out per 1M tokens" in shown
        assert "Existing projects keep their models" in shown
        assert "thinking" in shown and "provider default" in shown and "medium" in shown
        assert "unchanged" in shown  # the classifier did not change
        app.screen.query_one("#use-new", Button).press()
        await pilot.pause()
    saved = system.read_system()
    assert saved is not None
    assert saved.assistant_model == "anthropic:claude-sonnet-5-5"
    assert saved.assistant_thinking == "medium"
    assert saved.recommendation_seen == system.RECOMMENDED_REVISION
    assert old_system.read_text() == 'classifier_model = "keep:me"\n'


async def test_modal_keep_mine_only_acknowledges(old_system):
    app = ModalHost()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one("#keep-mine", Button).press()
        await pilot.pause()
    saved = system.read_system()
    assert saved is not None
    assert saved.assistant_model == "anthropic:claude-opus-4-5"
    assert saved.recommendation_seen == system.RECOMMENDED_REVISION
    assert old_system.read_text() == 'classifier_model = "keep:me"\n'


async def test_fits_80x24_with_keys_models_stores_and_save_visible(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    system.write_system(existing())
    system.add_store("one", "b", "i", None, "e")
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        for selector in ("#save", "#cancel", "#savekey-OPENAI_API_KEY", "#reset"):
            region = screen.query_one(selector).region
            assert region.height and region.right <= 80 and region.bottom <= 24, (
                selector
            )


async def test_modal_groups_now_and_new_lines_and_focuses_use_new(old_system):
    system.write_system(stored().model_copy(update={"classifier_model": "x:old"}))
    app = ModalHost()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        modal = app.screen
        assert modal.focused is modal.query_one("#use-new", Button)
        lines = [str(w.render()) for w in modal.query(Static)]
        assert any("now" in t and "anthropic:claude-opus-4-5" in t for t in lines)
        assert any("new" in t and "anthropic:claude-sonnet-5-5" in t for t in lines)
        assert any("now" in t and "x:old" in t for t in lines)
        assert any("new" in t and "anthropic:claude-haiku-4-5" in t for t in lines)
        assert not any("unchanged" in t for t in lines)
