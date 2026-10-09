# 03 — `files.approve`, `State.inputs`

Spec: Approvals, Recorded inputs (storage), Behaviour changes. Add `State.inputs: dict[str, dict[str,str]]`, `files.approve(flag, stage, summary)` replacing every hand-set flag (grep all `seeds_approved = True` etc.), logging an `approval` entry via `history.approval`. Old `state.json` without `inputs` still loads. Recording the components themselves is task 04; here `approve` records whatever `files.current_inputs()` returns (stub returns `{}` until 04 if needed, but keep the seam).
