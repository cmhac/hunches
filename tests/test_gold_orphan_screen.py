"""Spec 004 task 10: gold rows that left the candidate pool, on the Gold screen."""

import pytest
from conftest import panel_title
from test_gold_screen import gold_screen, project
from textual.widgets import Button, DataTable, Static

from hunches import files
from hunches.app import HunchesApp, current_status
from hunches.screens.gold import GoldRowsScreen, GoldScreen, RemoveGoldScreen

pytestmark = pytest.mark.usefixtures("system_ready")


@pytest.fixture(autouse=True)
def cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def text(widget) -> str:
    return str(widget.render())


def dev_with_orphans():
    """50 dev rows: x0-x3 labelled and x4-x5 unlabelled are not in the pool; 0-43 are, all labelled."""
    orphans = [
        files.GoldRow(
            id=f"x{i}", text=f"gone {i}", labels=["b"] if i < 4 else [], split="dev"
        )
        for i in range(6)
    ]
    rest = [
        files.GoldRow(id=str(i), text=f"item {i}", labels=["a"], split="dev")
        for i in range(44)
    ]
    project(n=80, gold=orphans + rest)
    state = files.read_state()
    state.dev_done = True  # Tuning was approved, so the dev set counts as something that was complete
    files.write_state(state)


def test_and_dev():
    """Test split: dev done; test rows tx0 (labelled) and tx1 (unlabelled) are not in the pool."""
    dev = [
        files.GoldRow(id=str(i), text=f"item {i}", labels=["a"], split="dev")
        for i in range(50)
    ]
    test = [
        files.GoldRow(
            id=f"tx{i}", text=f"gone {i}", labels=["b"] if i == 0 else [], split="test"
        )
        for i in range(2)
    ] + [
        files.GoldRow(id=str(i), text=f"item {i}", labels=["a"], split="test")
        for i in range(50, 98)
    ]
    project(n=120, gold=dev + test)
    state = files.read_state()
    state.dev_done = True
    files.write_state(state)


async def start(pilot, app):
    await pilot.pause()
    screen = gold_screen(app)
    await pilot.pause()
    return screen


async def test_orphan_banner_subtitle_and_badge():
    dev_with_orphans()
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        screen = await start(pilot, app)
        assert text(screen.query_one("#orphan-banner", Static)) == (
            "ORPHANED: 6 of 50 dev rows are no longer in the candidate pool (4 labelled)."
        )
        stale = screen.query_one("#remove-stale", Button)
        assert str(stale.label) == "Remove stale rows  x"
        assert (
            panel_title(screen.query_one("#counts-panel"))[1] == "48 of 50 · 6 orphaned"
        )
        # the first unlabelled row is x4, which is orphaned
        assert "ORPHANED" in panel_title(screen.query_one("#item"))[1]
        await pilot.press("right", "right")  # x4 -> x5 -> the first row in the pool
        assert "ORPHANED" not in panel_title(screen.query_one("#item"))[1]
        # orphans keep their labels and count as labelled until removed; x4 and x5 have none
        assert screen.query_one("#finish", Button).disabled


async def test_no_orphans_no_banner_and_the_rows_button_is_there():
    project(n=60, gold=[])
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        screen = await start(pilot, app)
        assert not screen.query_one("#orphans").display
        assert str(screen.query_one("#show-rows", Button).label) == "Rows  r"
        assert panel_title(screen.query_one("#counts-panel"))[1] == "0 of 50"


async def test_x_asks_first_and_cancel_changes_nothing():
    dev_with_orphans()
    before = files.read_text("gold.jsonl")
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        screen = await start(pilot, app)
        await pilot.press("x")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, RemoveGoldScreen)
        assert modal.text == (
            "6 rows are no longer in the candidate pool. 4 of them are labelled; those 4 "
            "labels are discarded. The rows are kept in gold_removed.jsonl and are never "
            "drawn again."
        )
        assert str(modal.query_one("#cancel", Button).label) == "Cancel  Esc"
        assert str(modal.query_one("#remove", Button).label) == "Remove 6 rows"
        assert app.focused is modal.query_one("#cancel")
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is screen
    assert files.read_text("gold.jsonl") == before
    assert files.read_text("gold_removed.jsonl") is None


async def test_confirmed_removal_then_draw_replacements():
    dev_with_orphans()
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        screen = await start(pilot, app)
        await pilot.press("x")
        await pilot.pause()
        await pilot.click("#remove")
        await pilot.pause()
        assert app.screen is screen
        removed = files.read_jsonl("gold_removed.jsonl")
        assert sorted(r["id"] for r in removed) == [f"x{i}" for i in range(6)]
        assert {r["reason"] for r in removed} == {"no longer in the candidate pool"}
        assert len(files.read_gold()) == 44
        assert len(screen.rows) == 44
        assert text(screen.query_one("#info", Static)) == (
            "Removed 6 stale rows (4 labels discarded). The set has 44 of 50 rows. "
            "Draw 6 replacements to continue."
        )
        assert not screen.query_one("#orphans").display
        assert screen.query_one("#finish", Button).disabled
        more = screen.query_one("#more", Button)
        assert str(more.label) == "Draw 6 replacements  d"
        assert more.variant == "primary"
        # the app's status follows straight away: stage 4 is incomplete, resume goes back to it
        assert current_status()[4] == ("incomplete", "44 of 50 rows")
        assert files.first_incomplete_stage() == 4

        await pilot.press("d")
        await pilot.pause()
        assert len(screen.rows) == 50
        new = screen.rows[44:]
        assert all(r.labels == [] for r in new)
        assert not {r.id for r in new} & {r["id"] for r in removed}
        assert (
            len(files.read_jsonl("gold_removed.jsonl")) == 6
        )  # the draw never writes it
        assert str(screen.query_one("#more", Button).label) == "Draw 10 more  d"
        assert not text(screen.query_one("#info", Static))
        assert screen.query_one("#finish", Button).disabled  # six rows to label


