from textual.app import App
from textual.widgets import Input, OptionList

from hunches import models
from hunches.screens.model_picker import ModelPicker


class PickApp(App):
    result = "unset"

    def __init__(self, embedding=False):
        super().__init__()
        self.embedding = embedding

    def on_mount(self):
        self.push_screen(ModelPicker(self.embedding), self.got)

    def got(self, model):
        self.result = model


def with_keys(monkeypatch, anthropic=False, openai=False):
    for var, on in (("ANTHROPIC_API_KEY", anthropic), ("OPENAI_API_KEY", openai)):
        if on:
            monkeypatch.setenv(var, "sk-test")
        else:
            monkeypatch.delenv(var, raising=False)


def fake_known(monkeypatch):
    with_keys(monkeypatch, openai=True)
    monkeypatch.setattr(
        models,
        "known_models",
        lambda embedding=False: [
            "openai:gpt-6-sol",
            "openai:gpt-6-luna",
            "anthropic:claude-haiku-4-5",
        ],
    )


async def test_lists_provider_models_with_prices_and_recommended_marker(monkeypatch):
    fake_known(monkeypatch)
    app = PickApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        options = app.screen.query_one(OptionList)
        text = [
            str(options.get_option_at_index(i).prompt)
            for i in range(options.option_count)
        ]
        assert len(text) == 3  # two openai models and Other…
        assert "openai:gpt-6-sol" in text[0] and "recommended" in text[0]
        assert "$2.00 in / $10.00 out per 1M tokens" in text[0]
        assert "claude" not in "".join(text)
        assert "Other" in text[2]


async def test_enter_on_row_returns_that_model(monkeypatch):
    fake_known(monkeypatch)
    app = PickApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("down", "enter")  # second row, gpt-6-luna
        await pilot.pause()
        assert app.result == "openai:gpt-6-luna"


async def test_escape_returns_none(monkeypatch):
    fake_known(monkeypatch)
    app = PickApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None


async def test_other_accepts_any_string_and_warns_when_not_in_known_list(monkeypatch):
    fake_known(monkeypatch)
    app = PickApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("down", "down", "enter")  # Other…
        await pilot.pause()
        box = app.screen.query_one("#other", Input)
        assert box.has_focus
        note = app.screen.query_one("#note")
        box.value = "openai:gpt-9"
        await pilot.pause()
        assert "not in known list" in str(note.render())
        box.value = "openai:gpt-6-sol"
        await pilot.pause()
        assert "not in known list" not in str(note.render())
        box.value = "openai:gpt-9"
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == "openai:gpt-9"


async def test_other_with_empty_value_does_not_dismiss(monkeypatch):
    fake_known(monkeypatch)
    app = PickApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("down", "down", "enter", "enter")
        await pilot.pause()
        assert app.result == "unset"


def option_text(app):
    options = app.screen.query_one(OptionList)
    return [
        str(options.get_option_at_index(i).prompt) for i in range(options.option_count)
    ]


async def test_both_keys_show_both_providers(monkeypatch):
    fake_known(monkeypatch)
    with_keys(monkeypatch, anthropic=True, openai=True)
    app = PickApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        text = "".join(option_text(app))
        assert "openai:gpt-6-sol" in text and "anthropic:claude-haiku-4-5" in text


async def test_anthropic_key_only_shows_anthropic(monkeypatch):
    fake_known(monkeypatch)
    with_keys(monkeypatch, anthropic=True)
    app = PickApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        text = "".join(option_text(app))
        assert "claude-haiku" in text and "gpt-6" not in text


async def test_no_keys_shows_no_models_and_says_why(monkeypatch):
    fake_known(monkeypatch)
    with_keys(monkeypatch)
    app = PickApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        text = option_text(app)
        assert len(text) == 1 and "Other" in text[0]
        assert "No API key" in str(app.screen.query_one("#note").render())
