"""Spec 004 task 09: stale and incomplete markers, banners, the Redo plan, the embedding-model
warning and Tuning's `r`. Expected values are written by hand; nothing here calls a real model."""

import asyncio
import json

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from test_redo_plan import SINGLE, complete_project
from textual.widgets import Button, Footer
from textual.widgets._footer import FooterKey

from hunches import classifier, files, history
from hunches.app import HunchesApp, StatusHeader

pytestmark = pytest.mark.usefixtures("system_ready", "stub_taxonomy_assistant")

CALLS: list[str] = []  # the item text of every classifier call a test makes


def classify(messages, info: AgentInfo):
    CALLS.append(messages[-1].parts[-1].content)
    out = {"reasoning": "r", "labels": ["a"]}
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    """Every stage done and approved under prompt "p"; 3 gold rows per split, 4 candidates."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(files, "SAMPLE_SIZE", 3)
    CALLS.clear()
    monkeypatch.setattr(
        classifier, "Agent", lambda model, **kw: Agent(FunctionModel(classify), **kw)
    )
    complete_project()
    run = files.run_digest("p", SINGLE, "m1")  # Browse needs max_similarity in the rows
    files.write_jsonl(
        "results.jsonl",
        [
            {"id": i, "text": "t", "labels": ["a"], "max_similarity": sim, "run": run}
            for i, sim in (("c1", 0.9), ("c2", 0.7))
        ],
    )
    from hunches import candidates

    bands = [
        [] for _ in candidates.BANDS
    ]  # the threshold screen indexes the sample by band
    bands[0] = ["c3", "c4"]
    sample = json.loads(files.read_text("threshold_sample.json") or "")
    files.write_text("threshold_sample.json", json.dumps({**sample, "ids": bands}))
    write_test_result()  # with the metrics and timestamp the test screen shows
    config = files.read_config()
    files.write_config(
        config.model_copy(
            update={"corpus_dir": "c", "assistant_model": "anthropic:claude-sonnet-5-5"}
        )
    )


def edit_prompt(text="p2") -> None:
    history.save("prompt", text, "user", "Prompt: edited by the user")


def footer_keys(app) -> set[str]:
    return {k.key for k in app.screen.query(Footer).first().query(FooterKey)}


def rail_lines(app) -> list[str]:
    return str(app.screen.query_one(StatusHeader).render()).split("\n")


def header_text(app) -> str:
    return str(app.screen.query_one(StatusHeader).render())


# ---- rail glyphs, legend, tooltip, Redo plan row ------------------------------------------


async def test_rail_marks_stale_stages_and_names_only_the_kinds_present():
    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        lines = rail_lines(app)
        assert app.stage == 5  # resumes at the first stage that is not current
        for name in ("Tuning loop", "Gold test set", "Threshold", "Full run"):
            assert "↻" in next(ln for ln in lines if name in ln)
        for name in (
            "Brief and seeds",
            "Search",
            "Taxonomy and prompt",
            "Gold dev",
            "Browse",
        ):
            assert not {"↻", "◐"} & set(next(ln for ln in lines if name in ln))
        assert any("↻ stale" in ln for ln in lines)
        assert not any("◐" in ln for ln in lines)
        assert all(len(ln) <= 26 for ln in lines) and len(lines) <= 30


async def test_rail_marks_incomplete_stages_and_the_legend_names_both_kinds():
    rows = [r for r in files.read_gold() if not (r.split == "dev" and r.id == "d0")]
    files.write_gold(rows)  # 2 of 3 dev rows: stage 4 incomplete, stage 5 stale
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        lines = rail_lines(app)
        assert "◐" in next(ln for ln in lines if "Gold dev set" in ln)
        assert "↻" in next(ln for ln in lines if "Tuning loop" in ln)
        assert any("↻ stale" in ln and "◐ incomplete" in ln for ln in lines)


async def test_rail_without_anything_to_redo_has_no_marks_legend_or_redo_row():
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        text = "\n".join(rail_lines(app))
        assert "↻" not in text and "◐" not in text and "Redo plan" not in text


async def test_rail_has_a_redo_plan_row_with_f9_only_when_something_is_marked():
    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        row = next(ln for ln in rail_lines(app) if "Redo plan" in ln)
        assert "↻" in row and row.rstrip().endswith("F9")


async def test_rail_tooltip_lists_each_marked_stage_with_its_reason():
    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        tip = str(app.screen.query_one(StatusHeader).tooltip)
        assert "5 Tuning loop · STALE: prompt changed" in tip
        assert "8 Full run · STALE: prompt changed" in tip
        assert "Search" not in tip


async def test_rail_follows_a_file_change_without_a_navigation():
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert "↻" not in "\n".join(rail_lines(app))
        edit_prompt()
        await pilot.pause(0.6)
        assert "↻" in next(ln for ln in rail_lines(app) if "Full run" in ln)


async def test_status_is_reused_for_a_moment_so_the_poll_does_not_rescan(monkeypatch):
    import hunches.app as app_module

    monkeypatch.setattr(app_module, "STATUS_AGE", 0.5)
    seen = []
    real = files.stage_status
    monkeypatch.setattr(files, "stage_status", lambda: seen.append(1) or real())
    app_module.current_status(fresh=True)
    for _ in range(5):
        app_module.current_status()
    assert len(seen) == 1
    await asyncio.sleep(0.6)
    app_module.current_status()
    assert len(seen) == 2
    app_module.current_status(fresh=True)
    assert len(seen) == 3


# ---- narrow header: stepper glyphs and a badge after the stage name ----------------------


async def test_narrow_header_shows_glyphs_in_the_stepper_and_a_stale_badge():
    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        text = header_text(app)
        # the classifier model has no price, so the long cost warning pushes the stage name out first
        assert "5/9 STALE" in text.replace("  ", " ")
        # stages 1-4 plain, 5 current but marked, 6-8 marked, 9 done
        assert text.count("↻") == 4
        assert "INCOMPLETE" not in text


async def test_narrow_header_badge_says_incomplete_for_an_incomplete_current_stage():
    files.write_gold([r for r in files.read_gold() if r.id != "d0"])
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.goto_stage(4)
        await pilot.pause()
        assert "INCOMPLETE" in header_text(app) and "◐" in header_text(app)


async def test_narrow_footer_gains_f9_while_something_is_marked_and_the_rail_replaces_it():
    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert "f9" in footer_keys(app)
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert "f9" not in footer_keys(app)


async def test_footer_has_no_f9_when_everything_is_current():
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert "f9" not in footer_keys(app)


# ---- banners on stages 5-9 -----------------------------------------------------------------

BANNERS = "StageBanner"


async def settle(app, pilot) -> None:
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


def write_test_result() -> None:
    """A test result computed under the current inputs, with the metrics the screen shows."""
    from hunches import metrics

    m = metrics.compute_metrics([{"a"}, {"a"}], [{"a"}, {"a"}], ["a", "off_topic"])
    import dataclasses

    files.write_text(
        "test_result.json",
        json.dumps(
            {
                "inputs": files.current_inputs("test_done"),
                "timestamp": "2026-10-06T12:00:00+00:00",
                "metrics": dataclasses.asdict(m),
                "disagreements": [],
            }
        ),
    )


def banner(screen):
    from hunches.app import StageBanner

    found = list(screen.query(StageBanner))
    assert len(found) == 1
    return found[0]


async def test_tuning_banner_says_the_results_are_current_but_need_approving_again():
    edit_prompt()  # the dev set runs on entering Tuning, so its results are current
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        assert app.stage == 5
        b = banner(app.screen)
        assert b.display and b.has_class("banner", "-stale")
        assert str(b.render()) == (
            "STALE: prompt changed. The results below are current. Approve again with F2."
            " F9 shows the redo plan."
        )


async def test_final_banner_for_a_current_result_that_was_accepted_under_older_inputs():
    edit_prompt()
    write_test_result()  # re-run after the change, not accepted again
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(6)
        await settle(app, pilot)
        b = app.screen.query_one("#banner")
        assert b.display
        assert str(b.render()) == (
            "STALE: prompt changed. The result below is current. Accept again with F2."
            " F9 shows the redo plan."
        )


async def test_threshold_banner_names_the_reason_and_what_to_do():
    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(7)
        await settle(app, pilot)
        b = banner(app.screen)
        assert b.display
        assert str(b.render()) == (
            "STALE: prompt changed. The rates below are for the current settings."
            " Choose a band and save the cutoff again. F9 shows the redo plan."
        )


async def test_full_run_banner_and_rerun_button_when_rows_come_from_another_prompt():
    edit_prompt()
    write_test_result()  # the new prompt was tested, so the untested block does not apply
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)  # the app opens on Tuning, which runs the dev set
        CALLS.clear()
        app.goto_stage(8)
        await settle(app, pilot)
        b = banner(app.screen)
        assert b.display
        assert str(b.render()) == (
            "STALE: prompt changed. results.jsonl was made with an earlier prompt. Re-run "
            "classifies those items again; items already cached cost nothing."
            " F9 shows the redo plan."
        )
        assert str(app.screen.query_one("#run-button", Button).label) == "Re-run  s"
        assert not CALLS


async def test_full_run_untested_block_takes_precedence_over_the_stale_banner():
    edit_prompt()  # no new test result: the existing block applies
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(8)
        await settle(app, pilot)
        assert not banner(app.screen).display
        assert app.screen.query_one("#blocked-text").display


async def test_browse_notice_is_a_warning_without_the_stale_prefix():
    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(9)
        await settle(app, pilot)
        b = banner(app.screen)
        assert b.display and b.has_class("banner", "-warning")
        assert str(b.render()) == (
            "Results are out of date: prompt changed. Press p to go to Full run and re-run."
        )


async def test_banners_are_hidden_when_the_stage_is_current():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for stage in (5, 7, 8, 9):
            app.goto_stage(stage)
            await settle(app, pilot)
            assert not banner(app.screen).display, stage


async def test_a_banner_follows_an_edit_made_while_the_screen_is_open():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.goto_stage(9)
        await settle(app, pilot)
        assert not banner(app.screen).display
        edit_prompt()
        await pilot.pause(0.7)
        assert banner(app.screen).display


# ---- Threshold classifies its sample again when the sample was made under other inputs ------


def store_sample_predictions() -> None:
    """The sample already has predictions, made under the inputs of `complete_project`."""
    sample = json.loads(files.read_text("threshold_sample.json") or "")
    files.write_text(
        "threshold_sample.json",
        json.dumps(
            {**sample, "predictions": {"c3": ["off_topic"], "c4": ["off_topic"]}}
        ),
    )


async def test_threshold_classifies_the_sample_again_after_a_prompt_change_like_the_plan_says():
    store_sample_predictions()
    edit_prompt()
    plan = {row["stage"]: row for row in classifier.redo_plan()}
    assert (plan[7]["live_calls"], plan[7]["cached_calls"]) == (2, 0)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)  # the app opens on Tuning
        CALLS.clear()
        app.goto_stage(7)
        await settle(app, pilot)
        assert sorted(CALLS) == [
            "s",
            "samp2",
        ]  # the two sampled items, as the plan said
        sample = json.loads(files.read_text("threshold_sample.json") or "")
        assert sample["predictions"] == {"c3": ["a"], "c4": ["a"]}
        assert sample["ids"][0] == ["c3", "c4"]  # same items, new predictions
        assert files.changed(sample["inputs"]) == []
        CALLS.clear()
        app.goto_stage(7)
        await settle(app, pilot)
        assert not CALLS  # now current: nothing is classified again


async def test_threshold_draws_a_new_sample_when_the_candidates_changed():
    store_sample_predictions()
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": f"n{i}", "text": f"new{i}", "max_similarity": 0.62, "best_seed": "x"}
            for i in range(4)
        ],
    )  # a new search: none of the sampled ids is in the pool any more
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        assert app.stage == 7  # the first stage that is not current
        sample = json.loads(files.read_text("threshold_sample.json") or "")
        ids = {i for band in sample["ids"] for i in band}
        assert ids == {"n0", "n1", "n2", "n3"}
        assert sorted(CALLS) == ["new0", "new1", "new2", "new3"]
        assert set(sample["predictions"]) == ids


# ---- the Redo plan (F9) -------------------------------------------------------------------------


def plan_rows(screen) -> list[list[str]]:
    from textual.widgets import DataTable

    table = screen.query_one("#plan", DataTable)
    return [[str(c) for c in table.get_row_at(i)] for i in range(table.row_count)]


def priced(monkeypatch) -> None:
    """Every classifier call costs $1 on average (the plan's own arithmetic is tested in test_redo_plan)."""
    from hunches import cost

    monkeypatch.setattr(cost, "per_call_dollars", lambda model: (1.0, True))


async def open_plan(app, pilot):
    from hunches.screens.redo_plan import RedoPlanScreen

    await pilot.press("f9")
    await pilot.pause()
    assert isinstance(app.screen, RedoPlanScreen), app.screen
    return app.screen


def approvals() -> list[dict]:
    return [e for e in history.entries() if e["kind"] == "approval"]


async def test_f9_lists_the_stale_stages_in_order_with_counts_and_dollars_and_calls_nothing(
    monkeypatch,
):
    priced(monkeypatch)
    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(
            app, pilot
        )  # Tuning runs the dev set with the new prompt: 3 calls, now cached
        CALLS.clear()
        screen = await open_plan(app, pilot)
        assert plan_rows(screen) == [
            ["▸ 5 Tuning loop", "STALE · prompt changed", "0", "3", "$0.0000"],
            ["↻ 6 Gold test set", "STALE · prompt changed", "3", "0", "$3.0000"],
            ["↻ 7 Threshold", "STALE · prompt changed", "2", "0", "$2.0000"],
            ["↻ 8 Full run", "STALE · prompt changed", "2", "0", "$2.0000"],
            ["Still to do", "", "7", "3", "$7.0000"],
        ]
        assert not CALLS  # the plan counts cache keys; it classifies nothing


async def test_plan_shows_a_question_mark_for_an_unknown_price_never_zero():
    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)  # the dev run records m1 calls whose price is unknown
        screen = await open_plan(app, pilot)
        rows = plan_rows(screen)
        assert [r[4] for r in rows] == [
            "$0.0000",
            "?",
            "?",
            "?",
            "?",
        ]  # 5 is fully cached: free
        text = str(screen.query_one("#plan-note").render())
        assert text == "No price for m1: dollars show ? and are not counted as $0."


