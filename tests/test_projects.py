import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from textual.widgets import Button, DataTable, Input, Static

from hunches import files, system
from hunches.app import ConfirmScreen, HunchesApp, StatusHeader
from hunches.screens.paths import PathPicker
from hunches.screens.projects import ProjectsScreen, RemoveModal
from hunches.theme import HUNCHES


class Host(HunchesApp):
    """HunchesApp that starts on the Projects screen (the startup flow is task 09)."""

    def on_mount(self, event):  # ty: ignore[invalid-method-override]
        event.prevent_default()  # skip HunchesApp.on_mount
        self.register_theme(HUNCHES)
        self.theme = "hunches"
        self.push_screen(ProjectsScreen())


Host.CSS_PATH = str(Path(__file__).parent.parent / "src" / "hunches" / "hunches.tcss")


def register(*projects):
    """First project is the most recently opened. Writes system.json (HUNCHES_HOME is a tmp dir)."""
    now = datetime.now(UTC)
    system.write_system(
        system.System(
            provider="anthropic",
            assistant_model="a",
            classifier_model="c",
            projects=[
                system.Project(
                    path=str(p),
                    last_opened=(now - timedelta(days=i + 1)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                )
                for i, p in enumerate(projects)
            ],
        )
    )


def rows(table: DataTable) -> list[list[str]]:
    return [[str(c) for c in table.get_row_at(i)] for i in range(table.row_count)]


def make_project(base, name="proj", corpus=True, **config):
    """A project dir with .hunches/config.toml and (optionally) a complete local corpus."""
    project = base / name
    (project / ".hunches").mkdir(parents=True)
    cfg = {
        "corpus_dir": "corpus",
        "embedding_model": "m",
        "assistant_model": "test",
        "classifier_model": "test",
        **config,
    }
    lines = "\n".join(f'{k} = "{v}"' for k, v in cfg.items())
    (project / ".hunches" / "config.toml").write_text(lines + "\n")
    if corpus:
        (project / "corpus").mkdir()
        for f in ("vectors.npy", "items.jsonl", "meta.json"):
            (project / "corpus" / f).write_text("x")
    return project


def test_status_ok(tmp_path):
    project = make_project(tmp_path)
    assert system.project_status(project) == ("OK", "")


def test_status_missing_dir(tmp_path):
    assert system.project_status(tmp_path / "gone")[0] == "MISSING DIR"


def test_status_no_config_when_missing_or_invalid(tmp_path):
    (tmp_path / "bare").mkdir()
    assert system.project_status(tmp_path / "bare")[0] == "NO CONFIG"
    project = make_project(tmp_path, "bad")
    (project / ".hunches" / "config.toml").write_text("backend = [broken")
    assert system.project_status(project)[0] == "NO CONFIG"


def test_status_missing_corpus_names_the_files(tmp_path):
    project = make_project(tmp_path)
    (project / "corpus" / "vectors.npy").unlink()
    (project / "corpus" / "meta.json").unlink()
    status, detail = system.project_status(project)
    assert status == "MISSING CORPUS"
    assert "vectors.npy" in detail and "meta.json" in detail
    assert "items.jsonl" not in detail


def test_status_s3_is_ok_but_not_checked(tmp_path):
    project = make_project(
        tmp_path, corpus=False, backend="s3", s3_bucket="b", s3_index="i"
    )
    assert system.project_status(project) == ("OK (s3 not checked)", "")


async def test_lists_projects_most_recent_first_with_status_and_banner(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    ok = make_project(tmp_path, "ok")
    nocorpus = make_project(tmp_path, "nocorpus", corpus=False)
    register(ok, tmp_path / "gone", nocorpus)
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one(DataTable)
        got = rows(table)
        assert [r[0] for r in got] == ["ok", "gone", "nocorpus"]
        assert [r[1] for r in got] == ["local", "?", "local"]
        assert [r[3] for r in got] == ["OK", "MISSING DIR", "MISSING CORPUS"]
        banner = app.screen.query_one("#banner", Static)
        assert "2 projects need attention" in str(banner.render())


async def test_empty_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    register()
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        empty = app.screen.query_one("#empty", Static)
        assert "No projects yet. Press n to create one." in str(empty.render())
        assert not app.screen.query_one("#banner").display


def at_stage_2(project):
    (project / ".hunches" / "seeds.csv").write_text("seed\nfoo\n")
    (project / ".hunches" / "state.json").write_text('{"seeds_approved": true}')
    return project


async def test_open_project_changes_cwd_and_shows_first_incomplete_stage(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    first = make_project(tmp_path, "first")
    second = at_stage_2(make_project(tmp_path, "second"))
    register(first, second)
    before = system.projects_by_recent()[1].last_opened
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.open_project(second)
        await pilot.pause()
        assert Path.cwd() == second.resolve()
        assert app.stage == 2
        assert not isinstance(app.screen, ProjectsScreen)
        assert len(app.screen_stack) == 2  # default screen + the stage
        # `first` was most recent and `second` is now: the order flipped
        assert system.projects_by_recent()[0].path == str(second.resolve())
        assert system.projects_by_recent()[0].last_opened >= before


async def test_open_unhealthy_project_shows_an_error_and_stays(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    register(tmp_path / "gone")
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        shown = []
        monkeypatch.setattr(app, "notify", lambda msg, **kw: shown.append((msg, kw)))
        app.open_project(tmp_path / "gone")
        await pilot.pause()
        assert Path.cwd() == tmp_path
        assert isinstance(app.screen, ProjectsScreen)
        assert "MISSING DIR" in shown[0][0] and shown[0][1]["severity"] == "error"


async def test_open_with_running_worker_asks_first(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = make_project(tmp_path, "target")
    register(target)
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        worker = app.run_worker(asyncio.sleep(60))
        app.open_project(target)
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        assert Path.cwd() == tmp_path and worker.is_running
        await pilot.click("#no")  # declining changes nothing
        await pilot.pause()
        assert Path.cwd() == tmp_path and worker.is_running
        app.open_project(target)
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert Path.cwd() == target.resolve() and worker.is_cancelled
        assert app.stage == 1


async def test_enter_opens_the_highlighted_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = at_stage_2(make_project(tmp_path, "target"))
    register(target)
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert Path.cwd() == target.resolve() and app.stage == 2


async def test_r_recomputes_statuses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    register(tmp_path / "later")
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one(DataTable)
        assert rows(table)[0][3] == "MISSING DIR"
        make_project(tmp_path, "later")
        await pilot.press("r")
        await pilot.pause()
        assert rows(table)[0][3] == "OK"
        assert not app.screen.query_one("#banner").display


async def test_remove_only_edits_the_registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project = make_project(tmp_path, "victim")
    keep = make_project(tmp_path, "keep")
    register(project, keep)
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert isinstance(app.screen, RemoveModal)
        assert (
            app.focused is not None and app.focused.id == "remove"
        )  # the safe action has focus
        await pilot.click("#remove")
        await pilot.pause()
        assert [r[0] for r in rows(app.screen.query_one(DataTable))] == ["keep"]
    assert [p.path for p in system.projects_by_recent()] == [str(keep)]
    assert (project / ".hunches" / "config.toml").exists()
    assert (project / "corpus" / "vectors.npy").exists()


async def test_delete_removes_only_dot_hunches_after_typing_the_name(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)  # a different dir: the victim is not the open project
    victim = make_project(tmp_path, "victim")
    (victim / "notes.txt").write_text("mine")
    (victim / ".hunches" / "cache").mkdir()
    (victim / ".hunches" / "cache" / "k.json").write_text("{}")
    neighbour = make_project(tmp_path, "neighbour")
    register(victim, neighbour)
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        delete = app.screen.query_one("#delete", Button)
        assert delete.disabled
        box = app.screen.query_one("#confirm", Input)
        box.value = "victi"
        await pilot.pause()
        assert delete.disabled
        box.value = "victim"
        await pilot.pause()
        assert not delete.disabled
        delete.press()
        await pilot.pause()
    assert not (victim / ".hunches").exists()
    assert (victim / "corpus" / "vectors.npy").exists()
    assert (victim / "notes.txt").read_text() == "mine"
    assert (neighbour / ".hunches" / "config.toml").exists()
    assert (neighbour / "corpus" / "items.jsonl").exists()


async def test_delete_refused_for_current_project_with_running_worker(
    tmp_path, monkeypatch
):
    victim = make_project(tmp_path, "victim")
    monkeypatch.chdir(victim)
    register(victim)
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        shown = []
        monkeypatch.setattr(app, "notify", lambda msg, **kw: shown.append(msg))
        app.run_worker(asyncio.sleep(60))
        await pilot.press("x")
        await pilot.pause()
        app.screen.query_one("#confirm", Input).value = "victim"
        await pilot.pause()
        app.screen.query_one("#delete", Button).press()
        await pilot.pause()
    assert (victim / ".hunches" / "config.toml").exists()
    assert "run is in progress" in shown[0]


def test_delete_project_files_never_follows_a_symlinked_dot_hunches(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "precious").write_text("x")
    project = tmp_path / "p"
    project.mkdir()
    (project / ".hunches").symlink_to(elsewhere)
    with pytest.raises(ValueError):
        system.delete_project_files(project)
    assert (elsewhere / "precious").exists()


async def test_locate_missing_dir_replaces_the_registry_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    moved = make_project(tmp_path, "moved")
    register(tmp_path / "old-place")
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, PathPicker)
        app.screen.dismiss(moved)
        await pilot.pause()
        assert rows(app.screen.query_one(DataTable))[0][3] == "OK"
    assert [p.path for p in system.projects_by_recent()] == [str(moved)]


async def test_locate_missing_corpus_updates_the_projects_corpus_dir(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    project = make_project(tmp_path, "p", corpus=False)
    moved = tmp_path / "moved-corpus"
    moved.mkdir()
    for f in ("vectors.npy", "items.jsonl", "meta.json"):
        (moved / f).write_text("x")
    register(project)
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert rows(app.screen.query_one(DataTable))[0][3] == "MISSING CORPUS"
        await pilot.press("l")
        await pilot.pause()
        app.screen.dismiss(moved)
        await pilot.pause()
        assert rows(app.screen.query_one(DataTable))[0][3] == "OK"
    assert files.read_config(project).corpus_dir == str(moved)
    assert Path.cwd() == tmp_path  # editing another project's config never chdirs
    assert [p.path for p in system.projects_by_recent()] == [str(project)]


async def test_header_names_the_screen_and_modal_fits_80x24(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    register(make_project(tmp_path, "p"))
    app = Host()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert "Projects" in str(app.screen.query_one(StatusHeader).render())
        await pilot.press("x")
        await pilot.pause()
        modal = app.screen.query_one("RemoveModal > Vertical")
        assert modal.region.bottom <= 24
        assert app.screen.query_one("#delete").region.bottom <= 24


async def test_esc_returns_to_the_open_project_only(tmp_path, monkeypatch):
    project = at_stage_2(make_project(tmp_path, "p"))
    monkeypatch.chdir(tmp_path)
    register(project)
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")  # no project open: stays
        await pilot.pause()
        assert isinstance(app.screen, ProjectsScreen)
        app.open_project(project)
        await pilot.pause()
        app.push_screen(ProjectsScreen())
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ProjectsScreen) and app.stage == 2


async def test_footer_has_no_stage_keys_without_a_project(tmp_path):
    register()
    app = Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        keys = {k: b.binding.description for k, b in app.screen.active_bindings.items()}
        assert keys["n"] == "New" and "p" not in keys
