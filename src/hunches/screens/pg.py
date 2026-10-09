"""The pgvector form section shared by New project and Project settings.

The widgets use fixed ids (#pg, #pg-table, ... #check-pg); the host screen calls
compose_pg() inside its layout and routes Select/Button events here. A pasted URL is saved
in the keyring (under search.pg_url_name of its id) by Check store, Create and Save."""

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
    ("pg-text-table", "text table", "pg_text_table"),
    ("pg-text-id", "text id col", "pg_text_id_column"),
    ("pg-text", "text col", "pg_text_column"),
    ("pg-vector", "vector col", "pg_vector_column"),
]
TWO_TABLE_INPUTS = ("pg-text-table", "pg-text-id")
LAYOUT_HELP = {
    "one": "One table (or view) has the id, text and vector columns.",
    "two": "Vectors in table, text in text table, joined where text id col = id col "
    "(empty: same name). For when you cannot create a view.",
}


class PgSection(Vertical):
    """The section; holds which saved URL the form uses (never the URL itself)."""

    url_id: str | None = None
    url_var: str | None = None  # a hand-written pg_url_var, kept until a URL is pasted


def section(screen: Screen) -> PgSection:
    return screen.query_one("#pg", PgSection)


def url_name(screen: Screen) -> str:
    from hunches import search

    return search.pg_url_name(section(screen).url_id, section(screen).url_var)


def compose_pg() -> ComposeResult:
    """Everything in the section except the embedding model (the host owns that row)."""
    with PgSection(id="pg"):
        with Horizontal(classes="row"):
            yield Label("layout")
            yield Select(
                [("One table", "one"), ("Two tables", "two")],
                value="one",
                allow_blank=False,
                compact=True,
                id="pg-layout",
            )
        yield Static(LAYOUT_HELP["one"], id="pg-layout-help")
        for id_, label, field in FIELDS:
            with Horizontal(classes="row", id=f"{id_}-row"):
                yield Label(label)
                yield Input(
                    placeholder="same as id col"
                    if id_ == "pg-text-id"
                    else files.PG_DEFAULTS.get(field, ""),
                    id=id_,
                    compact=True,
                )
        with Horizontal(classes="row"):
            yield Label("url")
            yield Input(
                password=True,
                placeholder="paste URL (saved in the keyring)",
                id="pg-url",
                compact=True,
            )
            yield Static("", id="pg-url-status")
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
    """Rows that depend on other widgets: the text table rows only for two tables, region and
    profile only for rds_iam; the URL status."""
    layout = str(screen.query_one("#pg-layout", Select).value)
    screen.query_one("#pg-layout-help", Static).update(LAYOUT_HELP[layout])
    for id_ in TWO_TABLE_INPUTS:
        screen.query_one(f"#{id_}-row").display = layout == "two"
    iam = screen.query_one("#pg-auth", Select).value == "rds_iam"
    screen.query_one("#pg-region-row").display = iam
    screen.query_one("#pg-profile-row").display = iam
    screen.query_one("#pg-url-status", Static).update(keys.status(url_name(screen)))


def text(screen: Screen, id_: str) -> str:
    return screen.query_one(f"#{id_}", Input).value.strip()


def two_tables(screen: Screen) -> bool:
    return screen.query_one("#pg-layout", Select).value == "two"


def pg_missing(screen: Screen) -> list[str]:
    """The required pgvector fields left empty, as labels."""
    missing = ["table"] * (not text(screen, "pg-table"))
    if two_tables(screen) and not text(screen, "pg-text-table"):
        missing.append("text table")
    return missing


def timeout_problem(screen: Screen) -> str:
    value = text(screen, "pg-timeout")
    return "" if not value or value.isdigit() else "timeout must be whole seconds"


def pg_fields(screen: Screen) -> dict:
    """The pg_* config fields for the form; unset (None) when left empty or at the default."""
    iam = screen.query_one("#pg-auth", Select).value == "rds_iam"
    fields: dict = {
        f: None
        if i in TWO_TABLE_INPUTS and not two_tables(screen)
        else text(screen, i) or None
        for i, _, f in FIELDS
    }
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
        "pg_url_id": section(screen).url_id,
        "pg_url_var": section(screen).url_var,
    }
    return fields


def pg_select_changed(screen: Screen, event: Select.Changed) -> None:
    if event.select.id in ("pg-auth", "pg-layout"):
        pg_refresh(screen)


def pg_pressed(screen: Screen, button: str, embedding: str) -> bool:
    """Handle the section's buttons; False when the button is not ours."""
    if button != "check-pg":
        return False
    check(screen, embedding)
    return True


def pg_save_url(screen: Screen) -> bool:
    """Save a pasted URL in the keyring unless it is already there, then clear the box.

    The section then points at it (url_id). False, with the reason shown, when it could
    not be saved; True when nothing was pasted."""
    from hunches import search

    box = screen.query_one("#pg-url", Input)
    url = box.value.strip()
    if not url:
        return True
    try:
        url_id = search.pg_url_id(url)
    except (ValueError, ImportError) as e:
        show(screen, f"ERROR: {escape(str(e))}")
        return False
    name = search.pg_url_name(url_id, None)
    if keys.resolve(name) != url and not keys.save(name, url):
        show(screen, f"ERROR: no keyring available; set {name} in the environment")
        return False
    box.value = ""  # the URL never stays in a widget
    section(screen).url_id, section(screen).url_var = url_id, None
    pg_refresh(screen)
    return True


def show(screen: Screen, message: str) -> None:
    screen.query_one("#pg-status", Static).update(message)


def check(screen: Screen, embedding: str) -> None:
    """search.check_store in a thread: the only network call on the screen."""
    from hunches import search

    if not pg_save_url(screen):
        return
    if missing := pg_missing(screen):
        show(screen, f"Required: {', '.join(missing)}")
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