async def test_plan_shows_a_dot_for_stages_without_model_calls(monkeypatch):
    priced(monkeypatch)
    files.write_gold(
        [r for r in files.read_gold() if r.id != "d0"]
    )  # stage 4 incomplete
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        assert app.stage == 4
        screen = await open_plan(app, pilot)
        assert plan_rows(screen) == [
            ["▸ 4 Gold dev set", "INCOMPLETE · 2 of 3 rows", "·", "·", "·"],
            ["↻ 5 Tuning loop", "STALE · gold rows changed", "2", "0", "$2.0000"],
            ["Still to do", "", "2", "0", "$2.0000"],
        ]


async def test_primary_button_goes_to_the_earliest_stage_and_approves_nothing(
    monkeypatch,
):
    priced(monkeypatch)
    files.write_gold([r for r in files.read_gold() if r.id != "d0"])
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        app.goto_stage(9)
        await settle(app, pilot)
        before = (files.read_state(), len(approvals()))
        screen = await open_plan(app, pilot)
        go = screen.query_one("#go")
        assert str(go.label) == "Go to Gold dev set  Enter" and go.has_focus
        await pilot.press("enter")
        await settle(app, pilot)
        assert app.stage == 4 and app.plan_active
        assert (files.read_state(), len(approvals())) == before  # nothing was approved


