from typing import ClassVar

from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header


class HunchesApp(App):
    TITLE = "hunches"
    BINDINGS: ClassVar = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()


def main() -> None:
    load_dotenv()
    HunchesApp().run()
