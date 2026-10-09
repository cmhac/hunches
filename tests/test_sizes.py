"""Every screen and modal mounts at 80x24, 100x30 and 120x36 without error, with the rail only from
100 columns and no widget clipped by its screen (scroll areas excepted)."""

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.scroll_view import ScrollView
from textual.widgets import DataTable

from hunches import classifier, files, history, metrics, system
from hunches.app import ConfirmScreen, HunchesApp, StatusHeader
from hunches.screens.history import HistoryScreen, NeedsVersionScreen
from hunches.screens.model_picker import ModelPicker
from hunches.screens.new_project import NewProjectScreen
from hunches.screens.paths import PathPicker
from hunches.screens.project_settings import ProjectSettingsScreen
from hunches.screens.projects import ProjectsScreen, RemoveModal
from hunches.screens.redo_plan import RedoPlanScreen
from hunches.screens.system import RecommendationModal, SystemSettingsScreen
from hunches.screens.taxonomy import VersionsScreen
from hunches.screens.tune import PromptEditScreen, ProposalScreen

pytestmark = pytest.mark.usefixtures("stub_taxonomy_assistant")

SIZES = [(80, 24), (100, 30), (120, 36)]
PROMPT = "Label the item."
STAGE_NAMES = [
    "brief",
    "search",
    "taxonomy",
    "gold-dev",
    "tune",
    "gold-test",
    "threshold",
    "full-run",
    "browse",
]
LONG = "A fairly long question that wraps over several lines in the narrow modal. " * 3


def classify(messages, info: AgentInfo):
    return ModelResponse(
        parts=[
            ToolCallPart(info.output_tools[0].name, {"reasoning": "r", "labels": ["a"]})
        ]
    )


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    """A finished project (every stage ready) with one archived taxonomy version."""
    monkeypatch.chdir(tmp_path)
    system.write_system(
        system.System(
            provider="anthropic",
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            recommendation_seen=system.RECOMMENDED_REVISION,
        )
    )
    (tmp_path / "c").mkdir()
    for name in ("vectors.npy", "items.jsonl", "meta.json"):
        (tmp_path / "c" / name).write_text(
            "x"
        )  # healthy as far as project_status looks
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir="c",
            embedding_model="m",
        )
    )
    files.write_text("brief.md", "Find even items\n")
    files.write_text("seeds.csv", "seed\nalpha\nbeta\n")
    files.write_state(
        files.State(
            seeds_approved=True,
            taxonomy_approved=True,
            dev_done=True,
            test_done=True,
            threshold_chosen=True,
        )
    )
    files.write_taxonomy(
        files.Taxonomy(
            mode="single",
            labels=[files.Label(name="a", description="even"), files.Label(name="b")],
        )
    )
    files.write_text("prompt.md", PROMPT)
    files.write_text("threshold.json", json.dumps({"threshold": 0.65}))
    model = "anthropic:claude-haiku-4-5"
    gold = [{"a"}, {"off_topic"}, {"a"}, {"off_topic"}]
    guess = [{"a"}, {"a"}, {"off_topic"}, {"off_topic"}]
    m = metrics.compute_metrics(gold, guess, ["a", "b", "off_topic"])
    files.write_text(
        "test_result.json",
        json.dumps(
            {
                "prompt_hash": hashlib.sha256(
                    json.dumps([PROMPT, model]).encode()
                ).hexdigest(),
                "timestamp": "2026-10-06T12:00:00+00:00",
                "metrics": dataclasses.asdict(m),
                "disagreements": [
                    {
                        "text": "item " + "long text " * 20,
                        "gold": sorted(gold[i]),
                        "predicted": sorted(guess[i]),
                        "reasoning": "because " * 30,
                    }
                    for i in m.disagreements
                ],
            }
        ),
    )
    files.write_jsonl(
        "candidates.jsonl",
        [
            {
                "id": f"i{i}",
                "text": f"item {i}",
                "max_similarity": 0.61 + (i % 20) / 100,
                "best_seed": "alpha",
            }
            for i in range(120)
        ],
    )
    files.write_gold(
        [
            files.GoldRow(
                id=f"i{i + (0 if s == 'dev' else 50)}",
                text=f"item {i + (0 if s == 'dev' else 50)}",
                labels=["a"] if i % 2 else ["off_topic"],
                split=s,
            )
            for s in ("dev", "test")
            for i in range(50)
        ]
    )
    files.archive_version("sweep")
    monkeypatch.setattr(
        classifier, "Agent", lambda model, **kw: Agent(FunctionModel(classify), **kw)
    )


MODALS = [
    "confirm",
    "recommendation",
    "remove",
    "model-picker",
    "embedding-picker",
    "path-picker",
    "versions",
    "proposal",
    "prompt-edit",
    "history",
    "needs-version-restore",
    "needs-version-new",
]


def modals():
    current = system.read_system()
    assert current
    labels = files.read_taxonomy()
    return {
        "confirm": lambda: ConfirmScreen(LONG),
        "recommendation": lambda: RecommendationModal(current),
        "remove": lambda: RemoveModal("a-project-name"),
        "model-picker": lambda: ModelPicker(),
        "embedding-picker": lambda: ModelPicker(embedding=True),
        "path-picker": lambda: PathPicker(Path.cwd()),
        "versions": lambda: VersionsScreen(),
        "proposal": lambda: ProposalScreen(PROMPT, PROMPT + "\nMore.\n" * 3),
        "prompt-edit": lambda: PromptEditScreen(PROMPT),
        "history": lambda: HistoryScreen(),
        "needs-version-restore": lambda: NeedsVersionScreen(
            history.NeedsVersion("restore", labels, 2), "restore"
        ),
        "needs-version-new": lambda: NeedsVersionScreen(
            history.NeedsVersion("new_version", labels, 2), "undo"
        ),
    }


