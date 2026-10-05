from textual.app import App

from hunches.screens.progress import LabelBar


def test_fill_cells_are_hand_computed():
    # width 20, 5 of 20 -> 5 cells; complete -> all 20
    assert LabelBar(20, 5, "x").fill_cells(20) == 5
    assert LabelBar(12, 4, "x").fill_cells(30) == 10
    assert LabelBar(10, 10, "x").fill_cells(20) == 20
    assert LabelBar(0, 0, "x").fill_cells(20) == 0  # no total: empty, no ZeroDivision


async def test_label_bar_renders_label_text_in_one_row():
    bar = LabelBar(50, 17, "17 / 50")

    class Host(App):
        def compose(self):
            yield bar

    async with Host().run_test(size=(40, 5)) as pilot:
        await pilot.pause()
        assert bar.region.height == 1
        assert "17 / 50" in bar.render().plain  # type: ignore[union-attr]
        bar.update_bar(50, 50, "50 / 50")
        await pilot.pause()
        assert "50 / 50" in bar.render().plain  # type: ignore[union-attr]
        assert bar.has_class("-complete")
