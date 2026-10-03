"""Projects: the registered projects, their health, and open / remove / delete."""

from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Input, Static

from hunches import files, system
from hunches.app import StatusHeader
from hunches.screens.new_project import NewProjectScreen
from hunches.screens.paths import PathPicker


def describe(project: system.Project) -> tuple[list[str], str, str]:
    """(Name, Backend, Where, Status, Opened) cells, the status word and its detail."""
    path = Path(project.path)
    status, detail = system.project_status(path)
    backend, where = "?", ""
    if status != "MISSING DIR" and status != "NO CONFIG":
        config = files.read_config(path)
        backend = config.backend
        where = (
            f"{config.s3_bucket}/{config.s3_index}"
            if backend == "s3"
            else config.corpus_dir or ""
        )
    cells = [path.name, backend, where, status, project.last_opened[:10]]
    return cells, status, detail


class RemoveModal(ModalScreen[str | None]):
    """Dismisses "remove", "delete" or None. Focus starts on the safe action."""

    AUTO_FOCUS = "#remove"
    DEFAULT_CSS = """
    RemoveModal > Vertical {
        width: 100%; max-width: 78; height: auto; max-height: 100%;
        border: round $primary; background: $surface; padding: 0 1;
    }
    RemoveModal Horizontal { height: auto; }
    """

    def __init__(self, name: str) -> None:
        super().__init__()
        self.project_name = name

    def compose(self) -> ComposeResult:
        with Vertical() as box:
            box.border_title = f"Remove {self.project_name}"
            yield Static(
                "Remove from list keeps every file. Delete project files removes "
                "only this project's .hunches/ folder: never the corpus, never S3. "
                "hunches does not run git, so committed history is unaffected.",
                classes="note",
            )
            with Horizontal():
                yield Button("Remove from list", id="remove", compact=True)
                yield Button("Cancel", id="cancel", compact=True)
            yield Input(
                placeholder=f"type {self.project_name} to enable delete",
                id="confirm",
                compact=True,
            )
            yield Button(
                "Delete project files", id="delete", disabled=True, compact=True
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        self.query_one("#delete", Button).disabled = event.value != self.project_name

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None if event.button.id == "cancel" else event.button.id)


class ProjectsScreen(Screen):
    stage_name = "Projects"
    BINDINGS: ClassVar = [
        ("n", "new", "New"),
        ("r", "refresh", "Refresh"),
        ("x", "remove", "Remove"),
        ("l", "locate", "Locate"),
        ("escape", "back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield StatusHeader()
        yield Static("", id="banner", classes="banner -warning")
        yield DataTable(cursor_type="row", zebra_stripes=True)
        yield Static(
            "No projects yet. Press n to create one.", id="empty", classes="note"
        )
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_projects()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.app.open_project(str(event.row_key.value))  # ty: ignore[unresolved-attribute]

    def current(self) -> str | None:
        """Path of the highlighted project."""
        table = self.query_one(DataTable)
        if not table.row_count:
            return None
        return str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)

    def action_new(self) -> None:
        self.app.push_screen(NewProjectScreen())

    def action_locate(self) -> None:
        path = self.current()
        if path is None:
            return
        status, _ = system.project_status(path)

        def moved_project(new: Path | None) -> None:
            if new is not None:
                system.remove_project(path)
                system.add_project(new)
                self.refresh_projects()

        def moved_corpus(new: Path | None) -> None:
            if new is not None:
                config = files.read_config(Path(path))
                config.corpus_dir = str(new)
                files.write_config(config, Path(path))
                self.refresh_projects()

        if status == "MISSING DIR":
            self.app.push_screen(PathPicker(Path(path).parent), moved_project)
        elif status == "MISSING CORPUS":
            self.app.push_screen(PathPicker(Path(path)), moved_corpus)

    def action_remove(self) -> None:
        path = self.current()
        if path is None:
            return

        def done(choice: str | None) -> None:
            if choice == "remove":
                system.remove_project(path)
            elif choice == "delete":
                current = Path.cwd().resolve() == Path(path).resolve()
                if current and any(w.is_running for w in self.app.workers):
                    self.app.notify(
                        "A run is in progress in this project; stop it first",
                        severity="error",
                    )
                else:
                    try:
                        system.delete_project_files(path)
                    except (OSError, ValueError) as e:
                        self.app.notify(f"Cannot delete: {e}", severity="error")
            self.refresh_projects()

        self.app.push_screen(RemoveModal(Path(path).name), done)

    def action_back(self) -> None:
        """Back to the open project (this screen was pushed over its stage)."""
        if self.app.stage and (files.root() / "config.toml").exists():  # ty: ignore[unresolved-attribute]
            self.app.pop_screen()

    def action_refresh(self) -> None:
        self.refresh_projects()

    def refresh_projects(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Backend", "Where", "Status", "Opened")
        problems = 0
        listed = system.projects_by_recent()
        table.display = bool(listed)
        self.query_one("#empty").display = not listed
        for project in listed:
            cells, status, _ = describe(project)
            problems += not status.startswith("OK")
            table.add_row(*cells, key=project.path)
        banner = self.query_one("#banner", Static)
        banner.update(f"{problems} projects need attention")
        banner.display = bool(problems)
