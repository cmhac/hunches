import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import numpy as np

from hunches import keys
from hunches.files import Config, pg_setting, read_config

# Max results per QueryVectors request: 10,000 (100 per page, followed via nextToken).
# Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html
S3_TOP_K = 10_000

IAM_CHECK = (
    "Check: the database user has the rds_iam role, the AWS identity may rds-db:connect "
    "on this DbiResourceId/user, and the URL host is the instance endpoint "
    "(not a custom DNS name)."
)


def pg_message(e: Exception, config: Config, token: str | None = None) -> str:
    """An exception's text with the URL, password and IAM token replaced by ***, plus a hint."""
    text = str(e)
    url = keys.resolve(pg_setting(config, "pg_url_var")) or ""
    password = urlsplit(url).password or ""
    secrets = [url, password, unquote(password), token or ""]
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            text = text.replace(secret, "***")
    hint = None
    if "conflict with recovery" in text:
        hint = (
            "Fix: run the search against the primary/writer endpoint, or a replica "
            "configured for long queries."
        )
    elif "statement timeout" in text:
        hint = (
            "Fix: raise statement_timeout for this role, or set "
            "pg_statement_timeout_s in config.toml"
        )
    elif re.search(r"different \w+ dimensions", text):
        hint = (
            "Fix: embedding_model in .hunches/config.toml must be the model the "
            "table was embedded with."
        )
    elif token and "authentication failed" in text:
        hint = IAM_CHECK
    return f"{text}\n{hint}" if hint else text


def pg_connect(config: Config):
    """Open a read-only connection; the caller owns it and the one transaction it starts."""
    try:
        import psycopg
    except ImportError as e:
        raise ImportError(
            "The pgvector backend needs psycopg: pip install hunches[pg]"
        ) from e
    if not config.pg_table:
        raise ValueError("config.toml: pg_table is required for pgvector")
    var = pg_setting(config, "pg_url_var")
    url = keys.resolve(var)
    if not url:
        raise ValueError(
            f"config.toml: pg_url_var {var} is not set (environment or keyring)"
        )
    kwargs: dict = {"prepare_threshold": None}
    token = None
    if pg_setting(config, "pg_auth") == "rds_iam":
        token = _iam_token(config, url)
        kwargs["password"] = token  # a keyword, never inside the URL string
        if "sslmode" not in url:
            kwargs["sslmode"] = "require"
    try:
        conn = psycopg.connect(url, **kwargs)
        conn.read_only = True
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        if config.pg_statement_timeout_s is not None:  # 0 is a value: no limit
            with conn.cursor() as cur:
                cur.execute(  # ty: ignore[no-matching-overload]  int() cast, not user text
                    f"SET LOCAL statement_timeout = {int(config.pg_statement_timeout_s) * 1000}"
                )
    except Exception as e:  # noqa: BLE001  the driver's own classes are not imported here
        raise RuntimeError(pg_message(e, config, token)) from None
    return conn


def _iam_token(config: Config, url: str) -> str:
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as e:
        raise ImportError(
            "IAM authentication needs boto3: pip install hunches[rds]"
        ) from e
    parts = urlsplit(url)
    if not (parts.hostname and parts.username):
        raise ValueError("config.toml: the rds_iam URL needs a host and a user")
    try:
        session = boto3.Session(profile_name=config.pg_aws_profile)
        region = config.pg_aws_region or session.region_name
        if not region:
            raise ValueError(
                "pg_aws_region is not set and boto3 found no default region"
            )
        return session.client("rds", region_name=region).generate_db_auth_token(
            DBHostname=parts.hostname,
            Port=parts.port or 5432,
            DBUsername=unquote(parts.username),
            Region=region,
        )
    except (BotoCoreError, ClientError) as e:
        raise ValueError(f"AWS: {e}") from None


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
