import json

import numpy as np
import pytest
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.usage import RequestUsage
from textual.widgets import DataTable, Label, Static

from hunches import files, search
from hunches.app import HunchesApp
from hunches.screens.search import SearchScreen


class StubEmbedder(Embedder):
    def __init__(self, vectors):
        super().__init__(TestEmbeddingModel("m"))
        self.vectors = vectors

    async def embed_query(self, query, *, settings=None):
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
    # cosine with [1, 0] is the first coordinate: 1.0, 0.8, 0.7, 0.62, 0.3
    vectors = [[1, 0], [0.8, 0.6], [0.7, 0.714], [0.62, 0.7846], [0.3, 0.954]]
    np.save(corpus / "vectors.npy", np.array(vectors, np.float32))
    items = [{"id": f"i{i}", "text": f"t{i}"} for i in range(5)]
    (corpus / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in items))
    (corpus / "meta.json").write_text(json.dumps({"embedding_model": "m"}))
    files.write_config(files.Config(corpus_dir=str(corpus), embedding_model="m"))
    files.write_text("seeds.csv", "seed\nalpha\n")


async def open_search(pilot, app):
    await pilot.pause()
    app.goto_stage(2)
    await pilot.pause()
    assert isinstance(app.screen, SearchScreen)
    return app.screen


async def run(pilot, app, screen):
    await pilot.press("r")
    await app.workers.wait_for_complete()
    await pilot.pause()


def rows(screen):
    table = screen.query_one("#bands", DataTable)
    return [list(table.get_row_at(i)) for i in range(table.row_count)]


async def test_band_table_matches_counts():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        await run(pilot, app, screen)
        # similarities 1.0 (0.75+), 0.8 (0.75+), 0.7 (0.7-0.725), 0.62 (0.6-0.625)
        assert rows(screen) == [
            ["0.6-0.625", "1", "4"],
            ["0.625-0.65", "0", "3"],
            ["0.65-0.675", "0", "3"],
            ["0.675-0.7", "0", "3"],
            ["0.7-0.725", "1", "3"],
            ["0.725-0.75", "0", "2"],
            ["0.75+", "2", "2"],
            ["Total", "4", ""],
        ]
        assert "4  alpha" in str(screen.query_one("#seeds", Static).render())
        assert not str(screen.query_one("#warning", Label).render())


async def test_capped_warning_with_stubbed_s3(monkeypatch):
    class FakeS3:
        def query_vectors(self, **kw):
            v = {"key": "a", "distance": 0.1, "metadata": {"text": "text a"}}
            return {"vectors": [v, {**v, "key": "b"}]}

    files.write_config(
        files.Config(backend="s3", s3_bucket="b", s3_index="i", embedding_model="m")
    )
    monkeypatch.setattr("boto3.client", lambda name: FakeS3())
    monkeypatch.setattr(search, "S3_TOP_K", 2)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        await run(pilot, app, screen)
        assert "topK cap of 2" in str(screen.query_one("#warning", Label).render())
        assert rows(screen)[-1][:2] == ["Total", "2"]


async def test_embedding_model_mismatch_is_shown():
    files.write_config(files.Config(corpus_dir="corpus", embedding_model="other-model"))
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        await run(pilot, app, screen)
        error = str(screen.query_one("#error", Label).render())
        assert "mismatch" in error and "embedding_model" in error
        assert app.is_running
