# 03 — Chat panel as widgets; context, edit and tool lines; edit recording

Spec: D4, D5, D6, conflict 6. Handoff: `design/BACKEND_CHANGES.md` §2 and the mechanism part of §5; `design/README.md` §3.3 "Chat panel"; mock `components-rail/chat/ChatPanel.jsx`; states `brief/seeds`, `brief/tool-open`, `brief/edits-sent`, `taxonomy/tool-open`, `taxonomy/context-open`. `[visual]` + `[backend]`.

## Goal
Replace the `RichLog` chat with a widget-based one that can show expandable tool, context and edit lines, and add the shared machinery later tasks use to keep the agent in sync with the user. No stage's behaviour changes yet except how its chat looks.

## Do
- **Rebuild `ChatPanel` (`app.py`; moving it to `src/hunches/chat.py` is fine, keep the import working).** Constructor stays `ChatPanel(stage, agent)`; add `empty: str = ""` for the centred empty-state text. Replace the `RichLog` with a `VerticalScroll` that mounts one widget per turn: `Static` for text, a small custom widget (or `Collapsible`) for tool, context and edit lines. Keep the live streaming `Static` at the bottom. Auto-scroll after each mount unless the user has scrolled up. History is restored through the same mount path as live turns, so a resumed chat looks identical.
- **Look.** Gutters `› │ ↳` unchanged. One blank row between turns, none between consecutive tool lines, one blank row between the last message and the input. Input is one row (task 01 styles) with a send button `↑` to its right, disabled while the input is empty or a reply is streaming. The send button and Enter run the same submit.
- **Tool lines.** `↳ name  summary  ▸` collapsed. Summary is the tool's return string, clipped with an ellipsis. Pair `ToolCallPart` with `ToolReturnPart` by `tool_call_id`. Expanded: arguments (pretty-printed from the call part) and the result in a tinted block indented to the text column; long values truncated with "… N more" in the collapsed-adjacent view, full text in the expanded block. While a call is running: the name and `…`, updated when the result arrives.
- **Context and edit lines.** `◇` marker, then a `YOU EDITED` (primary reverse) or `UPDATED` (secondary reverse) badge for edit/update lines, then a one-line summary, `▸`. Expanded shows the message body (`# What changed` heading bold; long bodies capped at 12 lines with "… N more lines"). Recognised by `ModelRequest.metadata["hunches"]` (D4): `"context"`, `"update"`, `"edit"`. A request with that metadata never renders as a user message.
- **Message and history API.**
  - `ChatPanel.send_context(text: str, kind: Literal["context", "update"], summary: str)`: runs a model turn with `text` as a hidden user prompt; after the run, set `.metadata = {"hunches": kind}` on the first request of `result.new_messages()` (D4), clear `.instructions` on persisted requests (D5), `save_chat`, render the context line collapsed, stream the reply. Cost recorded as for any turn.
  - `ChatPanel.record(summary: str, body: str)`: appends a hand-built `ModelRequest(parts=[UserPromptPart(content)], metadata={"hunches": "edit"})` to `self.history`, saves, mounts the line. **No model call.** Content shape (BACKEND §5.1): `# What changed`, then the diff/summary; `# Current <artifact>` with the full new state; `# Instructions` with "No reply needed. Treat this as the current state in your next turn."
  - Put the pure message builder next to `files.save_chat` as `files.edit_message(summary, body) -> ModelRequest` so tests need no widgets.
  - `ChatPanel.Submitted(text)` message posted on user submit. `BriefScreen` handles it (it replaces the current `Input.Submitted` bubbling that writes `brief.md`, conflict 6).
  - `reply()` keeps working as now: error line on failure, `files.save_chat`, `cost.record`. Strip `instructions` before saving (D5). Disable the input and send button while streaming.
- **Empty state.** Brief passes `empty="Describe what concepts you want to search for and the assistant will help you generate seed phrases"` (task 06 wires it; the parameter lands here).
- **Per-run instructions pattern (documented, used by 06, 08, 16).** Each screen registers `@agent.instructions` returning its current state; this task adds a short comment in `ChatPanel` pointing at it and a test that a dynamic instruction is evaluated on every run.

## Tests
- Hand-build a history: user text, assistant text, a tool call + return, an `edit` request, a `context` request. Mount a `ChatPanel` and assert the line kinds in order, that tool lines are collapsed with the return string, that expanding shows the arguments, and that the context/edit requests render as lines, not user turns. Mount the same history via live turns (`FunctionModel`) and assert identical widget structure.
- `record()` makes zero model calls (count `FunctionModel` invocations), persists, and the next `reply()` sends the edit request to the model (inspect `FunctionModel`'s messages).
- A `send_context` turn is tagged and persisted; reloading renders it collapsed.
- Persisted JSON has no `instructions` text; a dynamic `@agent.instructions` function is evaluated on each run (use a counter).
- Send button: disabled when empty and while streaming; Enter and button behave the same.
- Chat tests that use `#log`/`#live` (`test_app.py`, `test_brief.py`, `test_run_screen.py`, `test_taxonomy_screen.py`) move to the new structure; `test_assistant_thinking.py` keeps passing.

## Done when
- Brief and Taxonomy chats work end to end with the new widgets and look right at 80×24, 100×30 and 120×36.
