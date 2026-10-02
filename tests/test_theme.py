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
    files.write_config(files.Config(corpus_dir="c", embedding_model="m"))
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.theme == HUNCHES.name == "hunches"
        assert app.current_theme.primary == "#6EA8FE"
        assert app.screen.styles.background.hex.upper() == "#0E1218"