async def test_close_leaves_the_plan_and_a_later_approval_does_not_reopen_it():
    from hunches.screens.redo_plan import RedoPlanScreen

    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        await open_plan(app, pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, RedoPlanScreen) and not app.plan_active
        await pilot.press("f2")  # approve Tuning again
        await settle(app, pilot)
        assert app.stage == 6 and not isinstance(app.screen, RedoPlanScreen)


async def test_the_plan_reopens_on_the_next_stage_after_a_re_approval():
    edit_prompt()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        await open_plan(app, pilot)
        await pilot.press("enter")  # Go to Tuning loop
        await settle(app, pilot)
        assert app.stage == 5 and app.plan_active
        await pilot.press(
            "f2"
        )  # the user approves Tuning again; the dev run is current
        await settle(app, pilot)
        plan = app.screen
        from hunches.screens.redo_plan import RedoPlanScreen

        assert isinstance(plan, RedoPlanScreen)
        assert [r[0] for r in plan_rows(plan)][:2] == [
            "✓ 5 Tuning loop",
            "▸ 6 Gold test set",
        ]
        assert plan_rows(plan)[0][1] == "approved again"
        assert str(plan.query_one("#intro").render()) == (
            "Tuning loop approved again. Next stale stage: Gold test set. Nothing is "
            "approved for you; each stage needs your approval."
        )
        assert str(plan.query_one("#go").label) == "Continue to Gold test set  Enter"
        assert (
            len(approvals()) == 5 + 1
        )  # complete_project approved five flags; one more now


