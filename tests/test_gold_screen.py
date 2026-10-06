import json

import pytest
from conftest import panel_title
from textual.widgets import Button, DataTable, Static

from hunches import files
from hunches.app import HunchesApp
from hunches.screens.gold import GoldScreen, draw, milestone
from hunches.screens.progress import LabelBar

pytestmark = pytest.mark.usefixtures("system_ready")


def project(mode="single", n=60, gold=()):
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="test",
            corpus_dir="c",
            embedding_model="m",
        )
    )
    files.write_text("seeds.csv", "seed\nx\n")
    files.write_state(files.State(seeds_approved=True, taxonomy_approved=True))
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": str(i), "text": f"item {i}", "max_similarity": 0.7, "best_seed": "x"}
            for i in range(n)
        ],
    )
    files.write_taxonomy(
        files.Taxonomy(mode=mode, labels=[files.Label(name="a"), files.Label(name="b")])
    )
    files.write_text("prompt.md", "Classify.")
    files.write_gold(list(gold))


@pytest.fixture(autouse=True)
def cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def gold_screen(app) -> GoldScreen:
    assert isinstance(app.screen, GoldScreen)
    return app.screen


def counts(screen):
    table = screen.query_one("#counts", DataTable)
    return {str(k.value): str(table.get_row(k)[1]) for k in table.rows}


def test_draw_size_exclusion_and_reproducible():
    project(n=60)
    first = draw("dev", 50)
    assert len(first) == 50 and len({r.id for r in first}) == 50
    assert all(r.labels == [] and r.split == "dev" for r in first)
    assert len(files.read_gold()) == 50  # persisted immediately
    test = draw("test", 50)
    assert len(test) == 10  # only 10 candidates left
    assert not {r.id for r in first} & {r.id for r in test}
    # same project state, same draw
    files.write_gold([])
    assert [r.id for r in draw("dev", 50)] == [r.id for r in first]


async def test_single_mode_labels_persist():
    project("single")
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        assert isinstance(screen, GoldScreen)
        assert len(files.read_gold()) == 50
        await pilot.press("1")
        await pilot.pause()
        await pilot.press("0", "2")  # off_topic, then b
        await pilot.pause()
        gold = files.read_gold()
        assert [r.labels for r in gold[:3]] == [["a"], ["off_topic"], ["b"]]
        assert counts(screen)["a"] == "1" and counts(screen)["off_topic"] == "1"
        assert screen.index == 3
        assert files.first_incomplete_stage() == 4  # not complete until 50 labelled


async def test_multi_mode_toggle_and_invalid_refused():
    project("multi")
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        assert isinstance(screen, GoldScreen)
        await pilot.press("enter")  # nothing chosen
        await pilot.pause()
        assert files.read_gold()[0].labels == []
        assert "Not saved" in screen.note
        await pilot.press("1", "2", "0")  # off_topic clears a and b
        assert screen.pending == ["off_topic"]
        await pilot.press("1")  # a clears off_topic
        assert screen.pending == ["a"]
        await pilot.press("2", "1")  # add b, remove a
        assert screen.pending == ["b"]
        await pilot.press("1", "enter")
        await pilot.pause()
        assert files.read_gold()[0].labels == ["b", "a"]
        assert screen.index == 1


async def test_resume_skip_draw_more_and_finish():
    gold = [
        files.GoldRow(id=str(i), text=f"item {i}", labels=["a"], split="dev")
        for i in range(5)
    ] + [
        files.GoldRow(id=str(i), text=f"item {i}", labels=[], split="dev")
        for i in range(5, 50)
    ]
    project("single", n=100, gold=gold)
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        assert isinstance(screen, GoldScreen)
        assert screen.index == 5 and len(screen.rows) == 50  # resumed, same items
        await pilot.press("right")
        assert screen.index == 6 and files.read_gold()[5].labels == []
        await pilot.press("f2")  # unlabelled items remain: nothing happens
        await pilot.pause()
        assert screen.is_current and screen.note == ""
        await pilot.press("d")
        assert len(screen.rows) == 60 and len(files.read_gold()) == 60
        await pilot.press("left" * 1)
        for row in screen.rows:
            row.labels = ["b"]
        files.write_gold(screen.all)
        assert files.first_incomplete_stage() == 5
        await pilot.press("f2")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert app.stage == 5


def test_gold_file_is_jsonl():
    project()
    draw("dev", 2)
    lines = (files.root() / "gold.jsonl").read_text().splitlines()
    assert json.loads(lines[0])["labels"] == []


