import json
from types import SimpleNamespace

import pytest
import yaml
from conftest import panel_title
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from textual.widgets import Button, Input, Select, TextArea

from hunches import files
from hunches.app import ChatPanel, ConfirmScreen, HunchesApp
from hunches.screens import taxonomy as tx
from hunches.screens.taxonomy import TaxonomyScreen

pytestmark = pytest.mark.usefixtures("system_ready")

TWO = {
    "mode": "single",
    "labels": [
        {"name": "layoff", "description": "lost a job"},
        {"name": "fear", "description": "worried about a layoff"},
    ],
}
GOOD = {"mode": "multi", "labels": [{"name": "layoff", "description": "lost a job"}]}
BAD = {"mode": "single", "labels": [{"name": "off_topic", "description": ""}]}


# ---- pure builders: hand-computed values --------------------------------------------

ROWS = [
    {"id": "1", "text": "t1", "max_similarity": 0.61, "best_seed": "a"},
    {"id": "2", "text": "t2", "max_similarity": 0.70, "best_seed": "a"},
    {"id": "3", "text": "t3", "max_similarity": 0.80, "best_seed": "b"},
    {"id": "4", "text": "t4", "max_similarity": 0.80, "best_seed": "a"},
    {"id": "5", "text": "t5", "max_similarity": 0.66, "best_seed": "b"},
]
SEEDS = ["a", "b", "c"]


def test_initial_context_has_the_sections_and_items_won_add_up():
    body = tx.initial_context(["user: hello", "assistant: hi"], SEEDS, ROWS)
    headers = [line for line in body.splitlines() if line.startswith("# ")]
    assert headers == [
        "# Brief conversation",
        "# Seeds and results (items won)",
        "# Search",
        "# Instructions",
    ]
    assert "user: hello\nassistant: hi" in body
    # a won 3 (ids 1, 2, 4), b won 2 (ids 3, 5), c won 0; 3 + 2 + 0 = 5 candidates
    assert "     3  a\n     2  b\n     0  c" in body
    assert "5 candidates at or above 0.60" in body
    # bands: 0.6-0.625 has 0.61; 0.65-0.675 has 0.66; 0.7-0.725 has 0.70; 0.75+ has two
    assert "0.6-0.625: 1 · 0.625-0.65: 0 · 0.65-0.675: 1 · 0.675-0.7: 0" in body
    assert "0.7-0.725: 1 · 0.725-0.75: 0 · 0.75+: 2" in body
    assert "Reply in two or three sentences: where things stand (how many seeds" in body
    assert body.endswith("as the answers come in.")


def test_snapshot_counts_items_won():
    snap = tx.snapshot(SEEDS, ROWS)
    assert snap == {
        "seeds": SEEDS,
        "n_candidates": 5,
        "items_won": {"a": 3, "b": 2},
    }
    assert sum(snap["items_won"].values()) == snap["n_candidates"]


def test_update_context_says_what_changed():
    old = tx.snapshot(["a", "b"], ROWS[:3])  # a 2, b 1
    new = tx.snapshot(["a", "c"], ROWS)  # a 3 (b's two rows now count for nobody here)
    body = tx.update_context(old, new)
    assert body.startswith(
        "# What changed\nseeds: 1 added, 1 removed\n  + c\n  - b\ncandidates: 3 → 5\n"
    )
    assert "# Seeds and results (items won)\n     3  a\n     0  c" in body
    assert body.endswith(
        "Reply in one or two sentences: what changed and whether it affects the "
        "conversation so far. Then continue where you left off."
    )
    assert tx.update_summary(old, new) == "Seeds changed · 5 candidates (+2)"
    only_rows = tx.snapshot(["a", "b"], ROWS)
    assert tx.update_summary(old, only_rows) == "Search changed · 5 candidates (+2)"
    shrunk = tx.snapshot(["a", "b"], ROWS[:1])
    assert tx.update_summary(only_rows, shrunk) == "Search changed · 1 candidates (-4)"


def test_context_summary_line():
    assert tx.context_summary(SEEDS, ROWS) == "Context · 3 seeds · 5 candidates"
    many = [dict(ROWS[0], id=str(i)) for i in range(3612)]
    assert tx.context_summary(SEEDS, many) == "Context · 3 seeds · 3,612 candidates"