async def test_the_finished_plan_says_all_stages_are_current_and_only_offers_close():
    from textual.widgets import Button

    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        app.plan_active = True
        app.plan_done = (5,)
        app.open_plan()
        await pilot.pause()
        screen = app.screen
        assert str(screen.query_one("#intro").render()) == "All stages are current."
        assert [b.id for b in screen.query(Button)] == ["close"]
        await pilot.press("escape")
        await pilot.pause()
        assert not app.plan_active


async def test_f9_does_nothing_when_everything_is_current():
    from hunches.screens.redo_plan import RedoPlanScreen

    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press("f9")
        await pilot.pause()
        assert not isinstance(app.screen, RedoPlanScreen)


# ---- embedding-model change: Search warning, Project settings note ---------------------------


def switch_embedding_model(model="e2") -> None:
    files.write_config(
        files.read_config().model_copy(update={"embedding_model": model})
    )


async def test_search_warns_when_the_embedding_model_differs_from_the_candidates():
    switch_embedding_model()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        assert app.stage == 2  # stage 2 is stale: the first stage that is not current
        screen = app.screen
        warning = screen.query_one("#embedding-warning")
        assert warning.display and warning.has_class("banner", "-warning")
        assert str(warning.render()) == (
            "WARNING: this project now uses the embedding model e2, but the current candidates "
            "were built with e1. Run the search again. Expect gold rows to be reported as no "
            "longer in the pool."
        )
        assert str(screen.query_one("#status").render()) == (
            "Embedding model changed, rerun needed"
        )
        assert str(screen.query_one("#run", Button).label) == "Run search  r"


