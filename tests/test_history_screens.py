"""UI for the edit history (spec 004, task 08): undo/redo buttons, the History modal, the external-change notice."""

import pytest
import test_taxonomy_screen as taxonomy_tests
from pydantic_ai.messages import ModelRequest
from pydantic_ai.models.function import FunctionModel
from test_brief import rows as seed_rows
from test_brief import setup as brief_setup
from test_taxonomy_screen import edits as tax_edits
from test_taxonomy_screen import setup as tax_setup
from test_taxonomy_screen import start
from textual import events
from textual.widgets import Button, DataTable, Input, Select, Static, TextArea

from hunches import candidates, files, history
from hunches.app import HunchesApp
from hunches.screens.brief import BriefScreen, write_seeds
from hunches.screens.history import ExternalNotice, HistoryScreen, NeedsVersionScreen
from hunches.screens.project_settings import ProjectSettingsScreen
from hunches.screens.projects import ProjectsScreen
from hunches.screens.system import SystemSettingsScreen

pytestmark = pytest.mark.usefixtures("system_ready")

calls = (
    taxonomy_tests.calls
)  # the autouse fixture that stubs every TaxonomyScreen's model


def edit_lines(stage: str) -> list[str]:
    """Summaries of the YOU EDITED lines recorded in a stage's chat, in order."""
    return [
        (m.metadata or {})["summary"]
        for m in files.load_chat(stage)
        if isinstance(m, ModelRequest) and (m.metadata or {}).get("hunches") == "edit"
    ]


def label(screen, button: str) -> str:
    return str(screen.query_one(button, Button).label)


class Counter:
    """A model that counts its invocations: undo, redo and restore must never reach it."""

    def __init__(self):
        self.calls = 0

    async def stream(self, messages, info):
        self.calls += 1
        yield "x"

    def model(self):
        return FunctionModel(stream_function=self.stream)


# ---- Brief: seed list ------------------------------------------------------------------


