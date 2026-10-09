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

from hunches import files, history
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
        assert title == "Labels" and subtitle == "single · 2 labels · version 1"
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
        (entry,) = [e for e in history.entries() if e["kind"] == "approval"]
        assert (entry["stage"], entry["flag"], entry["summary"]) == (
            3,
            "taxonomy_approved",
            "Approved: Taxonomy and prompt (single, 2 labels)",
        )
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


# ---- taxonomy versions (003/17) -----------------------------------------------------

CONFIRM = (
    "Gold labels were made with the current labels. Saving starts a new taxonomy "
    "version: dev and test labelling restart on the same items (your current labels, "
    "prompt and results are kept as version {n} and can be restored). Continue?"
)


def gold_in_use():
    """Hand-built gold: 2 dev rows and 1 test row, all labelled, plus a threshold file."""
    files.write_gold(
        [
            files.GoldRow(id="1", text="I lost my job", labels=["layoff"], split="dev"),
            files.GoldRow(id="2", text="worried", labels=["fear"], split="dev"),
            files.GoldRow(id="3", text="laid off", labels=["layoff"], split="test"),
        ]
    )
    files.write_text("threshold.json", '{"threshold": 0.7}')
    # taxonomy_approved stays false so the app opens on this screen (startup picks the first
    # incomplete stage); dev_done stands for the later flags the new version must clear
    files.write_state(files.State(seeds_approved=True, dev_done=True))


async def rename_fear(pilot, screen):
    await edit_labels(pilot, screen)
    screen.query(".label-name").last(Input).value = "worry"
    await pilot.pause()
    await pilot.press("ctrl+s")
    await pilot.pause()


