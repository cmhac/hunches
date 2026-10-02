import pytest
from textual.widgets import DataTable, Input, SelectionList, Static

from hunches import files
from hunches.app import HunchesApp
from hunches.screens.browse import BrowseScreen

ROWS = [
    {"id": "0", "text": "Apples are red", "labels": ["a"], "max_similarity": 0.9},
    {"id": "1", "text": "Bananas are YELLOW", "labels": ["b"], "max_similarity": 0.8},
    {
        "id": "2",
        "text": "Red cars\nare fast",
        "labels": ["a", "b"],
        "max_similarity": 0.7,
    },
    {"id": "3", "text": "Nothing here", "labels": ["off_topic"], "max_similarity": 0.6},
    {
        "id": "4",
        "text": "broken red",
        "labels": [],
        "max_similarity": 0.6,
        "error": "x",
    },
]


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.write_config(
        files.Config(corpus_dir="c", embedding_model="m", cheap_model="test")
    )
    files.write_taxonomy(
        files.Taxonomy(
            mode="multi", labels=[files.Label(name="a"), files.Label(name="b")]
        )
    )
    files.write_jsonl("results.jsonl", ROWS)


async def open_browse(pilot, app):
    await pilot.pause()
    app.goto_stage(9)
    await pilot.pause()
    assert isinstance(app.screen, BrowseScreen)
    return app.screen


def ids(screen):
    return [screen.rows[i]["id"] for i in screen.shown]


def count(screen):
    return str(screen.query_one("#count", Static).render())


async def test_all_rows_skip_errors():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_browse(pilot, app)
        assert ids(screen) == ["0", "1", "2", "3"]
        assert screen.query_one("#table", DataTable).row_count == 4
        assert "Showing 4 of 4" in count(screen)


async def test_label_filter_any_and_off_topic():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_browse(pilot, app)
        labels = screen.query_one("#labels", SelectionList)
        labels.select("a")
        await pilot.pause()
        assert ids(screen) == ["0", "2"]
        labels.select("b")
        await pilot.pause()
        assert ids(screen) == ["0", "1", "2"]
        labels.deselect_all()
        labels.select("off_topic")
        await pilot.pause()
        assert ids(screen) == ["3"]
        assert "Showing 1 of 4" in count(screen)


async def test_search_and_combined_and_empty():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_browse(pilot, app)
        search = screen.query_one("#search", Input)
        search.value = "yellow"
        await pilot.pause()
        assert ids(screen) == ["1"]
        search.value = "RED"
        await pilot.pause()
        assert ids(screen) == ["0", "2"]
        screen.query_one("#labels", SelectionList).select("b")
        await pilot.pause()
        assert ids(screen) == ["2"]
        search.value = "zzz"
        await pilot.pause()
        assert ids(screen) == []
        assert screen.query_one("#table", DataTable).row_count == 0
        assert "Showing 0 of 4" in count(screen)
        assert str(screen.query_one("#detail", Static).render()) == ""


async def test_row_selection_shows_full_text():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_browse(pilot, app)
        table = screen.query_one("#table", DataTable)
        table.focus()
        await pilot.press("down", "down")
        await pilot.pause()
        assert str(screen.query_one("#detail", Static).render()) == "Red cars\nare fast"


async def test_large_result_is_capped(monkeypatch):
    from hunches.screens import browse

    monkeypatch.setattr(browse, "MAX_ROWS", 2)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_browse(pilot, app)
        assert ids(screen) == ["0", "1"]
        assert "Showing 2 of 4 (4 match" in count(screen)
