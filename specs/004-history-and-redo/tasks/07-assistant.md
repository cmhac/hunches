# 07 — Assistant context and gold tools

Spec: "What the assistant is told and can do", D9, Tests → Assistant. Context sections for status and gold coverage; the UPDATED proactive message added once per change; Tuning-assistant tools `get_gold_coverage`, `remove_gold` (blocks inside the tool via `await self.app.push_screen_wait(ConfirmScreen(...))`, as `write_taxonomy` does; writes nothing until confirmed), `draw_gold`. No tool sets a label. Embedding-model change is told to both assistants.