def test_digest_is_stable_and_sensitive():
    d = tx.context_digest(SEEDS, "rows\n")
    assert d == tx.context_digest(list(SEEDS), "rows\n")
    assert d != tx.context_digest(["a", "b"], "rows\n")
    assert d != tx.context_digest(SEEDS, "rows2\n")


def req(text: str, **kw):
    return ModelRequest(parts=[UserPromptPart(content=text)], **kw)


def test_brief_transcript_keeps_text_and_collapses_tools():
    messages = [
        req("Find layoffs"),
        ModelResponse(
            parts=[
                TextPart("Which kind?"),
                ToolCallPart("propose_seeds", {"seeds": ["x" * 200]}, "c1"),
            ]
        ),
        ModelRequest(parts=[ToolReturnPart("propose_seeds", "Added 1 seeds.", "c1")]),
        files.edit_message("Seed added", "+ 1  x"),  # edits are not conversation
    ]
    lines = tx.brief_transcript(messages)
    assert lines[0] == "user: Find layoffs"
    assert lines[1] == "assistant: Which kind?"
    assert lines[2].startswith("tool: propose_seeds ")
    assert lines[2].endswith("…") and len(lines[2]) < 120  # long arguments are cut
    assert len(lines) == 3


def test_brief_transcript_caps_at_forty_turns_with_a_visible_count():
    messages = [req(f"msg {i}") for i in range(47)]
    lines = tx.brief_transcript(messages)
    assert lines[0] == "… 7 more"
    assert lines[1] == "user: msg 7" and lines[-1] == "user: msg 46"
    assert len(lines) == 41
    assert tx.brief_transcript(messages[:40])[0] == "user: msg 0"


# ---- screen fixtures ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def calls(monkeypatch):
    """Every TaxonomyScreen gets a FunctionModel: no real model call is possible.

    `calls.prompts` holds the user prompt of each model call, `calls.instructions` the per-run
    instructions, `calls.returns` tool results seen by the model. A user message "write it"
    makes the model call `calls.tool` = (name, args).
    """
    log = SimpleNamespace(
        prompts=[], instructions=[], returns=[], tool=None, fail=False
    )

    async def stream(messages, info: AgentInfo):
        log.instructions.append(info.instructions)
        parts = messages[-1].parts
        returns = [p for p in parts if p.part_kind == "tool-return"]
        if returns:
            log.returns.append(str(returns[0].content))
            yield "Done."
            return
        prompt = [str(p.content) for p in parts if p.part_kind == "user-prompt"][-1]
        log.prompts.append(prompt)
        if log.fail:
            raise RuntimeError("boom")
        if prompt == "write it" and log.tool:
            name, args = log.tool
            yield {0: DeltaToolCall(name=name, json_args=json.dumps(args))}
        else:
            yield "Ready."

    original = TaxonomyScreen.__init__

    def init(self):
        original(self)
        self.agent.model = FunctionModel(stream_function=stream)

    monkeypatch.setattr(TaxonomyScreen, "__init__", init)
    return log


def setup(tmp_path, monkeypatch, seeds="seed\nx\ny\n", rows=True):
    monkeypatch.chdir(tmp_path)
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir="c",
            embedding_model="m",
        )
    )
    files.write_text("seeds.csv", seeds)
    files.write_text("brief.md", "Find layoff posts\n")
    if rows:
        files.write_jsonl(
            "candidates.jsonl",
            [
                {
                    "id": "1",
                    "text": "I lost my job",
                    "max_similarity": 0.8,
                    "best_seed": "x",
                },
                {
                    "id": "2",
                    "text": "laid off",
                    "max_similarity": 0.7,
                    "best_seed": "x",
                },
                {
                    "id": "3",
                    "text": "worried",
                    "max_similarity": 0.65,
                    "best_seed": "y",
                },
            ],
        )
    files.save_chat(
        "brief",
        [req("Find layoff posts"), ModelResponse(parts=[TextPart("Which kind?")])],
    )
    files.write_state(files.State(seeds_approved=True))


def with_files(taxonomy=TWO, prompt="# Prompt\nClassify the item.\n"):
    files.write_taxonomy(files.Taxonomy.model_validate(taxonomy))
    if prompt is not None:
        files.write_text("prompt.md", prompt)


