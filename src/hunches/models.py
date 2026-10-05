"""Model lists and prices for the pickers. The list of model strings comes from pydantic-ai;
genai-prices only annotates it (its ids are price-matching rules, not API strings)."""

import typing
from dataclasses import dataclass
from datetime import UTC, datetime

from genai_prices import data_snapshot
from genai_prices.types import ModelInfo, TieredPrices
from pydantic_ai.embeddings import KnownEmbeddingModelName
from pydantic_ai.models import KnownModelName

from hunches.system import RECOMMENDED

NO_PRICE = "no price: cost will show ?"


@dataclass
class ModelRow:
    model: str
    price: str
    deprecated: bool
    recommended: bool


def known_models(embedding: bool = False) -> list[str]:
    alias = KnownEmbeddingModelName if embedding else KnownModelName
    return list(typing.get_args(alias.__value__))


def snapshot_date() -> str:
    stamp = data_snapshot.get_snapshot().timestamp
    return f"{stamp.year:04d}-{stamp.month:02d}-{stamp.day:02d}"


def _info(model: str) -> ModelInfo | None:
    provider, sep, name = model.partition(":")
    if not sep:
        return None
    try:
        return data_snapshot.get_snapshot().find_provider_model(
            name, None, provider, None
        )[1]
    except LookupError:
        return None


def price_label(model: str) -> str:
    info = _info(model)
    price = info.get_prices(datetime.now(UTC)) if info else None
    if price is None or price.input_mtok is None:
        return NO_PRICE
    sides = [price.input_mtok] + (
        [price.output_mtok] if price.output_mtok is not None else []
    )
    starts = [t.start for p in sides if isinstance(p, TieredPrices) for t in p.tiers]
    base = [p.base if isinstance(p, TieredPrices) else p for p in sides]
    label = f"${base[0]:.2f} in"
    if len(base) == 2:
        label += f" / ${base[1]:.2f} out"
    label += " per 1M tokens"
    if starts:
        label += f" (higher above {min(starts) / 1000:g}K prompt tokens)"
    return label


def model_rows(provider: str, embedding: bool = False) -> list[ModelRow]:
    recommended = {
        v for r in RECOMMENDED.values() for k, v in r.items() if k != "thinking"
    }
    rows = []
    for model in known_models(embedding):
        if model.startswith(f"{provider}:"):
            info = _info(model)
            rows.append(
                ModelRow(
                    model,
                    price_label(model),
                    bool(info and info.deprecated),
                    model in recommended,
                )
            )
    return rows
