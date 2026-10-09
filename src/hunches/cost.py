import hashlib
import json
from decimal import Decimal

from pydantic_ai.embeddings import EmbeddingResult
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.usage import RequestUsage, RunUsage

from hunches.files import ensure_root, read_text, root, write_text


def cache_key(model: str, prompt: str, text: str) -> str:
    # JSON-encoding the tuple keeps ("ab", "c") and ("a", "bc") distinct
    return hashlib.sha256(json.dumps([model, prompt, text]).encode()).hexdigest()


def cache_get(key: str) -> dict | None:
    """Return {"output": ..., "usage": {...}} or None. A hit must not be recorded as cost or timing."""
    path = root() / "cache" / f"{key}.json"
    return json.loads(path.read_text()) if path.exists() else None


def cache_put(key: str, output, usage: RunUsage | RequestUsage) -> None:
    """Store a JSON-serialisable output plus its original usage (for estimates)."""
    ensure_root()
    (root() / "cache").mkdir(exist_ok=True)
    entry = {
        "output": output,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
    }
    (root() / "cache" / f"{key}.json").write_text(json.dumps(entry))


def messages_dollars(messages: list[ModelMessage]) -> float | None:
    """Dollars for the model responses in `messages` (use `result.new_messages()`); None if any price is unknown."""
    total = Decimal(0)
    for message in messages:
        if isinstance(message, ModelResponse):
            try:
                total += message.cost().total_price
            except LookupError:
                return None
    return float(total)


def embedding_dollars(result: EmbeddingResult) -> float | None:
    try:
        return float(result.cost().total_price)
    except LookupError:
        return None


def _read() -> dict:
    text = read_text("cost.json")
    return json.loads(text) if text else {"models": {}, "timings": []}


def _write(data: dict) -> None:
    write_text("cost.json", json.dumps(data, indent=2) + "\n")


def record(model: str, usage: RunUsage | RequestUsage, dollars: float | None) -> None:
    """Add one live call. `dollars` None means the price is unknown; it is stored as null, never 0."""
    data = _read()
    entry = data["models"].setdefault(
        model, {"input_tokens": 0, "output_tokens": 0, "calls": 0, "dollars": 0.0}
    )
    entry["input_tokens"] += usage.input_tokens
    entry["output_tokens"] += usage.output_tokens
    entry["calls"] += 1
    # once any call of a model is unknown, the model's dollars stay unknown
    if dollars is None or entry["dollars"] is None:
        entry["dollars"] = None
    else:
        entry["dollars"] += dollars
    _write(data)


def total() -> tuple[float, bool]:
    """(dollars over models with a known price, unknown flag). If the flag is set the dollars are only a lower bound; show "?"."""
    models = _read()["models"].values()
    known = sum(m["dollars"] for m in models if m["dollars"] is not None)
    return known, any(m["dollars"] is None for m in models)


def breakdown() -> dict[str, dict]:
    return _read()["models"]


def per_call_dollars(model: str) -> tuple[float | None, bool]:
    """(average dollars per recorded live call, whether any call is recorded).

    None with True: the price is unknown; with False: there is no sample to price from.
    """
    entry = breakdown().get(model)
    if not entry or not entry["calls"]:
        return None, False
    if entry["dollars"] is None:
        return None, True
    return entry["dollars"] / entry["calls"], True


def record_timing(label: str, n_items: int, seconds: float) -> None:
    """Live (non-cached) work only; used for items/sec estimates."""
    data = _read()
    data["timings"].append({"label": label, "n_items": n_items, "seconds": seconds})
    _write(data)


def items_per_second(label: str | None = None) -> float | None:
    rows = [t for t in _read()["timings"] if label is None or t["label"] == label]
    seconds = sum(t["seconds"] for t in rows)
    return sum(t["n_items"] for t in rows) / seconds if seconds > 0 else None
