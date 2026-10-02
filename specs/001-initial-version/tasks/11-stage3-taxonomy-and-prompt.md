# 11 — Stage 3: taxonomy and prompt

Spec section: Stages, item 3; Classifier.

## Goal
The smart model interviews the user and writes `taxonomy.yaml` and `prompt.md`.

## Do
- `src/hunches/screens/taxonomy.py`. Chat panel plus two read-only/editable panes: taxonomy (YAML text area) and prompt (text area).
- The agent starts from `brief.md` and some candidate samples (give it ~10 random candidate texts so it sees real data). It must ask whether each item gets exactly one label or possibly several, and whether there is one user label (binary) or several; it then writes the taxonomy with `mode`.
- The agent updates the files through structured output or tools. Validate with the taxonomy model from task 03 (e.g. reject a user label named `off_topic`) and feed the error back to the agent.
- The user can hand-edit both panes; edits save to disk.
- The prompt must describe each label, the `off_topic` label, and, for `single`, that exactly one label is returned. The agent is told this; add a test that the system prompt it receives contains those instructions.
- Approve key → `taxonomy_approved`.
- Tests with `FunctionModel`: agent writes a valid taxonomy → files created and approve works; invalid taxonomy produces a validation message and no file corruption; resume restores chat.

## Done when
- Pilot tests pass.