async def test_description_edit_with_gold_in_use_saves_without_a_confirm(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    gold_in_use()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await edit_labels(pilot, screen)
        screen.query(".label-desc").last(Input).value = "scared"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert pilot.app.screen is screen
        assert files.read_taxonomy().labels[1].description == "scared"
        assert files.list_versions() == []
        assert files.taxonomy_in_use()


async def test_rename_with_gold_in_use_confirms_then_archives_and_clears(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    gold_in_use()
    gold_before = files.read_text("gold.jsonl")
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        app = pilot.app
        screen = await start(app, pilot)
        before = len(calls.prompts)
        assert screen.query_one("#versions", Button).disabled
        await rename_fear(pilot, screen)
        assert isinstance(app.screen, ConfirmScreen)
        assert app.screen.question == CONFIRM.format(n=1)
        # Cancel: nothing changes and the draft stays open
        await pilot.click("#no")
        await pilot.pause()
        assert app.screen is screen and screen.edit == "labels"
        assert names(screen) == ["layoff", "worry"]
        assert files.read_text("gold.jsonl") == gold_before
        assert files.list_versions() == []
        assert files.read_taxonomy().labels[1].name == "fear"
        # Confirm
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert app.screen is screen and screen.edit is None
        assert [lb.name for lb in files.read_taxonomy().labels] == ["layoff", "worry"]
        assert [r.labels for r in files.read_gold()] == [[], [], []]
        assert [r.id for r in files.read_gold()] == ["1", "2", "3"]
        assert not files.taxonomy_in_use()
        assert files.read_text("threshold.json") is None
        assert not files.read_state().dev_done
        assert files.first_incomplete_stage() == 3
        [v] = files.list_versions()
        assert (v["version"], v["dev_labelled"], v["test_labelled"]) == (1, 2, 1)
        archived = (files.root() / "versions" / "1" / "gold.jsonl").read_text()
        assert archived == gold_before
        assert not screen.query_one("#versions", Button).disabled
        assert "Version 1 archived. Approve to relabel the dev set." in str(
            screen.query_one("#note").render()
        )
        assert "version 2" in panel_title(screen.query_one("#labels-panel"))[1]
        [edit] = edits()
        assert edit.metadata["summary"] == "Taxonomy version 2 started"
        text = str(edit.parts[0].content)
        assert (
            "Taxonomy version 2 started: label set/mode changed; gold labels cleared "
            "on the same items; version 1 archived" in text
        )
        assert "  - worry" in text  # the current taxonomy
        assert len(calls.prompts) == before  # no model call


async def test_label_change_without_labelled_gold_saves_normally(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    files.write_gold([files.GoldRow(id="1", text="t", labels=[], split="dev")])
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await rename_fear(pilot, screen)
        assert pilot.app.screen is screen
        assert files.read_taxonomy().labels[1].name == "worry"
        assert files.list_versions() == []
        assert not screen.query_one("#note").display


async def test_versions_modal_lists_and_restores(tmp_path, monkeypatch, calls):
    setup(tmp_path, monkeypatch)
    with_files()
    gold_in_use()
    original = {
        n: (files.root() / n).read_bytes()
        for n in ("taxonomy.yaml", "gold.jsonl", "threshold.json", "prompt.md")
    }
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        app = pilot.app
        screen = await start(app, pilot)
        await rename_fear(pilot, screen)
        await pilot.click("#yes")
        await pilot.pause()
        before = len(calls.prompts)
        await pilot.click("#versions")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, tx.VersionsScreen)
        listing = " ".join(str(w.render()) for w in modal.query("Static"))
        assert "single" in listing and "layoff, fear" in listing
        assert "dev 2" in listing and "test 1" in listing
        await pilot.click("#restore-1")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        assert "version 1" in app.screen.question
        await pilot.click("#yes")
        await pilot.pause()
        assert app.screen is screen
        for name, data in original.items():
            assert (files.root() / name).read_bytes() == data
        assert [v["version"] for v in files.list_versions()] == [1, 2]
        assert [lb.name for lb in screen.taxonomy.labels] == ["layoff", "fear"]
        assert names_in_view(screen) == ["layoff", "fear"]
        assert "version 3" in panel_title(screen.query_one("#labels-panel"))[1]
        summaries = [e.metadata["summary"] for e in edits()]
        assert summaries[-1] == "Restored taxonomy version 1"
        assert (
            "Restored taxonomy version 1; the previous state is archived as version 2"
            in str(edits()[-1].parts[0].content)
        )
        assert len(calls.prompts) == before
        # the version being left is kept
        assert (files.root() / "versions" / "2" / "taxonomy.yaml").exists()


async def test_versions_modal_close_and_restore_blocked_while_editing(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    gold_in_use()
    files.archive_version()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        app = pilot.app
        screen = await start(app, pilot)
        assert not screen.query_one("#versions", Button).disabled
        await pilot.click("#versions", offset=(2, 0))
        await pilot.pause()
        assert isinstance(app.screen, tx.VersionsScreen)
        await pilot.click("#close")
        await pilot.pause()
        assert app.screen is screen
        await edit_labels(pilot, screen)
        assert not screen.query_one("#labels-view-buttons").display
        screen.action_versions()
        await pilot.pause()
        assert app.screen is screen  # no modal while a draft is open


async def agent_write(pilot, screen, answer: str | None):
    box = screen.query_one("#chat-input", Input)
    box.focus()
    box.value = "write it"
    await pilot.press("enter")
    await pilot.pause(0.5)
    if answer:
        assert isinstance(pilot.app.screen, ConfirmScreen)
        await pilot.click(f"#{answer}")
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


async def test_agent_write_that_changes_labels_awaits_the_confirm(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    gold_in_use()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        calls.tool = ("write_taxonomy", GOOD)  # mode single -> multi, one label
        await agent_write(pilot, screen, "no")
        assert calls.returns[-1] == (
            "Not written: the user declined starting a new taxonomy version."
        )
        assert files.read_taxonomy().mode == "single"
        assert files.list_versions() == [] and files.taxonomy_in_use()
        await agent_write(pilot, screen, "yes")
        assert calls.returns[-1] == (
            "Written as version 2; gold labels were cleared and will need relabelling."
        )
        assert files.read_taxonomy().mode == "multi"
        assert not files.taxonomy_in_use()
        assert [v["version"] for v in files.list_versions()] == [1]
        assert edits() == []  # an agent write is not a user edit


async def test_agent_write_without_label_change_needs_no_confirm(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    gold_in_use()
    same = {
        "mode": "single",
        "labels": [
            {"name": "fear", "description": "new words"},
            {"name": "layoff", "description": "lost a job"},
        ],
    }
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        calls.tool = ("write_taxonomy", same)
        await agent_write(pilot, screen, None)
        assert calls.returns[-1] == "Taxonomy written."
        assert files.taxonomy_in_use() and files.list_versions() == []


async def test_agent_edit_rule_still_wins_over_the_confirm(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    gold_in_use()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await edit_labels(pilot, screen)
        calls.tool = ("write_taxonomy", GOOD)
        await agent_write(pilot, screen, None)
        assert calls.returns[-1].startswith("Not written: the user is editing")
        assert files.list_versions() == []


def logged(artifact):
    from hunches import history

    return [(e["source"], e["summary"]) for e in history.entries(artifact)]


async def test_user_edits_and_agent_writes_are_saved_through_history(
    tmp_path, monkeypatch, calls
):
    setup(tmp_path, monkeypatch)
    with_files()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        screen = await start(pilot.app, pilot)
        await edit_labels(pilot, screen)
        screen.query(".label-desc").last(Input).value = "worried they will"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert ("user", "Labels: fear description") in logged("taxonomy")
        calls.tool = ("write_taxonomy", GOOD)
        await send(pilot, screen, "write it")
        assert logged("taxonomy")[-1][0] == "assistant"
        calls.tool = ("write_prompt", {"prompt": "Classify the item."})
        await send(pilot, screen, "write it")
        assert logged("prompt")[-1][0] == "assistant"
        screen.query_one("#edit-prompt", Button).focus()
        await pilot.press("e")
        await pilot.pause()
        screen.query_one("#prompt-text", TextArea).text = "Classify the item.\nMore."
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert logged("prompt")[-1] == ("user", "Prompt: 1 line changed")


async def test_new_version_and_restore_are_logged(tmp_path, monkeypatch, calls):
    from hunches import history

    setup(tmp_path, monkeypatch)
    with_files()
    gold_in_use()
    async with HunchesApp().run_test(size=(120, 40)) as pilot:
        app = pilot.app
        screen = await start(app, pilot)
        await rename_fear(pilot, screen)
        await pilot.click("#yes")
        await pilot.pause()
        edit = history.entries("taxonomy")[-1]
        assert (edit["source"], edit["snapshot"]) == ("user", 1)
        assert history.entries()[-1]["kind"] == "version"
        await pilot.click("#versions")
        await pilot.pause()
        await pilot.click("#restore-1")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert logged("taxonomy")[-1] == ("restore", "Restored taxonomy version 1")
        assert (
            history.entries("taxonomy")[-1]["after"]
            == history.entries("taxonomy")[0]["after"]
        )
