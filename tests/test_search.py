import json

import numpy as np
import pytest

from hunches import files, search


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def local_corpus(tmp_path, model="m"):
    # unit vectors at known angles to the query [1, 0]
    vectors = np.array(
        [[1, 0], [0.6, 0.8], [0.5, 0.8660254], [0.59, 0.80752], [0, 1]], np.float32
    )
    d = tmp_path / "corpus"
    d.mkdir()
    np.save(d / "vectors.npy", vectors * 3)  # un-normalised on purpose
    items = [{"id": f"i{i}", "text": f"t{i}"} for i in range(5)]
    (d / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in items))
    (d / "meta.json").write_text(json.dumps({"embedding_model": model}))
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir=str(d),
            embedding_model="m",
        )
    )
    return d


def test_local_floor_inclusive_and_sorted(tmp_path):
    local_corpus(tmp_path)
    hits, capped = search.search([2.0, 0.0], 0.6)  # i1 is exactly 0.6; i3 is 0.59
    assert not capped
    assert [h[0] for h in hits] == ["i0", "i1"]
    assert hits[0] == ("i0", "t0", pytest.approx(1.0))
    assert hits[1][2] == pytest.approx(0.6, abs=1e-6)


def test_local_model_mismatch_refused(tmp_path):
    local_corpus(tmp_path, model="other")
    with pytest.raises(ValueError, match="mismatch"):
        search.search([1.0, 0.0], 0.6)


def test_local_row_count_mismatch(tmp_path):
    d = local_corpus(tmp_path)
    (d / "items.jsonl").write_text('{"id": "a", "text": "b"}\n')
    with pytest.raises(ValueError, match="rows"):
        search.search([1.0, 0.0], 0.6)


class FakeS3:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def query_vectors(self, **kw):
        self.calls.append(kw)
        return self.pages[len(self.calls) - 1]


def vec(key, distance):
    return {"key": key, "distance": distance, "metadata": {"text": f"text {key}"}}


def s3_setup(monkeypatch, pages):
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            backend="s3",
            s3_bucket="b",
            s3_index="i",
            embedding_model="m",
        )
    )
    fake = FakeS3(pages)
    monkeypatch.setattr("boto3.client", lambda name, **kw: fake)
    return fake


def test_s3_pages_and_floor(monkeypatch):
    fake = s3_setup(
        monkeypatch,
        [
            {"vectors": [vec("a", 0.25)], "nextToken": "t"},
            {"vectors": [vec("b", 0.4), vec("c", 0.5)]},  # c is below the 0.6 floor
        ],
    )
    hits, capped = search.search([1.0, 0.0], 0.6)
    assert [(h[0], h[1]) for h in hits] == [("a", "text a"), ("b", "text b")]
    assert hits[0][2] == pytest.approx(0.75)
    assert not capped
    assert fake.calls[0]["topK"] == search.S3_TOP_K
    assert fake.calls[0]["returnDistance"] and fake.calls[0]["returnMetadata"]
    assert fake.calls[1]["nextToken"] == "t"


def test_s3_capped(monkeypatch):
    monkeypatch.setattr(search, "S3_TOP_K", 2)
    s3_setup(monkeypatch, [{"vectors": [vec("a", 0.1), vec("b", 0.2)]}])
    hits, capped = search.search([1.0, 0.0], 0.6)
    assert len(hits) == 2 and capped


def test_s3_uses_the_configured_region(monkeypatch):
    s3_setup(monkeypatch, [{"vectors": []}])
    made = []

    def client(name, **kw):
        made.append((name, kw))
        return FakeS3([{"vectors": []}])

    monkeypatch.setattr("boto3.client", client)
    config = files.read_config()
    config.s3_region = "eu-west-1"
    files.write_config(config)
    search.search([1.0, 0.0], 0.6)
    assert made == [("s3vectors", {"region_name": "eu-west-1"})]
