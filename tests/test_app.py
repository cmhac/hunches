from hunches.app import HunchesApp


async def test_app_starts_and_quits_on_q():
    app = HunchesApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
    assert app.return_code == 0
