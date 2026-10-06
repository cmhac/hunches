# 16 — Stage 5 Tuning: assistant chat, tools, context, proposal cards, layout

Spec: D4, D5, D6, D9, conflict 2. Handoff: `design/BACKEND_CHANGES.md` §9 (and §5, §10.7, §11.4–5); `design/README.md` §5 "5 Tuning (`screens/tune.py`): assistant chat"; mock `ui_kits/tui-rail/Tune.jsx`; states `tune/below`, `tune/chatting`, `tune/tool-open`, `tune/asking`, `tune/proposal`, `tune/proposal-pending`, `tune/rerun`, `tune/pass`, `tune/rejected`, `tune/proposal-failed`, `tune/metric`, `tune/chat-tab`, `tune/chat-focus`, `tune/edit-prompt-changed`. `[behaviour]` + `[backend]` + `[visual]`. File: `screens/tune.py`. Starts from task 15's result.

## Goal
Tuning gets the full chat panel. The assistant sees what the user sees, replies in prose, and acts through two tools. The one-shot `propose()` is gone.

## Do

### A. Agent and tools (BACKEND §9)
- Agent: replace `INSTRUCTIONS`/`output_type=str` with a conversational agent (replies in prose, never outputs the prompt as plain text; "Each disagreement includes the classifier's own reasoning. Use it to explain why the classifier chose its label and to decide what the prompt is missing."; call `propose_prompt` only when asked or agreed). `@agent.instructions` returns the **current** prompt, taxonomy and target metric/score (BACKEND §5; D5).
- `get_disagreements(label: str | None = None, limit: int = 10) -> str`: read-only; text, gold, predicted and reasoning, filtered by gold or predicted label. The context message carries the first `MAX_SHOWN` (20); this gives the rest.
- `propose_prompt(prompt: str, rationale: str) -> str`: stores the proposal, shows a pending card in the chat, opens `ProposalScreen(self.prompt, prompt)` and **waits** for the decision with `await self.app.push_screen_wait(...)` inside the chat worker (D6). Returns "Accepted", "Accepted with edits: <unified diff vs. the proposal>" or "Rejected". If the user dismisses with Esc without deciding, keep the card with a **Review** button that reopens the modal and return "Pending: the user has not decided yet".
- Both tools return "Not available while the dev set is running" while `self.running` or `self.stopped` (task 11; wording may be "…is not complete").

### B. Context (same mechanism as task 08)
- **First run:** when the first dev run completes and no tuning history exists, `chat.send_context(..., "context", summary)` with: dev metrics (target metric, score, n), per-label P/R/F1/gold, up to 20 disagreements (each with a `reasoning:` line), the current prompt, the taxonomy and instructions ("reply in two or three sentences: where the classifier stands against the target and the main pattern in the errors; offer to propose an edit; call propose_prompt only when asked or agreed"). The assistant replies on its own.
- **Every later run:** when a dev run completes, compare a digest of (prompt hash, classifier model, gold dev rows, metrics) with `chat/tuning.meta.json`; if it differs, send an UPDATED context line with the new metrics and disagreements and let the assistant reply briefly. Write the meta after the reply completes.
- **YOU EDITED lines (`chat.record`, no model call):** a target metric or score change (`action_next_metric`, `action_score`), a proposal accepted **with edits** (diff between proposal and accepted text, plus the new prompt), and a manual prompt edit from task 15 ("Prompt: edited by the user", was/now, `# Current prompt`; same helper as accepted-with-edits so both read alike). Rejections are covered by the tool result.
- **Superseded proposals.** If a proposal card is pending when the user saves a manual prompt edit, mark it `status: "superseded"` so the old diff cannot be applied over the new prompt.
- **After an accepted proposal or manual edit** the re-run's completion triggers the UPDATED context (above). `accepted()` is otherwise unchanged (write `prompt.md`, `rerun()`); the tool result is returned when the modal closes.

### C. Chat and the Propose button
- Yield `ChatPanel("tuning", self.agent)` with `files.save_chat("tuning", …)` history. The **Propose edit  e** button/key sends the canned user message "Propose a prompt edit based on the current disagreements." through the chat; disabled while a reply streams or a run is in progress. Remove `propose()`, the "Proposal failed" note and the "Asking the assistant…" note; a failed assistant call is an error line in the chat (`ChatPanel` already does this).
- **Proposal card** in the chat (mock `ChatPanel.jsx`, `proposal` role): "Proposed prompt change" with `+N −M` diff size; pending shows **Review** and **Reject**; afterwards "Accepted" (with note "edited" when applicable) or "Rejected. The assistant keeps the current prompt." Cards persist across resumes: store the decision in a small `chat/tuning.proposals.json` (`[{"id", "status", "plus", "minus"}]`) or as `edit`-typed requests — pick the smaller; do not widen the agent's message history format beyond D4.
- Hide the chat panel (`display = False`, not removal, so history and scroll survive) while `self.running`/`self.stopped`; it returns when the run completes. Single-letter keys do not fire while the chat input has focus (normal Textual); Tab moves focus; buttons always work.

### D. Layout (README §5)
- **≥120 columns:** `Horizontal` with `ChatPanel` first (`width: 42`, same as Brief/Taxonomy) and the results column `1fr`.
- **<120 columns:** a "Chat | Results" tab strip (chat first) — a full-width `$surface` bar with a half-row gap (one blank row if needed) before the first panel; `c` switches; the footer lists `c Chat` first so it survives truncation; the Chat tab shows `●` when the assistant has replied or a proposal is waiting and Results is showing. The tab strip is hidden together with the chat during runs. Use `TabbedContent` or two containers toggled by a `-chat` class; toggle in `on_resize`.
- Footer labels shorten to Propose / Metric / Done under 120 columns.

## Tests (`FunctionModel` only; count calls)
- Chat starts after the first run with exactly one context turn (tagged), no user typing; a second identical run sends nothing; a changed prompt hash sends one UPDATED turn.
- `get_disagreements` filters by gold and by predicted label and includes reasoning; both tools return the "Not available…" text while running.
- `propose_prompt`: Accept → "Accepted" and `prompt.md` written and re-run started; Accept with edits → "Accepted with edits: <diff>"; Reject → "Rejected" and `prompt.md` untouched; Esc → "Pending…" and the card keeps Review; Review reopens.
- Target changes and accepted-with-edits and manual edit each append exactly one `edit` request with **zero model calls**; a pending card becomes `superseded` on a manual edit.
- The instructions function reflects the current prompt after an edit.
- Layout: at 120 columns chat is 42 wide at the left; at 119 the tab strip shows, `c` switches, the Chat tab shows `●` after a reply while on Results; chat hidden during a run and back after.
- Breakers in `tests/test_tune_screen.py`: every test of `propose()` and of the one-shot agent (`output_type=str`), `Proposal failed`.

## Done when
- `tune/*` states including chat match at the three sizes; no real model is ever called.
