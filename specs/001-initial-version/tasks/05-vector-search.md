# 05 — Vector search (local and S3)

Spec section: Vector search, Candidate generation (floor).

## Goal
One function: `search(query_vector, floor) -> list[(id, text, similarity)]`, with a plain `if backend == "local"` / `else` inside it. No classes or interfaces.

## Do
- `src/hunches/search.py`.
- Local: load `vectors.npy`, `items.jsonl`, `meta.json`. L2-normalise, matrix-multiply, return everything with similarity ≥ floor. Validate `len(items) == N` rows and raise a clear error otherwise.
- Embedding model check: refuse to search when `meta.json["embedding_model"]` (local) differs from `config.toml`'s `embedding_model`. For S3 the config value is the only record, so just use it.
- S3: `boto3.client("s3vectors")`, `query_vectors` with cosine distance, `returnDistance=True`, `returnMetadata=True`. Key is the id, text is in metadata. Convert distance to similarity (verify the exact distance definition in the AWS docs; do not assume `1 - d`).
- **topK cap.** Look up the real per-query maximum in the AWS docs and record the source URL in a comment. If the cap is below the number of hits above the floor, return the highest-scoring hits and report a `capped=True` flag so the UI can show a warning. If you cannot verify the cap, stop and list it under "Needs human".
- `boto3` is an optional extra. Import it inside the S3 branch and give a helpful error pointing at `pip install hunches[s3]`.
- Tests: tiny hand-built `vectors.npy` with known similarities (including an item exactly at the floor and one just below); model-mismatch refusal; S3 with a stubbed client returning a canned `query_vectors` response, including the capped case.

## Done when
- Tests pass and no test touches the network or AWS.

## Needs human
- Possibly the S3 `topK` maximum (see above).
- Optional real-S3 check needs AWS credentials and an index; not required to finish this task.
