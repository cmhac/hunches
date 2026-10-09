import csv
import hashlib
import io
import json
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic_ai import Embedder

from hunches.cost import cache_get, cache_key, cache_put, embedding_dollars, record
from hunches.files import read_config, read_text, write_jsonl, write_text
from hunches.search import search

FLOOR = 0.60
# Lower edges of the similarity bands; the last band (0.75+) is open-ended.
BANDS = [0.60, 0.625, 0.65, 0.675, 0.70, 0.725, 0.75]


def read_seeds() -> list[str]:
    """Seed phrases from seeds.csv: first column, blank lines and an optional `seed` header skipped."""
    rows = csv.reader(io.StringIO(read_text("seeds.csv") or ""))
    seeds = [r[0].strip() for r in rows if r and r[0].strip()]
    return seeds[1:] if seeds and seeds[0].lower() == "seed" else seeds


def seeds_digest(seeds: list[str]) -> str:
    return hashlib.sha256(json.dumps(seeds).encode()).hexdigest()


def seeds_changed() -> bool:
    """True when candidates were built from different seeds. No meta file (old project) counts as unchanged."""
    meta = read_text("candidates.meta.json")
    if meta is None:
        return False
    return json.loads(meta)["seeds_digest"] != seeds_digest(read_seeds())


async def embed_seeds(
    seeds: list[str], embedder: Embedder | None = None
) -> list[list[float]]:
    """Query embeddings, one per seed. Cache hits cost nothing; live calls are recorded."""
    model = read_config().embedding_model
    embedder = embedder or Embedder(model)
    vectors = []
    for seed in seeds:
        key = cache_key(model, "embed_query", seed)
        hit = cache_get(key)
        if hit:
            vectors.append(hit["output"])
            continue
        result = await embedder.embed_query(seed)
        vector = [float(x) for x in result.embeddings[0]]
        cache_put(key, vector, result.usage)
        record(model, result.usage, embedding_dollars(result))
        vectors.append(vector)
    return vectors


def band_of(similarity: float) -> int:
    """Index into BANDS of the band containing `similarity` (lower-inclusive); -1 below the floor."""
    return max((i for i, edge in enumerate(BANDS) if similarity >= edge), default=-1)


def band_counts(candidates: list[dict]) -> list[int]:
    counts = [0] * len(BANDS)
    for c in candidates:
        if (i := band_of(c["max_similarity"])) >= 0:
            counts[i] += 1
    return counts


def top_seeds(rows: list[dict], threshold: float, n: int = 10) -> list[tuple[str, int]]:
    """Seeds ranked by items won among rows at or above `threshold` (best_seed is each item's argmax)."""
    won = Counter(r["best_seed"] for r in rows if r["max_similarity"] >= threshold)
    return won.most_common(n)


async def build_candidates(
    embedder: Embedder | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> bool:
    """Write candidates.jsonl; returns True if any search hit the S3 topK cap (show a warning).

    `progress(done, total, seed)` is called after each seed's search.
    """
    seeds = read_seeds()
    best: dict[str, dict] = {}
    capped = False
    vectors = await embed_seeds(seeds, embedder)
    for done, (seed, vector) in enumerate(zip(seeds, vectors), 1):
        hits, seed_capped = search(vector, FLOOR)
        capped = capped or seed_capped
        for id, text, sim in hits:
            if id not in best or sim > best[id]["max_similarity"]:
                best[id] = {
                    "id": id,
                    "text": text,
                    "max_similarity": sim,
                    "best_seed": seed,
                }
        if progress:
            progress(done, len(seeds), seed)
    rows = sorted(best.values(), key=lambda r: (-r["max_similarity"], r["id"]))
    write_jsonl("candidates.jsonl", rows)
    meta = {
        "seeds_digest": seeds_digest(seeds),
        "written_at": datetime.now(UTC).isoformat(),
        "floor": FLOOR,
        "embedding_model": read_config().embedding_model,
    }
    write_text("candidates.meta.json", json.dumps(meta))
    return capped
