from conftest import panel_title

from hunches import files
from hunches.app import HunchesApp
from hunches.theme import HUNCHES, OFF_TOPIC_COLOR, label_color


def test_label_color_follows_taxonomy_order_and_wraps():
    assert label_color(0, "a") == "#5CC8B4"
    assert label_color(1, "b") == "#E592B8"
    assert label_color(8, "i") == "#5CC8B4"  # 8 colours, then wraps
    assert label_color(0, "off_topic") == OFF_TOPIC_COLOR == "#6B7585"


async def test_app_uses_hunches_theme_and_stylesheet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir="c",
            embedding_model="m",
        )
    )
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.theme == HUNCHES.name == "hunches"
        assert app.current_theme.primary == "#6EA8FE"
        assert app.screen.styles.background.hex.upper() == "#0E1218"


def test_label_tag_markup():
    from hunches.theme import label_tag

    names = ["layoff_story", "hiring"]
    assert label_tag(names, "hiring") == "[#E592B8]■[/] hiring"
    assert label_tag(names, "off_topic") == "[#6B7585]■[/] [$text-muted]off_topic[/]"
    assert label_tag(names, "removed") == "[#6B7585]■[/] removed"  # not in the taxonomy
    assert (
        label_tag(names, "a[b]") == "[#6B7585]■[/] a\\[b]"
    )  # markup in names is escaped


def test_label_text_for_tables():
    from hunches.theme import label_text

    names = ["layoff_story", "hiring"]
    t = label_text(names, "hiring")
    assert t.plain == "■ hiring" and t.spans[0].style == "#E592B8"
    off = label_text(names, "off_topic")
    assert off.plain == "■ off_topic" and "#8C96A6" in str(off.spans[-1].style)
    assert label_text(names, "a[b]").plain == "■ a[b]"  # no markup parsing


async def test_panel_mounts_one_title_row_and_retitle_updates_it():
    from textual.app import App
    from textual.containers import Vertical
    from textual.widgets import Static

    from hunches.app import panel, retitle

    box = panel(Vertical(Static("body")), "t", "s")

    class Host(App):
        def compose(self):
            yield box

    async with Host().run_test() as pilot:
        await pilot.pause()
        assert len(box.query(".panel-title")) == 1
        assert box.query(".panel-title").first().region.height == 1
        assert panel_title(box) == ("t", "s")
        assert not box.border_title
        assert box.styles.border.top[0] in ("", "none")
        retitle(box, "t2")  # subtitle untouched
        assert panel_title(box) == ("t2", "s")
        retitle(box, subtitle="[b]x[/]")  # markup allowed
        assert panel_title(box) == ("t2", "[b]x[/]")
        retitle(box, subtitle="")
        assert panel_title(box) == ("t2", "")


def test_key_button_label_has_two_spaces_before_key():
    from hunches.app import key_button

    b = key_button("Approve seeds", "F2", id="go", variant="success")
    assert str(b.label) == "Approve seeds  F2"
    assert b.id == "go"


async def test_say_hides_empty_note():
    from textual.app import App
    from textual.widgets import Static

    from hunches.app import say

    note = Static("", id="note")

    class Host(App):
        def compose(self):
            yield note

    async with Host().run_test() as pilot:
        say(note, "careful")
        await pilot.pause()
        assert note.display is True and str(note.content) == "careful"
        say(note, "")
        await pilot.pause()
        assert note.display is False


def test_boost_is_the_solid_design_colour():
    from textual.app import App

    app = App()
    app.register_theme(HUNCHES)
    app.theme = "hunches"
    assert (
        app.get_css_variables()["boost"] == "#252E3E"
    )  # not Textual's 4% white overlay
