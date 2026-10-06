import asyncio

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.app import App
from textual.screen import Screen
from textual.widgets import Button, Static

from hunches import files
from hunches.classifier import classify_many
from hunches.screens.progress import LabelBar, RunIndicator, eta_text, seconds_text


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


def test_seconds_text_trims_leading_zero_minutes():
    assert seconds_text(14) == "14s"
    assert seconds_text(65) == "1m05s"
    assert seconds_text(3720) == "1h02m"


def test_eta_text_needs_three_live_completions():
    assert eta_text(10, 50, 2, 20) is None
    assert eta_text(10, 50, 0, 20) is None  # everything came from the cache
    # (50 - 10) * 20 / 10 = 80 s
    assert eta_text(10, 50, 10, 20) == "1m20s"
    # (5 - 3) * 6 / 3 = 4 s
    assert eta_text(3, 5, 3, 6) == "4s"


class IndicatorHost(App):
    def compose(self):
        yield RunIndicator()


async def test_run_indicator_counts_line_with_and_without_eta():
    async with IndicatorHost().run_test(size=(80, 24)) as pilot:
        ind = pilot.app.query_one(RunIndicator)
        ind.set_title("Running the dev set")
        ind.set_progress(23, 50)
        await pilot.pause()
        assert str(ind.query_one("#run-title", Static).content) == "Running the dev set"
        assert str(ind.query_one("#run-counts", Static).content) == "23 of 50"
        bar = ind.query_one(LabelBar)
        assert (bar.total, bar.value) == (50, 23)
        assert bar.region.width == 36
        ind.set_progress(23, 50, eta="14s")
        await pilot.pause()
        counts = ind.query_one("#run-counts", Static).content
        assert str(counts) == "23 of 50 \u00b7 about 14s left"
        ind.set_progress(50, 50)
        await pilot.pause()
        assert bar.has_class("-complete")


async def test_run_indicator_status_and_button_slot():
    async with IndicatorHost().run_test(size=(80, 24)) as pilot:
        ind = pilot.app.query_one(RunIndicator)
        status = ind.query_one("#run-status", Static)
        assert not status.display
        ind.set_status("1 failed", "error")
        await pilot.pause()
        assert status.display and status.has_class("error")
        assert str(status.content) == "1 failed"
        ind.set_status("")
        await pilot.pause()
        assert not status.display
        button = ind.query_one("#run-button", Button)
        assert not button.display  # no button until asked
        for kind, label in [
            ("stop", "Stop  x"),
            ("resume", "Resume  s"),
            ("start", "Start  s"),
        ]:
            ind.set_button(kind)
            await pilot.pause()
            assert button.display and str(button.label) == label
        ind.set_button(None)
        await pilot.pause()
        assert not button.display


def respond(messages, info: AgentInfo):
    calls.append(1)
    return ModelResponse(
        parts=[
            ToolCallPart(info.output_tools[0].name, {"reasoning": "r", "labels": ["a"]})
        ]
    )


calls: list[int] = []


class StubRun(Screen):
    """The pattern tasks 12 to 15 follow: own `running`/`stopped`, keep the worker, try/finally."""

    BINDINGS = [("x", "stop", "Stop"), ("s", "start", "Start")]  # noqa: RUF012

    def __init__(self):
        super().__init__()
        self.running = self.stopped = False
        self.done = 0
        self.parked = False
        self.worker = None

    def compose(self):
        yield RunIndicator()

    def action_start(self) -> None:
        if self.running:
            return
        self.running, self.stopped = True, False
        self.worker = self.run_worker(self.run(), exclusive=True)

    def action_stop(self) -> None:
        if self.worker is not None:
            self.worker.cancel()

    async def run(self) -> None:
        ind = self.query_one(RunIndicator)
        ind.set_button("stop")
        self.done = 0
        try:
            async for _i, _p in classify_many(
                [f"t{n}" for n in range(6)],
                "p",
                files.read_taxonomy(),
                FunctionModel(respond),
                concurrency=1,
            ):
                self.done += 1
                ind.set_progress(self.done, 6)
                if self.done == 3 and not self.parked:
                    self.parked = True
                    await asyncio.sleep(30)  # parked until the user stops
        finally:
            self.running = False
            self.stopped = self.done < 6
            if self.is_attached:  # a removed screen has no widgets left to update
                ind.set_button("resume" if self.stopped else None)


async def wait_for(pilot, test):
    for _ in range(200):
        if test():
            return
        await pilot.pause(0.02)
    raise AssertionError("timed out")


async def test_stop_keeps_count_and_resume_pays_nothing_twice(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.write_taxonomy(files.Taxonomy(mode="single", labels=[files.Label(name="a")]))
    calls.clear()

    class Host(App):
        def on_mount(self):
            self.push_screen(StubRun())

    async with Host().run_test(size=(80, 24)) as pilot:
        screen = pilot.app.screen
        assert isinstance(screen, StubRun)
        await pilot.press("s")
        await wait_for(pilot, lambda: screen.done == 3)
        await pilot.press("x")
        await wait_for(pilot, lambda: screen.stopped)
        assert not screen.running and screen.done == 3
        ind = screen.query_one(RunIndicator)
        assert str(ind.query_one("#run-button", Button).label) == "Resume  s"
        assert str(ind.query_one("#run-counts", Static).content) == "3 of 6"
        assert len(calls) >= 3  # items still in flight at Stop may have finished too
        await pilot.press("s")
        await wait_for(pilot, lambda: screen.done == 6 and not screen.running)
        assert not screen.stopped
        assert (
            len(calls) == 6
        )  # one call per text in total: finished items came from the cache


async def test_leaving_the_screen_cancels_its_worker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.write_taxonomy(files.Taxonomy(mode="single", labels=[files.Label(name="a")]))
    calls.clear()

    class Host(App):
        def on_mount(self):
            self.push_screen(StubRun())

    async with Host().run_test(size=(80, 24)) as pilot:
        screen = pilot.app.screen
        assert isinstance(screen, StubRun)
        await pilot.press("s")
        await wait_for(pilot, lambda: screen.done == 3)
        await pilot.app.pop_screen()
        await pilot.pause()
        await wait_for(
            pilot, lambda: screen.worker is not None and screen.worker.is_cancelled
        )
        assert not screen.running
