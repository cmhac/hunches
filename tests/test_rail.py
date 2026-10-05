from pydantic_ai.usage import RunUsage
from test_app import make_project
from textual.widgets import Footer
from textual.widgets._footer import FooterKey

from hunches import cost
from hunches.app import HunchesApp, StatusHeader
from hunches.screens.project_settings import ProjectSettingsScreen
from hunches.screens.projects import ProjectsScreen
from hunches.screens.system import SystemSettingsScreen

RAIL_KEYS = {"q", "n", "p", "f3", "f4", "f5"}


def footer_keys(app) -> set[str]:
    return {k.key for k in app.screen.query(Footer).first().query(FooterKey)}


def rail_text(app) -> list[str]:
    return str(app.screen.query_one(StatusHeader).render()).split("\n")


async def test_rail_at_100_columns_and_one_row_header_below(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        header = app.screen.query_one(StatusHeader)
        assert header.has_class("-rail") and app.rail
        assert header.region.width == 26 and header.region.height == 30
        assert header.region.x == 0
        await pilot.resize_terminal(99, 30)
        await pilot.pause()
        assert not header.has_class("-rail") and not app.rail
        assert header.region.height == 1 and header.region.width == 99


async def test_footer_drops_rail_keys_only_in_rail_mode(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        keys = footer_keys(app)
        assert not keys & RAIL_KEYS and "f2" in keys
        await pilot.resize_terminal(99, 30)
        await pilot.pause()
        assert RAIL_KEYS <= footer_keys(app)
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert not footer_keys(app) & RAIL_KEYS


async def test_footer_sits_under_the_content_column_in_rail_mode(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        footer = app.screen.query_one(Footer)
        assert footer.region.x == 26 and footer.region.width == 74
        assert footer.region.bottom == 30
        await pilot.resize_terminal(120, 36)
        await pilot.pause()
        assert footer.region.x == 26 and footer.region.width == 94
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert footer.region.x == 0 and footer.region.width == 80


async def test_rail_keys_still_work_at_both_widths(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    for size in ((100, 30), (99, 30)):
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.stage == 1
            await pilot.press("n")
            await pilot.pause()
            assert app.stage == 2
            await pilot.press("p")
            await pilot.pause()
            assert app.stage == 1
            await pilot.press("f3")
            await pilot.pause()
            assert isinstance(app.screen, ProjectSettingsScreen)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("f4")
            await pilot.pause()
            assert isinstance(app.screen, ProjectsScreen)
            await pilot.press("f5")
            await pilot.pause()
            assert isinstance(app.screen, SystemSettingsScreen)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert app.stage == 1 and not isinstance(app.screen, ProjectsScreen)
            await pilot.press("q")
            await pilot.pause()
        assert app.return_code == 0
        app = HunchesApp()


async def test_rail_content_marks_stages_and_shows_cost(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch, stage_done=3)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.goto_stage(4)
        await pilot.pause()
        cost.record("m", RunUsage(input_tokens=1, output_tokens=1), 0.3127)
        await pilot.pause(0.6)
        lines = rail_text(app)
        assert all(len(line) <= 26 for line in lines)
        assert len(lines) <= 30
        text = "\n".join(lines)
        assert text.count("✓") == 3
        assert text.count("●") == 1
        assert (
            next(ln for ln in lines if "●" in ln).split("●")[1].strip()
            == "Gold dev set"
        )
        assert (
            text.count("·") == 5 + 1
        )  # five upcoming stages, one in "n/p stage · q quit"
        assert "$0.3127" in text and "cost ?" not in text
        assert lines[0].strip() == "hunches"
        name = tmp_path.name
        assert lines[1].strip() == (name if len(name) <= 23 else name[:22] + "…")
        for label, key in (
            ("Projects", "F4"),
            ("Project settings", "F3"),
            ("System settings", "F5"),
        ):
            assert any(label in ln and ln.rstrip().endswith(key) for ln in lines)
        assert "n/p stage · q quit" in text


async def test_rail_current_app_screen_is_marked(tmp_path, monkeypatch):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("f4")
        await pilot.pause()
        lines = rail_text(app)
        assert (
            next(ln for ln in lines if "▸" in ln).split("▸")[1].split("F4")[0].strip()
            == "Projects"
        )
        assert not any(
            "●" in ln for ln in lines
        )  # no stage is current under an overlay


async def test_rail_unknown_price_shows_badge_and_model_never_zero(
    tmp_path, monkeypatch
):
    make_project(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        cost.record("mystery", RunUsage(input_tokens=1, output_tokens=1), None)
        await pilot.pause(0.6)
        text = "\n".join(rail_text(app))
        assert "cost ?" in text and "mystery" in text
        assert "$" not in text
        assert app.screen.query_one(StatusHeader).has_class("-cost-unknown")