async def test_brief_undo_redo_buttons_step_the_seed_list_without_a_model_call(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    write_seeds(["a"], summary="Seed added")
    write_seeds(["a", "b"], summary="Seed added")
    counter = Counter()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.agent.model = counter.model()
        assert label(screen, "#undo") == "Undo  F6"
        assert label(screen, "#redo") == "Redo  F7"
        assert not screen.query_one("#undo", Button).disabled
        assert screen.query_one("#redo", Button).disabled

        await pilot.click("#undo", offset=(2, 0))
        await pilot.pause()
        assert candidates.read_seeds() == ["a"]
        assert seed_rows(screen) == ["a"]
        assert (
            str(screen.query_one("#hist-note", Static).render()) == "Undid: Seed added"
        )
        assert not screen.query_one("#redo", Button).disabled
        assert edit_lines("brief") == ["Undid: Seed added"]

        await pilot.press("f7")
        await pilot.pause()
        assert candidates.read_seeds() == ["a", "b"]
        assert seed_rows(screen) == ["a", "b"]
        assert (
            str(screen.query_one("#hist-note", Static).render()) == "Redid: Seed added"
        )
        assert screen.query_one("#redo", Button).disabled
        assert edit_lines("brief") == ["Undid: Seed added", "Redid: Seed added"]

        await pilot.press("f6")
        await pilot.pause()
        assert candidates.read_seeds() == ["a"]
    assert counter.calls == 0


async def test_brief_undo_is_off_while_a_seed_is_being_edited(tmp_path, monkeypatch):
    brief_setup(tmp_path, monkeypatch)
    write_seeds(["a"], summary="Seed added")
    write_seeds(["a", "b"], summary="Seed added")
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.query_one("#seed-list").focus()
        await pilot.press("a")
        await pilot.pause()
        assert screen.editor is not None
        assert screen.query_one("#undo", Button).disabled
        await pilot.press("f6")
        await pilot.pause()
        assert candidates.read_seeds() == ["a", "b"]
        await pilot.press("escape")
        await pilot.pause()
        assert not screen.query_one("#undo", Button).disabled


async def test_brief_note_clears_on_the_next_edit(tmp_path, monkeypatch):
    brief_setup(tmp_path, monkeypatch)
    write_seeds(["a"], summary="Seed added")
    write_seeds(["a", "b"], summary="Seed added")
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        await pilot.press("f6")
        await pilot.pause()
        assert screen.query_one("#hist-note", Static).display
        screen.query_one("#seed-list").focus()
        await pilot.press("d")
        await pilot.pause()
        assert not screen.query_one("#hist-note", Static).display


# ---- Taxonomy: Labels and Prompt panels --------------------------------------------------


def tax_yaml(*names: str) -> str:
    return files.taxonomy_yaml(
        files.Taxonomy(
            mode="single",
            labels=[files.Label(name=n, description=n.upper()) for n in names],
        )
    )


def prompt_history():
    history.save("taxonomy", tax_yaml("a", "b"), "user", "Taxonomy written")
    history.save("prompt", "# Prompt\nOne.\n", "user", "Prompt: 1 line changed")
    history.save("prompt", "# Prompt\nTwo.\n", "user", "Prompt: 2 lines changed")


async def test_taxonomy_prompt_panel_undo_redo_leaves_labels_alone(
    tmp_path, monkeypatch, calls
):
    tax_setup(tmp_path, monkeypatch)
    prompt_history()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        before = len(calls.prompts)
        assert label(screen, "#undo-prompt") == "Undo  F6"
        assert label(screen, "#redo-prompt") == "Redo  F7"
        assert not screen.query_one("#undo-prompt", Button).disabled
        assert screen.query_one("#redo-prompt", Button).disabled
        assert screen.query_one(
            "#undo-labels", Button
        ).disabled  # nothing before the first write
        await pilot.click("#undo-prompt", offset=(2, 0))
        await pilot.pause()
        assert files.read_text("prompt.md") == "# Prompt\nOne.\n"
        assert screen.prompt == "# Prompt\nOne.\n"
        note = str(screen.query_one("#note", Static).render())
        assert note == "Undid: Prompt: 2 lines changed"
        assert not screen.query_one("#redo-prompt", Button).disabled
        assert tax_edits()[-1].metadata["summary"] == "Undid: Prompt: 2 lines changed"
        await pilot.click("#redo-prompt", offset=(2, 0))
        await pilot.pause()
        assert files.read_text("prompt.md") == "# Prompt\nTwo.\n"
        assert (
            str(screen.query_one("#note", Static).render())
            == "Redid: Prompt: 2 lines changed"
        )
        assert files.read_text("taxonomy.yaml") == tax_yaml("a", "b")
        assert len(calls.prompts) == before  # no model call


async def test_taxonomy_f6_acts_on_the_focused_panel(tmp_path, monkeypatch, calls):
    tax_setup(tmp_path, monkeypatch)
    prompt_history()
    history.save(
        "taxonomy",
        tax_yaml("a", "b").replace("A", "AA"),
        "user",
        "Labels: a description",
    )
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        screen.query_one("#chat-input", Input).focus()
        await pilot.press("f6")
        await pilot.pause()
        assert (
            files.read_text("prompt.md") == "# Prompt\nTwo.\n"
        )  # chat focused: nothing
        assert files.read_text("taxonomy.yaml") == tax_yaml("a", "b").replace("A", "AA")
        screen.query_one("#edit-prompt", Button).focus()
        await pilot.press("f6")
        await pilot.pause()
        assert files.read_text("prompt.md") == "# Prompt\nOne.\n"
        assert files.read_text("taxonomy.yaml") == tax_yaml("a", "b").replace("A", "AA")
        screen.query_one("#edit-labels", Button).focus()
        await pilot.press("f6")
        await pilot.pause()
        assert files.read_text("taxonomy.yaml") == tax_yaml("a", "b")
        assert files.read_text("prompt.md") == "# Prompt\nOne.\n"
        assert (
            str(screen.query_one("#note", Static).render())
            == "Undid: Labels: a description"
        )


async def test_taxonomy_undo_is_off_while_an_editor_is_open(
    tmp_path, monkeypatch, calls
):
    tax_setup(tmp_path, monkeypatch)
    prompt_history()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        screen.query_one("#edit-prompt", Button).focus()
        await pilot.press("e")
        await pilot.pause()
        assert screen.edit == "prompt"
        assert screen.query_one("#undo-prompt", Button).disabled
        assert screen.query_one("#undo-labels", Button).disabled
        await pilot.press("f6")  # the text area's own select-line
        await pilot.pause()
        assert files.read_text("prompt.md") == "# Prompt\nTwo.\n"
        assert screen.query_one("#prompt-text", TextArea).text == "# Prompt\nTwo.\n"


async def label_a_gold_item():
    files.write_gold([files.GoldRow(id="1", text="t", labels=["a"], split="dev")])


async def test_taxonomy_undo_that_changes_labels_asks_for_a_new_version(
    tmp_path, monkeypatch, calls
):
    tax_setup(tmp_path, monkeypatch)
    history.save("taxonomy", tax_yaml("a", "b"), "user", "Taxonomy written")
    history.save("taxonomy", tax_yaml("a", "b", "c"), "user", "Labels: +c")
    await label_a_gold_item()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await pilot.click("#undo-labels", offset=(2, 0))
        await pilot.pause()
        modal = pilot.app.screen
        assert isinstance(modal, NeedsVersionScreen)
        why = str(modal.query_one("#why", Static).render())
        assert "version 1" in why and "cleared" in why
        assert (
            str(modal.query_one("#archive", Button).label)
            == "Archive as version 1 and undo"
        )
        assert modal.focused is modal.query_one("#cancel", Button)
        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.screen is screen
        assert files.read_text("taxonomy.yaml") == tax_yaml(
            "a", "b", "c"
        )  # nothing changed
        await pilot.click("#undo-labels", offset=(2, 0))
        await pilot.pause()
        await pilot.click("#archive", offset=(2, 0))
        await pilot.pause()
        assert pilot.app.screen is screen
        assert files.read_text("taxonomy.yaml") == tax_yaml("a", "b")
        assert [r.labels for r in files.read_gold()] == [
            []
        ]  # D12: cleared on the same items
        assert [v["version"] for v in files.list_versions()] == [1]
        assert [x.name for x in screen.taxonomy.labels] == ["a", "b"]


async def test_taxonomy_undo_of_a_version_start_says_the_labels_come_back(
    tmp_path, monkeypatch, calls
):
    tax_setup(tmp_path, monkeypatch)
    history.save("taxonomy", tax_yaml("a", "b"), "user", "Taxonomy written")
    await label_a_gold_item()
    history.start_new_version(
        files.Taxonomy.model_validate(
            {"mode": "single", "labels": [{"name": "c"}, {"name": "d"}]}
        ),
        "Taxonomy version 2 started",
    )
    files.write_gold([files.GoldRow(id="1", text="t", labels=["c"], split="dev")])
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await pilot.click("#undo-labels", offset=(2, 0))
        await pilot.pause()
        modal = pilot.app.screen
        assert isinstance(modal, NeedsVersionScreen)
        why = str(modal.query_one("#why", Static).render())
        assert "come back" in why and "version 2" in why
        await pilot.click("#archive", offset=(2, 0))
        await pilot.pause()
        assert files.read_text("taxonomy.yaml") == tax_yaml("a", "b").replace("A", "A")
        assert [r.labels for r in files.read_gold()] == [
            ["a"]
        ]  # version 1's labels are back
        assert [x.name for x in screen.taxonomy.labels] == ["a", "b"]


# ---- History modal (F8) ----------------------------------------------------------------------


def mixed_history():
    """Five log entries: seeds, prompt, prompt, an approval, seeds (oldest first)."""
    write_seeds(["a"], summary="Seed added")
    history.save("prompt", "P1", "user", "Prompt: 1 line changed")
    history.save("prompt", "P2", "assistant", "Prompt written by assistant")
    history.approval(1, "seeds_approved", {}, "Approved: 1 seeds")
    write_seeds(["a", "b"], summary="Seed added")


def cells(table: DataTable, row: int) -> list[str]:
    return [str(c.plain if hasattr(c, "plain") else c) for c in table.get_row_at(row)]


def preview(modal) -> str:
    return str(modal.query_one("#preview", Static).render())


async def history_modal(pilot):
    await pilot.press("f8")
    await pilot.pause()
    modal = pilot.app.screen
    assert isinstance(modal, HistoryScreen)
    return modal


async def test_f8_opens_the_timeline_newest_first_with_source_badges(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    mixed_history()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        modal = await history_modal(pilot)
        table = modal.query_one("#timeline", DataTable)
        assert table.row_count == 5
        assert [c.label.plain for c in table.columns.values()] == [
            "Time",
            "File",
            "Source",
            "Summary",
        ]
        assert cells(table, 0)[1:] == ["seeds.csv", " YOU ", "Seed added  (current)"]
        assert cells(table, 1)[1:] == ["·", " APPROVAL ", "Approved: 1 seeds"]
        assert cells(table, 2)[1:] == [
            "prompt.md",
            " ASSISTANT ",
            "Prompt written by assistant  (current)",
        ]
        assert cells(table, 3)[1:] == ["prompt.md", " YOU ", "Prompt: 1 line changed"]
        assert cells(table, 4)[1:] == ["seeds.csv", " YOU ", "Seed added"]
        assert "newest first · 5 entries" in str(modal.query_one("#count").render())
        assert modal.focused is table
        assert str(modal.query_one("#close", Button).label) == "Close  Esc"
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, BriefScreen)


async def test_history_file_filter_hides_other_files_and_the_event_rows(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    mixed_history()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        modal = await history_modal(pilot)
        modal.query_one("#file", Select).value = "prompt.md"
        await pilot.pause()
        table = modal.query_one("#timeline", DataTable)
        assert table.row_count == 2
        assert {cells(table, i)[1] for i in range(2)} == {"prompt.md"}
        assert "newest first · 2 entries" in str(modal.query_one("#count").render())
        modal.query_one("#file", Select).value = "all"
        await pilot.pause()
        assert table.row_count == 5


async def test_history_preview_is_a_diff_against_the_previous_entry_v_shows_the_text(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    mixed_history()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        modal = await history_modal(pilot)
        await pilot.press("down", "down")  # prompt P2
        await pilot.pause()
        diff = preview(modal)
        assert "-P1" in diff and "+P2" in diff
        assert "this is the current text" in str(
            modal.query_one("#preview-panel .panel-subtitle").render()
        )
        assert str(modal.query_one("#mode", Button).label) == "Show text  v"
        await pilot.press("v")
        await pilot.pause()
        assert preview(modal).strip() == "P2"
        assert str(modal.query_one("#mode", Button).label) == "Show diff  v"
        await pilot.press("v")
        await pilot.pause()
        assert "+P2" in preview(modal)


async def test_history_event_row_shows_details_and_has_nothing_to_restore(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    mixed_history()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        modal = await history_modal(pilot)
        assert modal.query_one("#restore", Button).disabled  # the current seeds
        await pilot.press("down")  # the approval
        await pilot.pause()
        assert "An approval is not a file" in preview(modal)
        assert modal.query_one("#restore", Button).disabled
        assert modal.query_one("#mode", Button).disabled


async def test_history_restore_makes_the_file_match_and_is_itself_undoable(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    mixed_history()
    counter = Counter()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BriefScreen)
        screen.agent.model = counter.model()
        modal = await history_modal(pilot)
        for _ in range(4):
            await pilot.press("down")  # the first seeds edit
        await pilot.pause()
        restore = modal.query_one("#restore", Button)
        assert not restore.disabled
        assert str(restore.label) == "Restore this  r"
        await pilot.press("r")
        await pilot.pause()
        assert app.screen is screen
        assert candidates.read_seeds() == ["a"]
        assert seed_rows(screen) == ["a"]
        last = history.entries("seeds")[-1]
        assert last["source"] == "restore"
        when = last["ts"]
        from datetime import datetime

        clock = datetime.fromisoformat(when).astimezone().strftime("%H:%M:%S")
        first = history.entries("seeds")[0]
        then = datetime.fromisoformat(first["ts"]).astimezone().strftime("%H:%M:%S")
        assert str(screen.query_one("#hist-note", Static).render()) == (
            f"Restored seeds.csv to {then}. Undo with F6."
        )
        assert clock  # the restore entry has a time
        assert edit_lines("brief")[-1] == last["summary"]
        await pilot.press("f6")  # a restore is a normal edit
        await pilot.pause()
        assert candidates.read_seeds() == ["a", "b"]
    assert counter.calls == 0


async def test_history_restore_is_allowed_on_a_baseline_row(tmp_path, monkeypatch):
    brief_setup(tmp_path, monkeypatch)
    files.write_text("seeds.csv", "seed\nz\n")  # an existing file the log has not seen
    write_seeds(["a"], summary="Seed added")  # save() logs the baseline first
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        modal = await history_modal(pilot)
        table = modal.query_one("#timeline", DataTable)
        assert cells(table, 1)[2] == " BASELINE "
        await pilot.press("down")
        await pilot.pause()
        assert not modal.query_one("#restore", Button).disabled
        await pilot.press("r")
        await pilot.pause()
        assert candidates.read_seeds() == ["z"]


async def test_history_restore_that_changes_labels_asks_first(
    tmp_path, monkeypatch, calls
):
    tax_setup(tmp_path, monkeypatch)
    history.save("taxonomy", tax_yaml("a", "b"), "user", "Taxonomy written")
    history.save("taxonomy", tax_yaml("a", "b", "c"), "user", "Labels: +c")
    await label_a_gold_item()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        modal = await history_modal(pilot)
        await pilot.press("down")  # the first taxonomy entry
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        ask = pilot.app.screen
        assert isinstance(ask, NeedsVersionScreen)
        assert (
            str(ask.query_one("#archive", Button).label)
            == "Archive as version 1 and restore"
        )
        await pilot.click("#archive", offset=(2, 0))
        await pilot.pause()
        assert pilot.app.screen is screen and not modal.is_attached
        assert files.read_text("taxonomy.yaml") == tax_yaml("a", "b")
        assert [r.labels for r in files.read_gold()] == [[]]
        assert [x.name for x in screen.taxonomy.labels] == ["a", "b"]


async def test_f8_does_nothing_while_an_editor_is_open_or_over_a_modal(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    mixed_history()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#seed-list").focus()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("f8")
        await pilot.pause()
        assert app.screen is screen
        await pilot.press("escape")
        await pilot.pause()
        modal = await history_modal(pilot)
        await pilot.press("f8")
        await pilot.pause()
        assert app.screen is modal  # not stacked on itself


async def test_function_keys_for_settings_and_projects_still_work(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for key, screen in (
            ("f3", ProjectSettingsScreen),
            ("f4", ProjectsScreen),
            ("f5", SystemSettingsScreen),
        ):
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, screen)
            app.pop_screen()
            await pilot.pause()
        assert isinstance(app.screen, BriefScreen)


# ---- external changes ----------------------------------------------------------------------


async def focus_again(pilot):
    pilot.app.post_message(events.AppFocus())
    await pilot.pause()
    await pilot.pause()


def notices(app) -> list[ExternalNotice]:
    return list(app.screen.query(ExternalNotice))


async def test_an_outside_edit_shows_one_notice_with_undo_history_dismiss(
    tmp_path, monkeypatch, calls
):
    tax_setup(tmp_path, monkeypatch)
    prompt_history()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        assert notices(pilot.app) == []
        files.write_text("prompt.md", "# Prompt\nEdited in an editor.\n")
        await focus_again(pilot)
        (notice,) = notices(pilot.app)
        assert "prompt.md changed outside hunches." in str(
            notice.query_one(".notice-text", Static).render()
        )
        assert [str(b.label) for b in notice.query(Button)] == [
            "Undo  F6",
            "History  F8",
            "Dismiss  Esc",
        ]
        assert (
            screen.prompt == "# Prompt\nEdited in an editor.\n"
        )  # the screen followed the file
        entry = history.entries("prompt")[-1]
        assert entry["source"] == "external"
        await focus_again(pilot)  # the same change is not announced twice
        assert len(notices(pilot.app)) == 1
        await pilot.press("escape")
        await pilot.pause()
        assert notices(pilot.app) == []
        await focus_again(pilot)
        assert notices(pilot.app) == []


async def test_notice_undo_reverts_to_the_entry_before_the_outside_edit(
    tmp_path, monkeypatch, calls
):
    tax_setup(tmp_path, monkeypatch)
    prompt_history()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        files.write_text("prompt.md", "outside")
        await focus_again(pilot)
        before = len(calls.prompts)
        await pilot.click("#notice-undo")
        await pilot.pause()
        assert files.read_text("prompt.md") == "# Prompt\nTwo.\n"
        assert screen.prompt == "# Prompt\nTwo.\n"
        assert notices(pilot.app) == []
        assert len(calls.prompts) == before


async def test_notice_history_button_opens_the_history_modal(
    tmp_path, monkeypatch, calls
):
    tax_setup(tmp_path, monkeypatch)
    prompt_history()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await start(pilot.app, pilot)
        files.write_text("prompt.md", "outside")
        await focus_again(pilot)
        await pilot.click("#notice-history")
        await pilot.pause()
        modal = pilot.app.screen
        assert isinstance(modal, HistoryScreen)
        table = modal.query_one("#timeline", DataTable)
        assert cells(table, 0)[2] == " EXTERNAL "


async def test_a_change_made_while_a_stage_is_left_shows_on_the_next_stage(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    mixed_history()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        files.write_text("seeds.csv", "seed\nq\n")
        app.goto_stage(2)
        await pilot.pause()
        await pilot.pause()
        (notice,) = notices(app)
        assert "seeds.csv changed outside hunches." in str(
            notice.query_one(".notice-text", Static).render()
        )
        app.goto_stage(1)  # navigating clears it
        await pilot.pause()
        await pilot.pause()
        assert notices(app) == []
        assert seed_rows(app.screen) == ["q"]


async def test_history_is_a_rail_row_and_a_footer_key_only_without_the_rail(
    tmp_path, monkeypatch
):
    from test_rail import footer_keys, rail_text

    brief_setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert any("History" in line and "F8" in line for line in rail_text(app))
        assert "f8" not in footer_keys(app)
        await pilot.resize_terminal(99, 30)
        await pilot.pause()
        assert "f8" in footer_keys(app)
        assert {"f6", "f7"} <= footer_keys(app)


async def test_f6_undoes_an_outside_edit_announced_on_a_screen_that_has_no_undo(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    mixed_history()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(2)  # Search binds no F6
        await pilot.pause()
        files.write_text("prompt.md", "outside")
        await focus_again(pilot)
        assert len(notices(app)) == 1
        await pilot.press("f6")
        await pilot.pause()
        assert files.read_text("prompt.md") == "P2"
        assert notices(app) == []


async def test_a_change_made_while_hunches_was_closed_is_announced_when_the_project_opens(
    tmp_path, monkeypatch
):
    brief_setup(tmp_path, monkeypatch)
    mixed_history()
    files.write_text("prompt.md", "edited while closed")  # the log has not seen this
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        (notice,) = notices(app)
        assert "prompt.md changed outside hunches." in str(
            notice.query_one(".notice-text", Static).render()
        )
        assert history.entries("prompt")[-1]["source"] == "external"


async def test_the_rail_row_for_history_is_dimmed_while_an_editor_is_open(
    tmp_path, monkeypatch
):
    from hunches.app import StatusHeader

    def history_style(app) -> str:
        content = app.screen.query_one(StatusHeader).render()
        at = str(content).index("History")
        return next(s.style for s in content.spans if s.start <= at < s.end)

    brief_setup(tmp_path, monkeypatch)
    write_seeds(["a"], summary="Seed added")
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert "text-muted" in history_style(app)
        app.screen.query_one("#seed-list").focus()
        await pilot.press("a")
        await pilot.pause()
        app.screen.query_one(StatusHeader).refresh_cost()
        assert "text-disabled" in history_style(app)
