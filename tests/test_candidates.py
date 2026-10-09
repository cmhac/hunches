import json

import numpy as np
import pytest
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.usage import RequestUsage

from hunches import candidates, cost, files


class StubEmbedder(Embedder):
    """Maps seed text to a fixed 2-d vector; counts live calls."""

    def __init__(self, vectors):
        super().__init__(TestEmbeddingModel("m"))
        self.vectors, self.calls = vectors, 0

    async def embed_query(self, query, *, settings=None):
        self.calls += 1
        return EmbeddingResult(
            [self.vectors[query]],
            inputs=[query],
            input_type="query",
            model_name="m",
            provider_name="test",
            usage=RequestUsage(input_tokens=3),
        )


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    # unit vectors; cosine with [1, 0] is the first coordinate, with [0, 1] the second
    vectors = [[1, 0], [0.8, 0.6], [0.6, 0.8], [0, 1], [0.5, 0.8660254]]
    np.save(corpus / "vectors.npy", np.array(vectors, np.float32))
    items = [{"id": f"i{i}", "text": f"t{i}"} for i in range(5)]
    (corpus / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in items))
    (corpus / "meta.json").write_text(json.dumps({"embedding_model": "m"}))
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir=str(corpus),
            embedding_model="m",
        )
    )
    files.write_text("seeds.csv", "seed\nalpha\n\nbeta\n")


async def test_merge_takes_max_and_best_seed():
    embedder = StubEmbedder({"alpha": [1, 0], "beta": [0, 1]})
    assert await candidates.build_candidates(embedder) is False
    rows = files.read_jsonl("candidates.jsonl")
    # i0: alpha 1.0; i1: alpha 0.8 (beta 0.6); i2: beta 0.8 (alpha 0.6); i3: beta 1.0;
    # i4: beta 0.866 (alpha 0.5, below floor)
    assert [(r["id"], r["best_seed"]) for r in rows] == [
        ("i0", "alpha"),
        ("i3", "beta"),
        ("i4", "beta"),
        ("i1", "alpha"),
        ("i2", "beta"),
    ]
    assert rows[3]["max_similarity"] == pytest.approx(0.8)
    assert rows[3]["text"] == "t1"


async def test_second_run_identical_and_free():
    embedder = StubEmbedder({"alpha": [1, 0], "beta": [0, 1]})
    await candidates.build_candidates(embedder)
    first = (files.root() / "candidates.jsonl").read_text()
    spent = cost.breakdown()["m"]
    assert embedder.calls == 2 and spent["calls"] == 2
    await candidates.build_candidates(embedder)
    assert (files.root() / "candidates.jsonl").read_text() == first
    assert embedder.calls == 2 and cost.breakdown()["m"] == spent


@pytest.mark.parametrize(
    ("sim", "band"),
    [
        (0.5999, -1),
        (0.60, 0),
        (0.6249, 0),
        (0.625, 1),
        (0.70, 4),
        (0.7249, 4),
        (0.725, 5),
        (0.7499, 5),
        (0.75, 6),
        (0.99, 6),
    ],
)
def test_band_of(sim, band):
    assert candidates.band_of(sim) == band


def test_band_counts():
    rows = [{"max_similarity": s} for s in (0.60, 0.61, 0.625, 0.75, 0.9)]
    assert candidates.band_counts(rows) == [2, 1, 0, 0, 0, 0, 2]


def test_seeds_digest_is_sha256_of_json_list():
    import hashlib

    assert (
        candidates.seeds_digest(["a", "b"]) == hashlib.sha256(b'["a", "b"]').hexdigest()
    )
    assert candidates.seeds_digest(["a", "b"]) != candidates.seeds_digest(["b", "a"])


async def test_build_writes_meta_and_progress_per_seed():
    calls = []
    embedder = StubEmbedder({"alpha": [1, 0], "beta": [0, 1]})
    await candidates.build_candidates(
        embedder, progress=lambda done, total, seed: calls.append((done, total, seed))
    )
    assert calls == [(1, 2, "alpha"), (2, 2, "beta")]
    meta = json.loads(files.read_text("candidates.meta.json") or "")
    assert meta["seeds_digest"] == candidates.seeds_digest(["alpha", "beta"])
    assert meta["floor"] == 0.6
    assert meta["embedding_model"] == "m"  # config.toml's embedding_model
    assert meta["written_at"].endswith("+00:00")


async def test_seeds_changed_cases():
    embedder = StubEmbedder({"alpha": [1, 0], "beta": [0, 1], "gamma": [1, 0]})
    assert candidates.seeds_changed() is False  # nothing built, no meta
    await candidates.build_candidates(embedder)
    assert candidates.seeds_changed() is False  # unchanged
    files.write_text("seeds.csv", "seed\nbeta\n\nalpha\n")
    assert candidates.seeds_changed() is True  # reordered counts as changed
    files.write_text("seeds.csv", "seed\nalpha\n\nbeta\n")
    assert candidates.seeds_changed() is False  # back to the original
    files.write_text("seeds.csv", "seed\nalpha\n\ngamma\n")
    assert candidates.seeds_changed() is True  # edited
    (files.root() / "candidates.meta.json").unlink()
    assert candidates.seeds_changed() is False  # old project: meta missing = unchanged


def test_top_seeds_at_two_thresholds():
    rows = [
        {"max_similarity": s, "best_seed": b}
        for s, b in [(0.61, "A"), (0.62, "A"), (0.63, "A"), (0.7, "B"), (0.8, "B")]
    ]
    assert candidates.top_seeds(rows, 0.6) == [("A", 3), ("B", 2)]
    assert candidates.top_seeds(rows, 0.7) == [("B", 2)]  # A drops out, ranking changes
    assert candidates.top_seeds(rows, 0.65)[0] == ("B", 2)
    assert len(candidates.top_seeds(rows * 1, 0.6, n=1)) == 1
