# 05 — `classifier.is_cached`, `redo_plan`

Spec: Redo plan, Cache, Tests → Redo plan. `classifier.is_cached(...)` builds the cache key without calling anything. `redo_plan()` lists every stale/incomplete stage with cached vs live counts and dollars (`?` if the price is unknown, never 0; `None` counts for non-model stages; `not_started` absent). Prove with `FunctionModel` call counting that the plan equals what a real run does and a second run makes zero calls.