def text(screen, id_):
    return str(screen.query_one(id_, Static).render())


def squashed(screen, id_):
    return " ".join(text(screen, id_).split())


async def test_redesigned_layout_80x24_single():
    project("single")
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        assert isinstance(screen, GoldScreen)
        assert "dev set" in text(screen, "#p-split")
        item = screen.query_one("#item")
        first = screen.rows[0]
        assert panel_title(item)[0] == f"item {first.id}"
        assert "item" in text(screen, "#text")
        labels = screen.query_one("#labels-panel")
        assert panel_title(labels)[0] == "labels · single"
        assert panel_title(labels)[1] == "press a key to label"
        counts_panel = screen.query_one("#counts-panel")
        assert panel_title(counts_panel)[0] == "counts"
        assert panel_title(counts_panel)[1] == "0 of 50"
        assert counts_panel.outer_size.width <= 30
        rows = text(screen, "#labels").splitlines()
        assert [r.replace("▌", "").split()[0] for r in rows] == ["1", "2", "0"]
        assert all("○" in r for r in rows)
        for widget in screen.query("#item, #labels-panel, #counts-panel"):
            assert widget.region.bottom <= 23


async def test_label_rows_marks_and_counts_subtitle():
    project("single")
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        assert isinstance(screen, GoldScreen)
        await pilot.press("1")
        await pilot.pause()
        await pilot.press("left")
        rows = text(screen, "#labels").splitlines()
        assert "●" in rows[0] and "○" in rows[1]  # the saved label is filled
        assert panel_title(screen.query_one("#counts-panel"))[1] == "1 of 50"
        assert "1 / 50" == screen.query_one("#bar", LabelBar).label


async def test_multi_mode_uses_square_marks_and_hint():
    project("multi")
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        assert panel_title(screen.query_one("#labels-panel"))[0] == "labels · multi"
        assert (
            panel_title(screen.query_one("#labels-panel"))[1]
            == "keys toggle, enter confirms"
        )
        await pilot.press("2")
        rows = text(screen, "#labels").splitlines()
        assert "□" in rows[0] and "■" in rows[1] and "□" in rows[2]


async def test_not_ready_notice():
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="test",
            corpus_dir="c",
            embedding_model="m",
        )
    )
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(4)
        await pilot.pause()
        notice = app.screen.query_one("#not-ready")
        assert str(notice.render()) == "Finish stage 3 (taxonomy and prompt) first."
        assert notice.has_class("not-ready")


# ---- 003/09 ----


def test_milestone_arithmetic_total_50():
    # 25 % of 50 is 12.5, so ceil gives 13; 75 % is 37.5, so 38
    assert milestone(0, 50) == ("a quarter of the way", 13, None)
    assert milestone(12, 50) == ("a quarter of the way", 1, None)
    assert milestone(13, 50) == ("halfway", 12, "A quarter of the way there.")
    assert milestone(25, 50) == ("three quarters", 13, "Halfway there.")
    assert milestone(38, 50) == ("done", 12, "Three quarters of the way there.")
    assert milestone(49, 50) == ("done", 1, None)
    assert milestone(50, 50) == ("done", 0, "All labelled. Press F2 to finish.")


def test_milestone_arithmetic_total_56_after_a_draw():
    # 14, 28, 42, 56
    assert milestone(13, 56) == ("a quarter of the way", 1, None)
    assert milestone(14, 56) == ("halfway", 14, "A quarter of the way there.")
    assert milestone(28, 56) == ("three quarters", 14, "Halfway there.")
    assert milestone(42, 56) == ("done", 14, "Three quarters of the way there.")


def labelled(n_done, n_total=50, split="dev", start=0):
    return [
        files.GoldRow(
            id=str(start + i),
            text=f"item {start + i}",
            labels=["a"] if i < n_done else [],
            split=split,
        )
        for i in range(n_total)
    ]


async def test_progress_block_values():
    project("single", n=100, gold=labelled(17))
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        assert text(screen, "#p-split") == "dev set"
        assert text(screen, "#p-item") == "item 18"
        assert text(screen, "#p-left") == "33 to go"
        bar = screen.query_one("#bar", LabelBar)
        assert (bar.total, bar.value, bar.label) == (50, 17, "17 / 50")
        assert text(screen, "#p-next") == "Next milestone: halfway · 8 more"
        assert text(screen, "#p-pct") == "34%"