async def test_search_has_no_embedding_warning_when_the_model_is_the_same_or_unrecorded():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        app.goto_stage(2)
        await settle(app, pilot)
        assert not app.screen.query_one("#embedding-warning").display
    meta = json.loads(files.read_text("candidates.meta.json") or "")
    del meta["embedding_model"]  # a project from before 004
    files.write_text("candidates.meta.json", json.dumps(meta))
    switch_embedding_model()
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        app.goto_stage(2)
        await settle(app, pilot)
        assert not app.screen.query_one("#embedding-warning").display


async def test_search_reruns_after_an_embedding_change_without_the_nothing_changed_question(
    monkeypatch,
):
    from hunches.app import ConfirmScreen
    from hunches.screens.search import SearchScreen

    switch_embedding_model()
    started = []
    monkeypatch.setattr(SearchScreen, "start", lambda self: started.append(1))
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press("r")
        await pilot.pause()
        assert started == [1] and not isinstance(app.screen, ConfirmScreen)


async def test_search_shows_nothing_extra_when_the_candidates_match(monkeypatch):
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        app.goto_stage(2)
        await settle(app, pilot)
        assert str(app.screen.query_one("#run", Button).label) == "Rerun search  r"
        assert not app.screen.query_one("#status").display


async def test_a_plan_ends_by_itself_once_nothing_is_marked_so_a_later_approval_does_not_reopen_it():
    from hunches.screens.redo_plan import RedoPlanScreen

    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        # the plan was started and the user redid everything (stage 8 has no approval to reopen on)
        app.plan_active, app.plan_stages = True, (5, 8)
        app.goto_stage(9)  # entering a stage checks the history
        await settle(app, pilot)
        assert not app.plan_active
        files.approve(
            "dev_done", 5, "Approved: Tuning loop"
        )  # a later, unrelated approval
        app.check_history()
        await pilot.pause()
        assert not isinstance(app.screen, RedoPlanScreen)


def test_no_text_widget_binds_f9():
    from textual.widgets import Input, TextArea

    for widget in (Input, TextArea):
        assert "f9" not in {b.key for b in widget.BINDINGS if hasattr(b, "key")}


async def test_the_last_re_approval_reopens_the_plan_to_say_all_stages_are_current():
    from hunches.screens.redo_plan import RedoPlanScreen

    rows = files.read_gold()
    rows[0] = rows[0].model_copy(
        update={"labels": ["off_topic"]}
    )  # only Tuning goes stale
    files.write_gold(rows)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        assert [r["stage"] for r in classifier.redo_plan()] == [5]
        await open_plan(app, pilot)
        await pilot.press("enter")
        await settle(app, pilot)
        await pilot.press("f2")
        await pilot.pause()
        await pilot.click("#yes")  # the target is no longer met: approve anyway
        await settle(app, pilot)
        assert isinstance(app.screen, RedoPlanScreen)
        assert str(app.screen.query_one("#intro").render()) == "All stages are current."
