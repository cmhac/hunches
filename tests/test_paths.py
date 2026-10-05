from textual.app import App
from textual.widgets import Button, Input

from hunches.screens.paths import (
    BROWSE_LABEL,
    DirTree,
    PathInput,
    PathPicker,
    PathSuggester,
    browse,
)


def tree(tmp_path):
    for name in ["alpha", "alps", "beta", ".hidden", "alpha/inner"]:
        (tmp_path / name).mkdir(parents=True)
    (tmp_path / "alfile.txt").write_text("x")
    return tmp_path


async def test_completes_last_segment_with_trailing_slash(tmp_path):
    base = tree(tmp_path)
    assert await PathSuggester().get_suggestion(f"{base}/be") == f"{base}/beta/"


async def test_files_are_excluded(tmp_path):
    base = tree(tmp_path)
    assert await PathSuggester().get_suggestion(f"{base}/alf") is None


async def test_first_sorted_directory_wins(tmp_path):
    base = tree(tmp_path)
    assert await PathSuggester().get_suggestion(f"{base}/al") == f"{base}/alpha/"


async def test_no_match_and_missing_parent_give_nothing(tmp_path):
    base = tree(tmp_path)
    s = PathSuggester()
    assert await s.get_suggestion(f"{base}/zzz") is None
    assert await s.get_suggestion(f"{base}/nope/a") is None


async def test_trailing_slash_lists_children(tmp_path):
    base = tree(tmp_path)
    assert (
        await PathSuggester().get_suggestion(f"{base}/alpha/") == f"{base}/alpha/inner/"
    )


async def test_hidden_only_when_segment_starts_with_dot(tmp_path):
    base = tree(tmp_path)
    s = PathSuggester()
    assert await s.get_suggestion(f"{base}/") == f"{base}/alpha/"
    assert await s.get_suggestion(f"{base}/.") == f"{base}/.hidden/"


async def test_tilde_expands_but_keeps_typed_prefix(tmp_path, monkeypatch):
    base = tree(tmp_path)
    monkeypatch.setenv("HOME", str(base))
    assert await PathSuggester().get_suggestion("~/be") == "~/beta/"


async def test_relative_to_cwd(tmp_path, monkeypatch):
    tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert await PathSuggester().get_suggestion("be") == "beta/"


async def test_unreadable_directory_gives_nothing(tmp_path, monkeypatch):
    base = tree(tmp_path)

    def boom(self):
        raise PermissionError

    monkeypatch.setattr("pathlib.Path.iterdir", boom)
    assert await PathSuggester().get_suggestion(f"{base}/a") is None


async def test_listing_is_capped(tmp_path, monkeypatch):
    base = tree(tmp_path)
    monkeypatch.setattr("hunches.screens.paths.MAX_ENTRIES", 2)
    # only the first 2 entries in directory order are looked at; "beta" is beyond the cap
    entries = [base / "alpha", base / "alps", base / "beta"]
    monkeypatch.setattr("pathlib.Path.iterdir", lambda self: iter(entries))
    assert await PathSuggester().get_suggestion(f"{base}/be") is None


class InputApp(App):
    def __init__(self, value=""):
        super().__init__()
        self.value = value

    def compose(self):
        yield PathInput(self.value, id="path")
        yield Input(id="other")


async def test_tab_accepts_suggestion_else_moves_focus(tmp_path):
    base = tree(tmp_path)
    app = InputApp(f"{base}/be")
    async with app.run_test() as pilot:
        box = app.query_one("#path", PathInput)
        await pilot.pause()
        await pilot.press("tab")
        assert box.value == f"{base}/beta/"
        assert app.focused is box
        await pilot.pause()  # suggestion for the new value: beta has no children
        await pilot.press("tab")
        assert app.focused is app.query_one("#other")


class PickerApp(App):
    result = "unset"

    def __init__(self, start):
        super().__init__()
        self.start = start

    def on_mount(self):
        self.push_screen(PathPicker(self.start), self.got)

    def got(self, path):
        self.result = path


async def test_picker_select_returns_root_when_nothing_highlighted(tmp_path):
    base = tree(tmp_path)
    app = PickerApp(base / "beta")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.click("#select")
        await pilot.pause()
        assert app.result == base / "beta"


async def test_picker_up_rerooots_at_parent(tmp_path):
    base = tree(tmp_path)
    app = PickerApp(base / "beta")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.click("#up")
        await pilot.pause()
        await pilot.click("#select")
        await pilot.pause()
        assert app.result == base


async def test_picker_selects_highlighted_directory_not_files_or_hidden(tmp_path):
    base = tree(tmp_path)
    app = PickerApp(base)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        tree_widget = app.screen.query_one(DirTree)
        assert [str(n.label) for n in tree_widget.root.children] == [
            "alpha",
            "alps",
            "beta",
        ]
        tree_widget.focus()
        await pilot.press("down", "down")  # root -> alpha -> alps
        await pilot.click("#select")
        await pilot.pause()
        assert app.result == base / "alps"


async def test_picker_enter_expands_but_never_selects(tmp_path):
    base = tree(tmp_path)
    app = PickerApp(base)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen.query_one(DirTree).focus()
        await pilot.press("down", "enter")  # on alpha
        await pilot.pause()
        assert app.result == "unset"
        assert isinstance(app.screen, PathPicker)


async def test_picker_cancel_and_escape_return_none(tmp_path):
    base = tree(tmp_path)
    for how in ("click", "escape"):
        app = PickerApp(base)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            if how == "click":
                await pilot.click("#cancel")
            else:
                await pilot.press("escape")
            await pilot.pause()
            assert app.result is None


async def test_picker_enter_in_input_rerooots_and_ignores_non_directories(tmp_path):
    base = tree(tmp_path)
    app = PickerApp(base)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        box = app.screen.query_one("#root", PathInput)
        box.focus()
        box.value = str(base / "alpha")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.query_one(DirTree).path == base / "alpha"
        box.value = str(base / "alfile.txt")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.query_one(DirTree).path == base / "alpha"


class BrowseApp(App):
    def compose(self):
        yield PathInput("", id="path")
        yield Button(BROWSE_LABEL, id="browse")

    def on_button_pressed(self, event):
        if event.button.id == "browse":
            browse(self, self.query_one("#path", Input))


async def test_browse_writes_selection_back_and_cancel_keeps_value(tmp_path):
    base = tree(tmp_path)
    app = BrowseApp()
    async with app.run_test(size=(80, 24)) as pilot:
        box = app.query_one("#path", Input)
        box.value = str(base)
        await pilot.click("#browse")
        await pilot.pause()
        assert isinstance(app.screen, PathPicker)
        await pilot.click("#cancel")
        await pilot.pause()
        assert box.value == str(base)
        await pilot.click("#browse")
        await pilot.pause()
        app.screen.query_one(DirTree).focus()
        await pilot.press("down")  # alpha
        await pilot.click("#select")
        await pilot.pause()
        assert box.value == str(base / "alpha")