async def test_milestone_message_is_one_time():
    project("single", n=100, gold=labelled(24))
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        await pilot.press("1")  # 25 of 50 labelled
        await pilot.pause()
        assert text(screen, "#p-next") == "Halfway there. 25 to go."
        await pilot.press("1")  # 26
        await pilot.pause()
        assert text(screen, "#p-next") == "Next milestone: three quarters · 12 more"


async def test_complete_state_and_finish_button():
    project("single", n=100, gold=labelled(49))
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        finish = screen.query_one("#finish", Button)
        assert finish.disabled
        assert str(finish.label) == "Finish dev set  F2"
        assert str(screen.query_one("#more", Button).label) == "Draw 10 more  d"
        assert screen.check_action("finish", ()) is None  # dimmed, not hidden
        await pilot.press("1")
        await pilot.pause()
        assert text(screen, "#p-left") == "Complete"
        assert text(screen, "#p-next") == "All labelled. Press F2 to finish."
        assert not finish.disabled
        assert screen.check_action("finish", ()) is True
        await pilot.click("#finish")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert app.stage == 5


async def test_finish_does_nothing_while_unlabelled():
    project("single", n=100, gold=labelled(10))
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        screen.action_finish()
        await pilot.pause()
        assert app.screen is screen and screen.note == ""
        await pilot.press("d")  # the draw button works at any time
        assert len(screen.rows) == 60


async def test_labelling_never_calls_a_model(monkeypatch):
    import pydantic_ai

    import hunches.classifier
    from hunches.screens import gold

    def boom(*a, **k):
        raise AssertionError("labelling called the classifier")

    monkeypatch.setattr(hunches.classifier, "classify", boom)
    monkeypatch.setattr(pydantic_ai.Agent, "run", boom)
    project("single")
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        await pilot.press("1", "2")
        await pilot.pause()
        assert [r.labels for r in files.read_gold()[:2]] == [["a"], ["b"]]
        assert not hasattr(screen, "predictions") and not hasattr(screen, "predict")
        assert not screen.query("#prediction")
        assert not hasattr(gold, "classify")


async def test_pool_short_dev_blocks_labelling():
    project("single", n=38)
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        assert isinstance(screen, GoldScreen)
        assert (
            text(screen, "#short-banner")
            == "Only 38 candidates were found; the dev set needs 50."
        )
        assert (
            text(screen, "#short-title")
            == "Your corpus may be too small for this analysis"
        )
        numbers = squashed(screen, "#short-numbers")
        assert (
            numbers == "candidates found 38 left to draw 38 needed for the dev set 50"
        )
        assert not screen.query_one("#main").display
        await pilot.press("1", "d", "enter")
        await pilot.pause()
        assert all(r.labels == [] for r in files.read_gold())
        assert len(files.read_gold()) == 38
        assert screen.check_action("draw_more", ()) is False
        await pilot.click("#add-seeds")
        await pilot.pause()
        assert app.stage == 1


async def test_pool_short_test_split_wording_and_numbers():
    dev = labelled(50)
    project("single", n=74, gold=dev)
    state = files.read_state()
    state.dev_done = True
    files.write_state(state)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        assert isinstance(screen, GoldScreen) and screen.split == "test"
        assert (
            text(screen, "#short-banner")
            == "Only 24 unlabelled candidates are left for the test set; it needs 50."
        )
        assert squashed(screen, "#short-numbers") == (
            "candidates found 74 already in the dev set 50 "
            "left to draw 24 needed for the test set 50"
        )
        assert str(screen.query_one("#settings", Button).label) == (
            "Project settings  F3"
        )
        await pilot.click("#settings")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "ProjectSettingsScreen"


async def test_exhausted_banner_then_cleared_on_label():
    project("single", n=56, gold=labelled(10))
    app = HunchesApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = gold_screen(app)
        assert not screen.query_one("#exhausted").display
        await pilot.press("d")  # only 6 candidates remain
        await pilot.pause()
        assert len(screen.rows) == 56
        banner = screen.query_one("#exhausted")
        assert banner.display
        assert text(screen, "#exhausted") == (
            "No more candidates to draw: only 6 were left, so the set has 56 items. "
            "If you need more, your corpus may be too small for this analysis."
        )
        assert screen.query_one("#main").display  # not blocking
        await pilot.press("1")
        await pilot.pause()
        assert not screen.query_one("#exhausted").display