async def test_coming_back_after_a_removal_does_not_draw_by_itself():
    dev_with_orphans()
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        screen = await start(pilot, app)
        await pilot.press("x")
        await pilot.pause()
        await pilot.click("#remove")
        await pilot.pause()
        app.goto_stage(2)
        await pilot.pause()
        app.goto_stage(4)
        await pilot.pause()
        again = gold_screen(app)
        assert again is not screen
        assert len(again.rows) == 44
        assert len(files.read_gold()) == 44
        assert str(again.query_one("#more", Button).label) == "Draw 6 replacements  d"
        assert again.query_one("#finish", Button).disabled


async def test_test_split_shows_the_held_out_warning_even_for_unlabelled_rows():
    test_and_dev()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(pilot, app)
        assert isinstance(screen, GoldScreen) and screen.split == "test"
        await pilot.press("x")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, RemoveGoldScreen)
        assert modal.text.startswith(
            "2 rows are no longer in the candidate pool. 1 of them is labelled; that 1 label is discarded."
        )
        assert (
            "Test rows are held out so that the test result is an honest estimate."
            in modal.text
        )
        assert modal.text.endswith(
            "Do not remove rows because the classifier got them wrong."
        )
        await pilot.click("#remove")
        await pilot.pause()
        assert text(screen.query_one("#info", Static)) == (
            "Removed 2 stale rows (1 label discarded). The set has 48 of 50 rows. "
            "Draw 2 replacements to continue. The test result is stale until you re-run it."
        )


async def test_the_warning_is_shown_for_a_test_row_with_no_labels_at_all():
    test_and_dev()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await start(pilot, app)
        app.push_screen(
            RemoveGoldScreen([r for r in files.read_gold() if r.id == "tx1"])
        )
        await pilot.pause()
        ask = app.screen
        assert isinstance(ask, RemoveGoldScreen)
        assert "held out" in ask.text
        assert ask.text.startswith(
            "1 row is no longer in the candidate pool. It has no labels; no labels are discarded."
        )


async def test_rows_modal_lists_every_row_and_removes_the_selected_one():
    dev_with_orphans()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(pilot, app)
        await pilot.press("r")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, GoldRowsScreen)
        assert text(modal.query_one("#summary", Static)) == (
            "50 rows · 48 labelled · 6 orphaned. Orphaned rows are not in the candidate pool any more."
        )
        table = modal.query_one("#rows", DataTable)
        assert table.row_count == 50
        first = [str(c) for c in table.get_row_at(0)]
        assert first[0] == "1" and "ORPHANED" in first[1] and first[3] == "gone 0"
        in_pool = [str(c) for c in table.get_row_at(6)]
        assert in_pool[1] == "in pool" and in_pool[3] == "item 0"
        unlabelled = [str(c) for c in table.get_row_at(4)]
        assert "unlabelled" in unlabelled[2]
        labels = {
            "remove-row": "Remove row  Del",
            "remove-stale": "Remove stale rows  x",
            "close": "Close  Esc",
        }
        for id_, label in labels.items():
            assert str(modal.query_one(f"#{id_}", Button).label) == label

        # Del on an in-pool row (the selected one) asks about that row alone
        table.move_cursor(row=6)
        await pilot.press("delete")
        await pilot.pause()
        ask = app.screen
        assert isinstance(ask, RemoveGoldScreen)
        assert ask.text.startswith(
            "1 row will be removed from the dev set. It is labelled; that 1 label is discarded."
        )
        assert str(ask.query_one("#remove", Button).label) == "Remove 1 row"
        await pilot.click("#remove")
        await pilot.pause()
        assert app.screen is modal
        assert table.row_count == 49
        assert [r["id"] for r in files.read_jsonl("gold_removed.jsonl")] == ["0"]
        assert len(files.read_gold()) == 49

        await pilot.press("x")  # the stale rows, from inside the modal
        await pilot.pause()
        assert isinstance(app.screen, RemoveGoldScreen)
        await pilot.click("#remove")
        await pilot.pause()
        assert table.row_count == 43
        assert modal.query_one("#remove-stale", Button).disabled
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is screen
        assert len(screen.rows) == 43  # the screen follows what the modal removed
        assert "Removed 7 rows" in text(screen.query_one("#info", Static))
        assert str(screen.query_one("#more", Button).label) == "Draw 7 replacements  d"


async def test_removal_and_drawing_make_no_model_call(monkeypatch):
    import pydantic_ai

    calls = []

    def boom(*a, **k):
        calls.append(a)
        raise AssertionError("the gold screen called a model")

    monkeypatch.setattr(pydantic_ai.Agent, "run", boom)
    monkeypatch.setattr(pydantic_ai.Agent, "run_stream", boom)
    dev_with_orphans()
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await start(pilot, app)
        await pilot.press("x")
        await pilot.pause()
        await pilot.click("#remove")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert len(files.read_gold()) == 50
    assert calls == []