def clipped(screen: Screen) -> list[str]:
    """Widgets that are shown but not fully inside the screen, outside scroll areas."""
    bad = []
    for widget in screen.query("*"):
        chain = [widget, *widget.ancestors][:-2]  # up to, not including, the screen
        if not all(w.display for w in chain):
            continue
        if any(isinstance(w, (ScrollableContainer, ScrollView)) for w in chain[1:]):
            continue
        region = widget.region
        if region.area and not screen.region.contains_region(region):
            bad.append(f"{widget!r} {region} outside {screen.region}")
    return bad


async def check(app, pilot, width):
    screen = app.screen
    problems = clipped(screen)
    assert not problems, "\n".join(problems)
    for header in screen.query(StatusHeader):
        assert header.has_class("-rail") == (width >= 100)
        assert app.rail == (width >= 100)


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("stage", range(1, 10), ids=STAGE_NAMES)
async def test_stage_screens(size, stage):
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.goto_stage(stage)
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await check(app, pilot, size[0])


SETTINGS = {
    "projects": ProjectsScreen,
    "system": SystemSettingsScreen,
    "new-project": NewProjectScreen,
    "project-settings": ProjectSettingsScreen,
}


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("name", SETTINGS)
async def test_settings_screens(size, name):
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await app.push_screen(SETTINGS[name]())
        await pilot.pause()
        await check(app, pilot, size[0])


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("name", MODALS)
async def test_modals(size, name):
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await app.push_screen(modals()[name]())
        await pilot.pause()
        await check(app, pilot, size[0])


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("variant", ["text", "filter-open"])
async def test_history_variants(size, variant):
    files.write_text("prompt.md", PROMPT + "\nMore.")  # an outside edit for the log
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await app.push_screen(HistoryScreen())
        await pilot.pause()
        if variant == "text":
            await pilot.press("v")
        else:
            app.screen.query_one("#file").focus()
            await pilot.press("enter")
        await pilot.pause()
        await check(app, pilot, size[0])


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("stage", range(1, 10), ids=STAGE_NAMES)
async def test_external_notice_on_every_stage_screen(size, stage):
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.goto_stage(stage)
        await pilot.pause()
        files.write_text("prompt.md", PROMPT + "\nEdited in an editor.")
        app.check_history()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert len(app.notices()) == 1
        await check(app, pilot, size[0])


def make_stale(incomplete: bool = False) -> None:
    """Stages 5-8 were approved or run under PROMPT, then prompt.md changed (and the new prompt was
    tested). With `incomplete`, a dev row is gone too: stage 4 is incomplete."""
    for flag, stage in (("dev_done", 5), ("test_done", 6), ("threshold_chosen", 7)):
        files.approve(flag, stage, "approved")
    model = "anthropic:claude-haiku-4-5"
    run = files.run_digest(PROMPT, files.read_taxonomy(), model)
    files.write_jsonl(
        "results.jsonl",
        [
            {**c, "labels": ["a"], "run": run}
            for c in files.read_jsonl("candidates.jsonl")
            if c["max_similarity"] >= 0.65
        ],
    )
    history.save("prompt", PROMPT + "\nChanged.", "user", "Prompt: edited by the user")
    result = json.loads(files.read_text("test_result.json") or "")
    result.pop("prompt_hash")
    result["inputs"] = files.current_inputs("test_done")
    files.write_text("test_result.json", json.dumps(result))
    if incomplete:
        files.write_gold([r for r in files.read_gold() if r.id != "i0"])


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("variant", ["plan", "incomplete", "progress", "done"])
async def test_redo_plan_modal(size, variant):
    if variant != "done":
        make_stale(incomplete=variant == "incomplete")
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await app.push_screen(RedoPlanScreen([5] if variant == "progress" else []))
        await pilot.pause()
        await pilot.pause()
        await check(app, pilot, size[0])
        rows = app.screen.query_one("#plan", DataTable).row_count
        assert rows == {"plan": 5, "incomplete": 6, "progress": 5, "done": 0}[variant]


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("stage", range(1, 10), ids=STAGE_NAMES)
async def test_stage_screens_with_stale_and_incomplete_marks(size, stage):
    make_stale(incomplete=True)
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await (
            app.workers.wait_for_complete()
        )  # the app opens on Tuning, which runs the dev set
        app.goto_stage(stage)
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await check(app, pilot, size[0])
        marks = "\n".join(str(h.render()) for h in app.screen.query(StatusHeader))
        assert "↻" in marks and "◐" in marks


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("stage", range(5, 10), ids=STAGE_NAMES[4:])
async def test_stale_banners_are_shown_and_fit(size, stage):
    make_stale()
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await (
            app.workers.wait_for_complete()
        )  # the app opens on Tuning, which runs the dev set
        app.goto_stage(stage)
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await check(app, pilot, size[0])
        banners = [b for b in app.screen.query("StageBanner") if b.display]
        assert len(banners) == 1, stage


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
async def test_search_with_the_embedding_warning(size):
    files.write_text(
        "candidates.meta.json",
        json.dumps(
            {"seeds_digest": "x", "embedding_model": "an-older-embedding-model"}
        ),
    )
    app = HunchesApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.goto_stage(2)
        await pilot.pause()
        await check(app, pilot, size[0])
        assert app.screen.query_one("#embedding-warning").display
