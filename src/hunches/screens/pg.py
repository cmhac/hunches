"""The pgvector form section shared by New project and Project settings.

The widgets use fixed ids (#pg, #pg-table, ... #check-pg); the host screen calls
compose_pg() inside its layout and routes Select/Input/Button events here."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Select, Static

from hunches import files, keys, system

PG_CSS = "#pg { height: auto; }"  # the host screen supplies the .row rules

FIELDS = [  # (input id, label, config field); empty = unset, the default shows as placeholder
    ("pg-table", "table", "pg_table"),
    ("pg-id", "id col", "pg_id_column"),
    ("pg-text", "text col", "pg_text_column"),
    ("pg-vector", "vector col", "pg_vector_column"),
    ("pg-url-var", "url var", "pg_url_var"),
]


def compose_pg() -> ComposeResult:
    """Everything in the section except the embedding model (the host owns that row)."""
    with Vertical(id="pg"):
        for id_, label, field in FIELDS:
            with Horizontal(classes="row"):
                yield Label(label)
                yield Input(
                    placeholder=files.PG_DEFAULTS.get(field, ""),
                    id=id_,
                    compact=True,
                )
                if id_ == "pg-url-var":
                    yield Static("", id="pg-url-status")
        with Horizontal(classes="row"):
            yield Label("url")
            yield Input(
                password=True, placeholder="paste URL", id="pg-url", compact=True
            )
            yield Button("Save URL…", id="save-url", compact=True)
        with Horizontal(classes="row"):
            yield Label("auth")
            yield Select(
                [("URL", "url"), ("RDS IAM", "rds_iam")],
                value="url",
                allow_blank=False,
                compact=True,
                id="pg-auth",
            )
        with Horizontal(classes="row", id="pg-region-row"):
            yield Label("region")
            yield Input(placeholder="optional", id="pg-region", compact=True)
        with Horizontal(classes="row", id="pg-profile-row"):
            yield Label("profile")
            yield Input(placeholder="optional", id="pg-profile", compact=True)
        with Horizontal(classes="row"):
            yield Label("search")
            yield Select(
                [("Exact", "exact"), ("Index", "index")],
                value="exact",
                allow_blank=False,
                compact=True,
                id="pg-search",
            )
        with Horizontal(classes="row"):
            yield Label("timeout")
            yield Input(placeholder="seconds, optional", id="pg-timeout", compact=True)
        yield Static("", id="pg-status")
        yield Button("Check store", id="check-pg", compact=True)


def pg_mount(screen: Screen) -> None:
    screen.query_one("#pg").display = False
    pg_refresh(screen)


def pg_refresh(screen: Screen) -> None:
    """Rows that depend on other widgets: region and profile only for rds_iam; the URL status."""
    iam = screen.query_one("#pg-auth", Select).value == "rds_iam"
    screen.query_one("#pg-region-row").display = iam
    screen.query_one("#pg-profile-row").display = iam
    screen.query_one("#pg-url-status", Static).update(keys.status(url_var(screen)))


def url_var(screen: Screen) -> str:
    value = screen.query_one("#pg-url-var", Input).value.strip()
    return value or files.PG_DEFAULTS["pg_url_var"]


def text(screen: Screen, id_: str) -> str:
    return screen.query_one(f"#{id_}", Input).value.strip()


def timeout_problem(screen: Screen) -> str:
    value = text(screen, "pg-timeout")
    return "" if not value or value.isdigit() else "timeout must be whole seconds"


def pg_fields(screen: Screen) -> dict:
    """The pg_* config fields for the form; unset (None) when left empty or at the default."""
    iam = screen.query_one("#pg-auth", Select).value == "rds_iam"
    fields: dict = {f: text(screen, i) or None for i, _, f in FIELDS}
    fields |= {
        "pg_search": "index"
        if screen.query_one("#pg-search", Select).value == "index"
        else None,
        "pg_statement_timeout_s": int(text(screen, "pg-timeout"))
        if text(screen, "pg-timeout").isdigit()
        else None,
        "pg_auth": "rds_iam" if iam else None,
        "pg_aws_region": (text(screen, "pg-region") or None) if iam else None,
        "pg_aws_profile": (text(screen, "pg-profile") or None) if iam else None,
    }
    return fields


def pg_select_changed(screen: Screen, event: Select.Changed) -> None:
    if event.select.id == "pg-auth":
        pg_refresh(screen)


def pg_input_changed(screen: Screen, event: Input.Changed) -> None:
    if event.input.id == "pg-url-var":
        pg_refresh(screen)


def pg_pressed(screen: Screen, button: str, embedding: str) -> bool:
    """Handle the section's buttons; False when the button is not ours."""
    if button == "save-url":
        box = screen.query_one("#pg-url", Input)
        if box.value:
            saved = keys.save(url_var(screen), box.value)
            box.value = ""  # the URL never stays in a widget
            show(
                screen,
                "URL saved in the keyring"
                if saved
                else "ERROR: no keyring available; set the variable in the environment",
            )
        pg_refresh(screen)
    elif button == "check-pg":
        check(screen, embedding)
    else:
        return False
    return True


def show(screen: Screen, message: str) -> None:
    screen.query_one("#pg-status", Static).update(message)


def check(screen: Screen, embedding: str) -> None:
    """search.check_store in a thread: the only network call on the screen."""
    from hunches import search

    if not text(screen, "pg-table"):
        show(screen, "Required: table")
        return
    if problem := timeout_problem(screen):
        show(screen, f"ERROR: {problem}")
        return
    current = system.read_system()
    assert current
    config = files.Config(
        backend="pgvector",
        embedding_model=embedding,
        assistant_model=current.assistant_model,
        classifier_model=current.classifier_model,
        **pg_fields(screen),
    )
    button = screen.query_one("#check-pg", Button)
    button.disabled = True
    show(screen, "checking…")

    def run() -> None:
        result = search.check_store(config)
        screen.app.call_from_thread(done, screen, result)

    screen.run_worker(run, thread=True)


def done(screen: Screen, result: dict) -> None:
    show(screen, "\n".join(report(result)))
    screen.query_one("#check-pg", Button).disabled = False


def report(result: dict) -> list[str]:
    """Markup lines for a check_store result. WARNING and ERROR are words, colour only adds."""
    if result["errors"]:
        # a missing table repeats Postgres's text under several pieces: show it once
        lines = [f"[$error]ERROR: {escape(next(iter(result['errors'].values())))}[/]"]
    else:
        lines = []
    if result["version"]:
        encrypted = {True: "encrypted", False: "not encrypted"}.get(
            result["encrypted"], "encryption unknown"
        )
        lines.append(
            f"pgvector {'.'.join(map(str, result['version']))} in schema "
            f"{escape(str(result['schema']))}, {encrypted}"
        )
    if result["type"]:
        dimension = "?" if result["dimension"] is None else result["dimension"]
        lines.append(f"column type {escape(result['type'])}, dimension {dimension}")
    if result["rows"] is not None:
        lines.append(f"~{result['rows']:,} rows (planner estimate)")
    lines += [
        f"index {escape(name)} ({escape(method)}, {escape(opclass)})"
        for name, method, opclass in result["indexes"]
    ]
    if result["sample"]:
        row_id, row_text = result["sample"]
        lines.append(f"sample: {escape(str(row_id))} {escape(row_text)}")
    lines += [f"[$warning]WARNING: {escape(w)}[/]" for w in result["warnings"]]
    lines += [escape(n) for n in result["notes"]]
    return lines
