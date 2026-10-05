import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models import Model

from hunches import cost
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
    hit = cost.cache_get(key)
    # an old-shape entry (a bare label list) has no reasoning: treat it as a miss
    if hit is not None and isinstance(hit["output"], dict):
        out = hit["output"]
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
