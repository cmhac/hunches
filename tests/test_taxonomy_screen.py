import json

import yaml
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from textual.widgets import Input, RichLog, TextArea

from hunches import files
from hunches.app import HunchesApp
from hunches.screens.taxonomy import TaxonomyScreen


def hexcolor(style) -> str:
    assert style.color is not None
    return style.color.get_truecolor().hex.upper()


seen_instructions: list[str | None] = []


def make_stream(taxonomy_args: dict):
    async def stream(messages, info: AgentInfo):
        seen_instructions.append(info.instructions)
        returns = [p for p in messages[-1].parts if p.part_kind == "tool-return"]
        if not returns:
            yield {
                0: DeltaToolCall(
                    name="write_taxonomy", json_args=json.dumps(taxonomy_args)
                )
            }
        elif "Taxonomy written" in str(returns[0].content):
            yield {
                0: DeltaToolCall(
                    name="write_prompt", json_args='{"prompt": "Classify the item."}'
                )
            }
        else:
            yield "Done."

    return stream


GOOD = {
    "mode": "multi",
    "labels": [{"name": "layoff", "description": "lost a job"}],
}
BAD = {"mode": "single", "labels": [{"name": "off_topic", "description": ""}]}


def setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir="c",
            embedding_model="m",
        )
    )
    files.write_text("seeds.csv", "seed\nx\n")
    files.write_text("brief.md", "Find layoff posts\n")
    files.write_jsonl(
        "candidates.jsonl",
        [{"id": "1", "text": "I lost my job", "max_similarity": 0.8, "best_seed": "x"}],
    )
    state = files.State(seeds_approved=True)
    files.write_state(state)


async def chat(app, pilot, stream):
    screen = app.screen
    assert isinstance(screen, TaxonomyScreen)
    screen.agent.model = FunctionModel(stream_function=stream)
    box = screen.query_one("#chat-input", Input)
    box.focus()
    box.value = "multi please"
    await pilot.press("enter")
    await pilot.pause(0.5)
    await app.workers.wait_for_complete()
    await pilot.pause()
    return screen


async def test_agent_writes_files_and_approve_sets_flag_and_metric(
    tmp_path, monkeypatch
):
    setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = await chat(app, pilot, make_stream(GOOD))
        taxonomy = files.read_taxonomy()
        assert taxonomy.mode == "multi"
        assert [lab.name for lab in taxonomy.labels] == ["layoff"]
        assert files.read_text("prompt.md") == "Classify the item."
        assert "layoff" in screen.query_one("#taxonomy", TextArea).text
        # instructions carry the required prompt guidance, the brief and real samples
        text = seen_instructions[0] or ""
        assert "exactly one label is returned" in text
        assert "describe the off_topic label" in text
        assert "Find layoff posts" in text
        assert "I lost my job" in text
        assert files.read_config().target_metric == "accuracy"  # default so far

        await pilot.press("f2")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert files.read_state().taxonomy_approved
        assert files.read_config().target_metric == "macro_f1"  # multi default
        assert app.stage == 4


async def test_invalid_taxonomy_rejected_without_writing(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    files.write_text("taxonomy.yaml", "mode: single\nlabels:\n- name: a\n")
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = await chat(app, pilot, make_stream(BAD))
        assert (
            yaml.safe_load(files.read_text("taxonomy.yaml") or "")["mode"] == "single"
        )
        assert files.read_taxonomy().labels[0].name == "a"  # untouched
        assert files.read_text("prompt.md") is None

        # hand edits: valid ones save, invalid ones leave the file alone
        area = screen.query_one("#taxonomy", TextArea)
        area.text = "mode: [oops"
        await pilot.pause()
        assert files.read_taxonomy().labels[0].name == "a"
        area.text = "mode: multi\nlabels:\n- name: b\n"
        await pilot.pause()
        assert files.read_taxonomy().labels[0].name == "b"
        screen.query_one("#prompt", TextArea).text = "my prompt"
        await pilot.pause()
        assert files.read_text("prompt.md") == "my prompt"

        await pilot.press("f2")  # both files valid now
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert files.read_config().target_metric == "macro_f1"


async def test_approve_blocked_without_files_and_resume_restores_chat(
    tmp_path, monkeypatch
):
    setup(tmp_path, monkeypatch)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert not files.read_state().taxonomy_approved
        await chat(app, pilot, make_stream(GOOD))
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TaxonomyScreen)
        log = app.screen.query_one("#log", RichLog)
        assert any("multi please" in str(line.text) for line in log.lines)
        assert "layoff" in app.screen.query_one("#taxonomy", TextArea).text


async def test_redesigned_panels_status_and_highlighting(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    files.write_text(
        "taxonomy.yaml", "mode: single\n# note\nlabels:\n  - name: layoff\n"
    )
    files.write_text("prompt.md", "# Prompt\nClassify.\n")
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TaxonomyScreen)
        assert screen.query_one("ChatPanel").border_title == "chat · taxonomy"
        assert (
            screen.query_one("#taxonomy-panel").border_title
            == "taxonomy.yaml (editable)"
        )
        assert screen.query_one("#prompt-panel").border_title == "prompt.md (editable)"
        yaml_box, prompt_box = (
            screen.query_one("#taxonomy", TextArea),
            screen.query_one("#prompt", TextArea),
        )
        assert yaml_box.theme == prompt_box.theme == "hunches"
        assert prompt_box.language == "markdown"
        # keys sand (secondary), comments faint, headings primary bold
        styles = yaml_box._theme.syntax_styles
        assert hexcolor(styles["yaml.field"]) == "#D2BE94"
        assert hexcolor(styles["comment"]) == "#5C6676"
        heading = prompt_box._theme.syntax_styles["heading"]
        assert hexcolor(heading) == "#6EA8FE" and heading.bold
        assert yaml_box._highlights  # tree-sitter really highlighted something

        screen.query_one("#taxonomy", TextArea).text = "mode: [oops"
        await pilot.pause()
        status = screen.query_one("#status")
        assert str(status.render()).startswith("taxonomy.yaml not saved: ")
        assert status.has_class("warn")