async def start(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()
    assert isinstance(app.screen, TaxonomyScreen)
    return app.screen


def edits():
    return [
        m
        for m in files.load_chat("taxonomy")
        if isinstance(m, ModelRequest) and (m.metadata or {}).get("hunches") == "edit"
    ]


def meta():
    return json.loads(files.read_text("chat/taxonomy.meta.json") or "null")


async def edit_labels(pilot, screen):
    screen.query_one("#edit-labels", Button).focus()
    await pilot.press("e")
    await pilot.pause()


def names(screen) -> list[str]:
    return [i.value for i in screen.query(".label-name").results(Input)]


# ---- context turn -------------------------------------------------------------------


async def test_mount_without_history_sends_one_context_turn_then_writes_meta(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        assert len(calls.prompts) == 1
        body = calls.prompts[0]
        assert "user: Find layoff posts" in body and "assistant: Which kind?" in body
        assert "     2  x\n     1  y" in body  # x won 2, y won 1
        chat = screen.query_one(ChatPanel)
        assert [ln.text for ln in chat.lines] == [
            "Context · 2 seeds · 3 candidates",
            "Ready.",
        ]
        saved = files.load_chat("taxonomy")
        assert saved[0].metadata == {
            "hunches": "context",
            "summary": "Context · 2 seeds · 3 candidates",
        }
    m = meta()
    assert m["seeds"] == ["x", "y"] and m["n_candidates"] == 3
    assert m["items_won"] == {"x": 2, "y": 1}
    assert m["context_digest"] == tx.context_digest(
        ["x", "y"], files.read_text("candidates.jsonl") or ""
    )
    assert m["sent_at"]


async def test_unchanged_digest_sends_nothing(tmp_path, monkeypatch, calls):
    setup(tmp_path, monkeypatch)
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await start(pilot.app, pilot)
    assert len(calls.prompts) == 1
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await start(pilot.app, pilot)
    assert len(calls.prompts) == 1  # still one


async def test_changed_seeds_send_one_update_turn(tmp_path, monkeypatch, calls):
    setup(tmp_path, monkeypatch)
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await start(pilot.app, pilot)
    files.write_text("seeds.csv", "seed\nx\nz\n")  # y removed, z added
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        assert len(calls.prompts) == 2
        update = calls.prompts[1]
        assert update.startswith(
            "# What changed\nseeds: 1 added, 1 removed\n  + z\n  - y"
        )
        assert [ln.text for ln in screen.query_one(ChatPanel).lines][-2:] == [
            "Seeds changed · 3 candidates (+0)",
            "Ready.",
        ]
    assert meta()["seeds"] == ["x", "z"]
    kinds = [(m.metadata or {}).get("hunches") for m in files.load_chat("taxonomy")]
    assert kinds.count("context") == 1 and kinds.count("update") == 1


async def test_changed_candidates_send_an_update_turn(tmp_path, monkeypatch, calls):
    setup(tmp_path, monkeypatch)
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await start(pilot.app, pilot)
    rows = files.read_jsonl("candidates.jsonl")
    rows.append({"id": "4", "text": "t", "max_similarity": 0.9, "best_seed": "y"})
    files.write_jsonl("candidates.jsonl", rows)
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await start(pilot.app, pilot)
    assert "candidates: 3 → 4" in calls.prompts[1]
    assert meta()["n_candidates"] == 4


async def test_empty_seeds_or_missing_candidates_skip_the_context_turn(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch, seeds="seed\n")
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await start(pilot.app, pilot)
    (tmp_path / ".hunches" / "candidates.jsonl").unlink()
    files.write_text("seeds.csv", "seed\nx\n")
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        pilot.app.goto_stage(3)  # ty: ignore[unresolved-attribute]  # the app itself would resume at Search
        await start(pilot.app, pilot)
    assert calls.prompts == [] and meta() is None


async def test_a_failed_context_turn_leaves_no_meta_and_is_retried(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    calls.fail = True
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await start(pilot.app, pilot)
    assert len(calls.prompts) == 1 and meta() is None
    calls.fail = False
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await start(pilot.app, pilot)
    assert len(calls.prompts) == 2 and meta() is not None


async def test_instructions_carry_seeds_taxonomy_prompt_and_the_mode_sentence(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        text = calls.instructions[-1] or ""
        assert "exactly one label is returned" in text  # INSTRUCTIONS kept
        assert "1. x\n2. y" in text
        assert "mode: single" in text and "layoff: lost a job" in text
        assert "Classify the item." in text
        assert "The user chose mode single; do not ask about it again." in text
        assert "Find layoff posts" not in text  # brief.md moved to the context turn
        assert "I lost my job" not in text  # and so did the random samples
        assert not hasattr(tx, "build_instructions")
        box = screen.query_one("#chat-input", Input)
        box.focus()
        box.value = "hello"
        await pilot.press("enter")
        await pilot.pause(0.3)
    assert calls.instructions[-1] == text


async def test_instructions_without_files_say_none_yet(tmp_path, monkeypatch, calls):
    setup(tmp_path, monkeypatch)
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        await start(pilot.app, pilot)
    text = calls.instructions[-1] or ""
    assert "chose mode" not in text
    assert "# Current taxonomy\nNone yet." in text
    assert "# Current prompt\nNone yet." in text


# ---- labels panel -------------------------------------------------------------------


async def test_read_view_lists_labels_and_the_built_in_row(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with_files()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        title, subtitle = panel_title(screen.query_one("#labels-panel"))
        assert title == "Labels" and subtitle == "single · 2 labels"
        rows = [str(r.render()) for r in screen.query(".label-row-view")]
        assert len(rows) == 3
        assert "■ layoff" in rows[0] and "lost a job" in rows[0]
        assert "■ off_topic" in rows[2] and "built in" in rows[2]
        select = screen.query_one("#mode", Select)
        assert select.value == "single"
        assert not screen.query(".label-name")  # no inputs in the read view
        assert screen.query_one("#edit-labels", Button).label.plain.startswith(
            "Edit labels"
        )


async def test_mode_select_is_blank_without_a_taxonomy(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        assert screen.query_one("#mode", Select).is_blank()
        assert screen.query_one("#approve", Button).disabled  # nothing to approve yet
        assert panel_title(screen.query_one("#labels-panel"))[1] == ""


async def test_edit_description_save_records_without_a_model_call(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        before = len(calls.prompts)
        await edit_labels(pilot, screen)
        assert names(screen) == ["layoff", "fear"]
        assert "EDITING" in panel_title(screen.query_one("#labels-panel"))[1]
        save = screen.query_one("#save-labels", Button)
        assert save.disabled  # unchanged
        screen.query(".label-desc").last(Input).value = "worried they will"
        await pilot.pause()
        assert "UNSAVED" in panel_title(screen.query_one("#labels-panel"))[1]
        assert not save.disabled
        # nothing is written per keystroke
        assert "worried they will" not in (files.read_text("taxonomy.yaml") or "")
        await pilot.press("ctrl+s")
        await pilot.pause()
        taxonomy = files.read_taxonomy()
        assert taxonomy.labels[1].description == "worried they will"
        assert not screen.query(".label-name")  # back to the read view
        assert len(calls.prompts) == before  # no model call
        [edit] = edits()
        assert edit.metadata["summary"] == "Labels: fear description"
        text = str(edit.parts[0].content)
        assert (
            "~ fear\n    was: worried about a layoff\n    now: worried they will"
            in text
        )
        assert (
            "# Current taxonomy\nmode: single\nlabels:\n  - layoff: lost a job\n"
            in text
        )
        assert "  - fear: worried they will" in text
        assert "No reply needed." in text
        chat_lines = [ln.text for ln in screen.query_one(ChatPanel).lines]
        assert "Labels: fear description" in chat_lines


async def test_escape_discards_and_records_nothing(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with_files()
    original = files.read_text("taxonomy.yaml")
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await edit_labels(pilot, screen)
        screen.query(".label-name").first(Input).value = "renamed"
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not screen.query(".label-name")
        assert files.read_text("taxonomy.yaml") == original
        assert edits() == []
        await edit_labels(pilot, screen)  # a new draft starts from the file
        assert names(screen) == ["layoff", "fear"]


async def test_add_and_delete_labels(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with_files()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await edit_labels(pilot, screen)
        await pilot.click("#add-label")
        await pilot.pause()
        assert names(screen) == ["layoff", "fear", ""]
        assert "name" in str(screen.query_one("#labels-error").render())  # blank name
        assert screen.query_one("#save-labels", Button).disabled
        screen.query(".label-name").last(Input).value = "freeze"
        screen.query(".label-delete").first(Button).press()
        await pilot.pause()
        assert names(screen) == ["fear", "freeze"]
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert [lab.name for lab in files.read_taxonomy().labels] == ["fear", "freeze"]
        [edit] = edits()
        assert edit.metadata["summary"] == "Labels: +freeze, -layoff"
        assert "labels: 1 added, 1 deleted" in str(edit.parts[0].content)


async def test_invalid_draft_disables_save_and_marks_the_row(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with_files()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await edit_labels(pilot, screen)
        inputs = list(screen.query(".label-name").results(Input))
        inputs[1].value = "off_topic"
        await pilot.pause()
        assert screen.query_one("#save-labels", Button).disabled
        assert "built in" in str(screen.query_one("#labels-error").render())
        rows = list(screen.query(".label-edit-row"))
        assert not rows[0].has_class("-bad") and rows[1].has_class("-bad")
        await pilot.press("ctrl+s")  # the binding is a no-op as well
        await pilot.pause()
        assert files.read_taxonomy().labels[1].name == "fear"
        assert edits() == []


async def test_empty_labels_draft_cannot_be_saved(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with_files()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await edit_labels(pilot, screen)
        for _ in range(2):
            screen.query(".label-delete").first(Button).press()
            await pilot.pause()
        assert screen.query_one("#save-labels", Button).disabled
        assert "at least one label is required" in str(
            screen.query_one("#labels-error").render()
        )


async def test_changing_the_mode_enters_edit_mode_and_records_a_mode_edit(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        select = screen.query_one("#mode", Select)
        await pilot.press("m")
        await pilot.pause()
        assert select.expanded
        await pilot.press("escape")
        await pilot.pause()
        assert not screen.query(".label-name")  # opening it alone is not an edit
        select.value = "multi"
        await pilot.pause()
        assert names(screen) == ["layoff", "fear"]  # edit mode, new mode in the draft
        assert "UNSAVED" in panel_title(screen.query_one("#labels-panel"))[1]
        assert files.read_taxonomy().mode == "single"  # not written yet
        before = len(calls.prompts)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert files.read_taxonomy().mode == "multi"
        assert len(calls.prompts) == before
        [edit] = edits()
        assert edit.metadata["summary"] == "Mode: one label → several labels"
        text = str(edit.parts[0].content)
        assert "mode: single → multi" in text
        assert (
            "# Current taxonomy\nmode: multi\nlabels:\n  - layoff: lost a job" in text
        )
        assert select.value == "multi"


async def test_first_labels_can_be_added_by_hand(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        screen.query_one("#mode", Select).value = "multi"
        await pilot.pause()
        assert names(screen) == []
        assert screen.query_one("#save-labels", Button).disabled
        await pilot.click("#add-label")
        await pilot.pause()
        screen.query(".label-name").first(Input).value = "layoff"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert files.read_taxonomy().mode == "multi"
        assert [lab.name for lab in files.read_taxonomy().labels] == ["layoff"]


# ---- prompt panel -------------------------------------------------------------------


async def test_prompt_read_view_edit_save_and_discard(tmp_path, monkeypatch, calls):
    setup(tmp_path, monkeypatch)
    with_files(prompt="# Prompt\nClassify the item.\nUse the labels.\n")
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        assert panel_title(screen.query_one("#prompt-panel")) == (
            "Prompt",
            "classifier prompt",
        )
        assert "Classify the item." in screen.query_one("#prompt-view").source
        before = len(calls.prompts)
        screen.query_one("#edit-prompt", Button).focus()
        await pilot.press("e")
        await pilot.pause()
        area = screen.query_one("#prompt-text", TextArea)
        assert area.language == "markdown" and area.show_line_numbers
        assert area.theme == "hunches"
        assert screen.query_one("#save-prompt", Button).disabled
        area.text = "# Prompt\nClassify the item well.\nUse the labels.\nExtra.\n"
        await pilot.pause()
        assert "UNSAVED" in panel_title(screen.query_one("#prompt-panel"))[1]
        # nothing is written per keystroke
        assert "well" not in (files.read_text("prompt.md") or "")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "Extra." in (files.read_text("prompt.md") or "")
        assert len(calls.prompts) == before
        [edit] = edits()
        assert edit.metadata["summary"] == "Prompt: 2 lines changed"
        text = str(edit.parts[0].content)
        assert "-Classify the item.\n+Classify the item well." in text
        assert (
            "# Current prompt\n# Prompt\nClassify the item well.\nUse the labels.\nExtra."
            in text
        )

        # discard
        screen.query_one("#edit-prompt", Button).focus()
        await pilot.press("e")
        await pilot.pause()
        screen.query_one("#prompt-text", TextArea).text = "scrap"
        await pilot.press("escape")
        await pilot.pause()
        assert "scrap" not in (files.read_text("prompt.md") or "")
        assert len(edits()) == 1
        assert not screen.query("#prompt-text")


async def test_only_one_panel_is_editable_at_a_time(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with_files()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        approve = screen.query_one("#approve", Button)
        assert not approve.disabled
        await edit_labels(pilot, screen)
        assert screen.query_one("#prompt-panel").disabled and approve.disabled
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(app_screen(pilot), TaxonomyScreen)  # no confirm opened
        await pilot.press("escape")
        await pilot.pause()
        assert not screen.query_one("#prompt-panel").disabled and not approve.disabled
        screen.query_one("#edit-prompt", Button).focus()
        await pilot.press("e")
        await pilot.pause()
        assert screen.query_one("#labels-panel").disabled and approve.disabled
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(app_screen(pilot), TaxonomyScreen)


def app_screen(pilot):
    return pilot.app.screen


# ---- agent writes -------------------------------------------------------------------


async def send(pilot, screen, text):
    box = screen.query_one("#chat-input", Input)
    box.focus()
    box.value = text
    await pilot.press("enter")
    await pilot.pause(0.5)
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


async def test_agent_writes_files_and_marks_the_panels(tmp_path, monkeypatch, calls):
    setup(tmp_path, monkeypatch)
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        calls.tool = ("write_taxonomy", GOOD)
        await send(pilot, screen, "write it")
        assert files.read_taxonomy().mode == "multi"
        assert calls.returns == ["Taxonomy written."]
        assert names_in_view(screen) == ["layoff"]
        assert (
            "UPDATED BY ASSISTANT" in panel_title(screen.query_one("#labels-panel"))[1]
        )
        assert screen.query_one("#mode", Select).value == "multi"
        assert edits() == []  # the agent's own writes are not user edits
        calls.tool = ("write_prompt", {"prompt": "Classify the item."})
        await send(pilot, screen, "write it")
        assert files.read_text("prompt.md") == "Classify the item."
        assert (
            "UPDATED BY ASSISTANT" in panel_title(screen.query_one("#prompt-panel"))[1]
        )
        # the next agent turn clears the tag
        calls.tool = None
        await send(pilot, screen, "thanks")
        assert "UPDATED" not in panel_title(screen.query_one("#labels-panel"))[1]
        assert "UPDATED" not in panel_title(screen.query_one("#prompt-panel"))[1]


def names_in_view(screen) -> list[str]:
    return [str(r.render()).split()[1] for r in screen.query(".label-row-view")][
        :-1
    ]  # without the built-in row


async def test_agent_writes_are_refused_while_the_panel_is_being_edited(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    original = files.read_text("taxonomy.yaml")
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await edit_labels(pilot, screen)
        calls.tool = ("write_taxonomy", GOOD)
        await send(pilot, screen, "write it")
        assert calls.returns == [
            "Not written: the user is editing the taxonomy. Ask them to save or discard first."
        ]
        assert files.read_text("taxonomy.yaml") == original
        await pilot.press("escape")
        await pilot.pause()
        screen.query_one("#edit-prompt", Button).focus()
        await pilot.press("e")
        await pilot.pause()
        calls.tool = ("write_prompt", {"prompt": "new"})
        await send(pilot, screen, "write it")
        assert calls.returns[-1] == (
            "Not written: the user is editing the prompt. Ask them to save or discard first."
        )
        assert files.read_text("prompt.md") == "# Prompt\nClassify the item.\n"


async def test_invalid_agent_taxonomy_is_rejected_without_writing(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    original = files.read_text("taxonomy.yaml")
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        calls.tool = ("write_taxonomy", BAD)
        await send(pilot, screen, "write it")
        assert calls.returns[0].startswith("Rejected, nothing written:")
        assert files.read_text("taxonomy.yaml") == original
        calls.tool = ("write_taxonomy", {"mode": "single", "labels": []})
        await send(pilot, screen, "write it")
        assert calls.returns[1] == (
            "Rejected, nothing written: at least one label is required"
        )


async def test_save_and_agent_write_both_go_through_commit_taxonomy(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    seen = []
    original = TaxonomyScreen.commit_taxonomy

    def spy(self, new, by_user=True):
        seen.append((new.mode, by_user))
        original(self, new, by_user)

    monkeypatch.setattr(TaxonomyScreen, "commit_taxonomy", spy)
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await edit_labels(pilot, screen)
        screen.query(".label-desc").first(Input).value = "x"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        calls.tool = ("write_taxonomy", GOOD)
        await send(pilot, screen, "write it")
    assert seen == [("single", True), ("multi", False)]


# ---- approve ------------------------------------------------------------------------


async def test_approve_is_disabled_without_a_prompt_and_confirm_text_is_exact(
    tmp_path, monkeypatch
):
    setup(tmp_path, monkeypatch)
    with_files(prompt=None)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        approve = screen.query_one("#approve", Button)
        assert approve.disabled and approve.label.plain.startswith(
            "Approve taxonomy and prompt"
        )
        await pilot.press("f2")  # silent no-op
        await pilot.pause()
        assert app.screen is screen and not files.read_state().taxonomy_approved
        assert not screen.query("#status") and "Cannot approve" not in " ".join(
            str(w.render()) for w in screen.query("Static")
        )
        files.write_text("prompt.md", "Classify.")
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await start(app, pilot)
        assert not screen.query_one("#approve", Button).disabled
        await pilot.click("#approve")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        assert app.screen.question == (
            "Approve taxonomy (single, 2 labels) and prompt, and start labelling?"
        )
        await pilot.click("#yes")
        await pilot.pause()
        assert files.read_state().taxonomy_approved
        assert files.read_config().target_metric == "accuracy"
        assert app.stage == 4


async def test_approve_multi_sets_macro_f1(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with_files(GOOD)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await start(app, pilot)
        await pilot.press("f2")
        await pilot.pause()
        assert app.screen.question == (  # ty: ignore[unresolved-attribute]
            "Approve taxonomy (multi, 1 labels) and prompt, and start labelling?"
        )
        await pilot.click("#yes")
        await pilot.pause()
        assert files.read_config().target_metric == "macro_f1"


async def test_resume_restores_the_chat(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await send(pilot, screen, "multi please")
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        assert any(
            "multi please" in ln.text for ln in screen.query_one(ChatPanel).lines
        )


# ---- layout -------------------------------------------------------------------------


@pytest.mark.parametrize("size", [(80, 24), (100, 30), (120, 36)])
async def test_everything_fits_in_each_size(tmp_path, monkeypatch, size):
    setup(tmp_path, monkeypatch)
    with_files(prompt="# Prompt\nClassify.\n- layoff: x\n")
    async with HunchesApp().run_test(size=size) as pilot:
        screen = await start(pilot.app, pilot)
        width, height = size

        def inside(widget):
            r = widget.region
            return (
                r.width > 0 and r.height > 0 and r.right <= width and r.bottom <= height
            )

        for sel in ("#mode", "#edit-labels", "#edit-prompt", "#approve"):
            assert inside(screen.query_one(sel)), sel
        await edit_labels(pilot, screen)
        screen.query(".label-desc").first(Input).value = "changed"
        await pilot.pause()
        for sel in ("#mode", "#save-labels", "#discard-labels", "#approve"):
            assert inside(screen.query_one(sel)), sel
        assert inside(screen.query(".label-name").first())
        await pilot.press("escape")
        await pilot.pause()
        screen.query_one("#edit-prompt", Button).focus()
        await pilot.press("e")
        await pilot.pause()
        for sel in ("#prompt-text", "#save-prompt", "#discard-prompt"):
            assert inside(screen.query_one(sel)), sel


def test_yaml_format_is_unchanged(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with_files()
    assert yaml.safe_load(files.read_text("taxonomy.yaml") or "") == TWO
