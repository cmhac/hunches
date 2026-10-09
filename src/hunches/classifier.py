import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models import Model

from hunches import candidates, cost, files
from hunches.files import Taxonomy, all_labels, validate_labels


@dataclass
class Prediction:
    labels: list[str] | None  # None when `error` is set
    error: str | None = None  # validation retries exhausted or the model call failed
    cached: bool = False
    reasoning: str | None = None  # None when `error` is set


def system_prompt(prompt: str, taxonomy: Taxonomy) -> str:
    """prompt.md plus the label list and mode rule. This whole string is what the cache key hashes."""
    lines = [prompt.strip(), "", "Labels:"]
    lines += [f"- {label.name}: {label.description}" for label in taxonomy.labels]
    lines.append("- off_topic: the item matches none of the labels above")
    rule = (
        "Return exactly one label."
        if taxonomy.mode == "single"
        else "Return every label that applies."
    )
    lines.append(f"{rule} off_topic must never be combined with another label.")
    lines.append(
        "First give a short reasoning (one to three sentences) that names the "
        "evidence in the text, then the labels."
    )
    return "\n".join(lines)


def _model_name(model: str | Model) -> str:
    return model if isinstance(model, str) else model.model_name


def _hit(key: str) -> dict | None:
    """The cache entry's output dict; an old-shape entry (a bare label list, no reasoning) is a miss."""
    hit = cost.cache_get(key)
    return (
        hit["output"] if hit is not None and isinstance(hit["output"], dict) else None
    )


def is_cached(text: str, prompt: str, taxonomy: Taxonomy, model: str | Model) -> bool:
    """True when `classify` would answer from the cache. Calls nothing."""
    key = cost.cache_key(_model_name(model), system_prompt(prompt, taxonomy), text)
    return _hit(key) is not None


async def classify(
    text: str,
    prompt: str,
    taxonomy: Taxonomy,
    model: str | Model,
    *,
    timed: bool = True,
) -> Prediction:
    """Classify one text. Cache hits cost nothing and record no timing; failures are not cached."""
    system = system_prompt(prompt, taxonomy)
    name = _model_name(model)
    key = cost.cache_key(name, system, text)
    if (out := _hit(key)) is not None:
        return Prediction(out["labels"], cached=True, reasoning=out["reasoning"])

    # a Literal built at runtime from the taxonomy; the type checker can't see through it
    label_type = Literal[tuple(all_labels(taxonomy))]  # ty: ignore[invalid-type-form]

    class Classification(BaseModel):
        reasoning: str  # declared first so the model explains before it decides
        labels: list[label_type]

    agent = Agent(model, output_type=Classification, system_prompt=system)

    @agent.output_validator
    def check(out: Classification) -> Classification:
        try:
            validate_labels(out.labels, taxonomy)
        except ValueError as e:
            raise ModelRetry(str(e)) from e
        return out

    start = time.monotonic()
    try:
        result = await agent.run(text)
    except UnexpectedModelBehavior as e:
        return Prediction(None, error=e.message)
    seconds = time.monotonic() - start
    usage = result.usage
    cost.record(name, usage, cost.messages_dollars(result.new_messages()))
    if timed:
        cost.record_timing("classify", 1, seconds)
    out = result.output
    cost.cache_put(key, {"labels": list(out.labels), "reasoning": out.reasoning}, usage)
    return Prediction(list(out.labels), reasoning=out.reasoning)


async def classify_many(
    texts: list[str],
    prompt: str,
    taxonomy: Taxonomy,
    model: str | Model,
    *,
    concurrency: int = 8,
) -> AsyncIterator[tuple[int, Prediction]]:
    """Yield (index into texts, prediction) as each finishes, so callers can write incrementally.

    Records one wall-clock timing for the live (non-cached) items of the batch.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def one(i: int) -> tuple[int, Prediction]:
        async with semaphore:
            return i, await classify(texts[i], prompt, taxonomy, model, timed=False)

    tasks = [asyncio.create_task(one(i)) for i in range(len(texts))]
    start = time.monotonic()
    live = 0
    last_live = start
    try:
        for finished in asyncio.as_completed(tasks):
            i, prediction = await finished
            if not prediction.cached:
                live += 1
                last_live = time.monotonic()
            yield i, prediction
    finally:
        for task in tasks:
            task.cancel()
        if live:
            cost.record_timing("classify", live, last_live - start)


def redo_plan(from_stage: int = 1) -> list[dict]:
    """One row per stale or incomplete stage: how many model calls redoing it makes live and how many
    come from the cache, and what the live ones cost. Calls nothing.

    Stages are counted in order, as a user redoing them would run them: an item an earlier stage
    classifies live is a cache hit for a later one. Stages without model calls have None counts.
    Dollars is None with price_unknown set when there are live calls and no known price, never 0.
    """
    status = files.stage_status()
    todo = [n for n in range(1, 10) if status[n][0] in ("stale", "incomplete")]
    if not todo:
        return []
    config = files.read_config()
    taxonomy = files.read_taxonomy() if files.read_text("taxonomy.yaml") else None
    prompt = files.read_text("prompt.md") or ""
    gold = files.read_gold()
    by_id = {c["id"]: c["text"] for c in files.read_jsonl("candidates.jsonl")}
    sample = json.loads(files.read_text("threshold_sample.json") or "{}")
    has_threshold = files.read_text("threshold.json") is not None
    texts = {  # what each stage sends to the classifier
        5: [r.text for r in gold if r.split == "dev" and r.labels],
        6: [r.text for r in gold if r.split == "test" and r.labels],
        7: [by_id[i] for band in sample.get("ids", []) for i in band if i in by_id],
        8: [c["text"] for c in files.pending()] if has_threshold else [],
    }
    rows = []
    done: set[str] = set()  # texts an earlier stage of this plan classifies live
    for n in todo:
        live = cached = model = None
        if n == 2:
            model = config.embedding_model
            hits = [
                cost.cache_get(cost.cache_key(model, "embed_query", seed)) is not None
                for seed in candidates.read_seeds()
            ]
            live, cached = hits.count(False), hits.count(True)
        elif n in texts and taxonomy is not None:
            model = config.classifier_model
            hits = [
                t in done or is_cached(t, prompt, taxonomy, model) for t in texts[n]
            ]
            live, cached = hits.count(False), hits.count(True)
            done |= {t for t, hit in zip(texts[n], hits) if not hit}
        dollars, unknown = (0.0, False) if live == 0 else (None, False)
        if live and model:
            per_call, _ = cost.per_call_dollars(model)
            dollars, unknown = (
                (None, True) if per_call is None else (per_call * live, False)
            )
        if n >= from_stage:
            rows.append(
                {
                    "stage": n,
                    "status": status[n][0],
                    "reason": status[n][1],
                    "live_calls": live,
                    "cached_calls": cached,
                    "dollars": dollars,
                    "price_unknown": unknown,
                }
            )
    return rows
