import json
from pathlib import Path

import numpy as np

from hunches.files import read_config

# Max results per QueryVectors request: 10,000 (100 per page, followed via nextToken).
# Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html
S3_TOP_K = 10_000


def search(
    query_vector: list[float], floor: float
) -> tuple[list[tuple[str, str, float]], bool]:
    """Return ([(id, text, similarity)], capped), best first, all with similarity >= floor.

    `capped` is True when the S3 per-query topK limit may have hidden hits above the floor
    (the highest-scoring hits are returned); the UI must show a warning. Local is never capped.
    """
    config = read_config()
    if config.backend == "local":
        if config.corpus_dir is None:
            raise ValueError(
                "config.toml: corpus_dir is required for the local backend"
            )
        corpus = Path(config.corpus_dir)
        meta_model = json.loads((corpus / "meta.json").read_text())["embedding_model"]
        if meta_model != config.embedding_model:
            raise ValueError(
                f"embedding model mismatch: corpus uses {meta_model!r}, "
                f"config.toml has {config.embedding_model!r}"
            )
        vectors = np.load(corpus / "vectors.npy").astype(np.float32)
        items = [
            json.loads(line)
            for line in (corpus / "items.jsonl").read_text().splitlines()
            if line.strip()
        ]
        if len(items) != len(vectors):
            raise ValueError(
                f"items.jsonl has {len(items)} rows but vectors.npy has {len(vectors)}"
            )
        query = np.asarray(query_vector, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1)
        norms[norms == 0] = 1
        sims = (vectors / norms[:, None]) @ (query / np.linalg.norm(query))
        order = np.argsort(-sims)
        return [
            (items[i]["id"], items[i]["text"], float(sims[i]))
            for i in order
            if sims[i] >= floor
        ], False

    try:
        import boto3
    except ImportError as e:
        raise ImportError("The S3 backend needs boto3: pip install hunches[s3]") from e
    if not (config.s3_bucket and config.s3_index):
        raise ValueError("config.toml: s3_bucket and s3_index are required for s3")
    client = boto3.client("s3vectors", region_name=config.s3_region)
    params = {
        "vectorBucketName": config.s3_bucket,
        "indexName": config.s3_index,
        "queryVector": {"float32": [float(x) for x in query_vector]},
        "topK": S3_TOP_K,
        "returnDistance": True,
        "returnMetadata": True,
    }
    hits: list[tuple[str, str, float]] = []
    below_floor = False
    response = client.query_vectors(**params)
    while True:
        for v in response["vectors"]:
            # Cosine distance is taken as 1 - cosine similarity; the AWS docs do not state
            # this definition explicitly (see task 05 notes).
            sim = 1.0 - v["distance"]
            if sim < floor:
                below_floor = True
                break
            hits.append((v["key"], v["metadata"]["text"], sim))
        if below_floor or not response.get("nextToken"):
            break
        response = client.query_vectors(**params, nextToken=response["nextToken"])
    return hits, len(hits) >= S3_TOP_K and not below_floor
