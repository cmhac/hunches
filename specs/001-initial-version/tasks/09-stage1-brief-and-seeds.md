# 09 — Stage 1: brief and seeds

Spec section: Stages, item 1.

## Goal
Chat with the smart model about what to find, then review and approve seed phrases.

## Do
- `src/hunches/screens/brief.py`. Left: chat panel from task 08. Right: `DataTable` of seeds, editable (add row, edit cell, delete row) and saved to `seeds.csv` on every change.
- First message: user writes the description, which is saved verbatim to `brief.md`.
- Smart-model `Agent` asks follow-up questions and proposes seeds as statements that would be true of a matching item. Use structured output or a tool so proposed seeds land in the table directly rather than being parsed from prose (verify the pydantic-ai mechanism in current docs). Proposals append; the user can delete.
- Chat history saved to `chat/brief.json` and restored on resume.
- Key to approve → sets `seeds_approved` in `state.json` and advances. Refuse when there are zero seeds.
- Cost goes through the recorder (chat agent is not cached).
- Tests: `TestModel`/`FunctionModel` returns two seeds → they appear in the table and in `seeds.csv`; edit/delete persists; approve sets the flag; resume restores chat and seeds.

## Done when
- Pilot tests pass.
