import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import numpy as np

from hunches import keys, system
from hunches.files import Config, pg_setting, read_config

# Max results per QueryVectors request: 10,000 (100 per page, followed via nextToken).
# Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html
S3_TOP_K = 10_000
PG_TOP_K = 10_000
PG_BATCH = 5_000  # rows per round trip of the server-side cursors
# bytes added to every received row (id + text) when sizing a result: Python's tuple, float
# and str headers; a deliberately round estimate, not a measurement
PG_ROW_OVERHEAD = 128
MB = 1024 * 1024


class SearchCancelled(Exception):
    """The search was stopped with Stop.stop()."""


class Stop:
    """Handle for stopping a search from another thread: pass it to search_pg_exact and call
    stop(). Cancelling the Textual worker alone would leave the driver blocked in the query."""

    def __init__(self):
        self.conn = None
        self.stopped = False

    def stop(self):
        self.stopped = True
        if self.conn is not None:
            _cancel(self.conn)


def _cancel(conn):
    # cancel_safe() is psycopg 3.2+; the extras do not pin a version, so fall back plainly
    (getattr(conn, "cancel_safe", None) or conn.cancel)()


def _too_large(text: str, limit_mb: int) -> RuntimeError:
    return RuntimeError(
        f"{text} which exceeds the result limit of {limit_mb} MB. "
        "Use fewer seeds or raise the limit in System settings (F5)."
    )


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


def _regclass(table: str) -> str:
    """`schema.table` or `table` as a quoted name for a `%s::regclass` parameter."""
    schema, dot, name = table.partition(".")
    parts = [schema, name] if dot else [schema]
    return ".".join('"' + p.replace('"', '""') + '"' for p in parts)


def extension_version(conn) -> tuple[tuple[int, int, int], str]:
    """((major, minor, patch), schema) of the vector extension."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.extversion, n.nspname FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'"
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError(
            "The vector extension is not installed in this database "
            "(CREATE EXTENSION vector needs a DBA)."
        )
    # a suffix such as 0.8.0rc1 or 1.0.0-beta is ignored
    parts = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", row[0])
    major, minor, patch = (int(g or 0) for g in parts.groups()) if parts else (0, 0, 0)
    return (major, minor, patch), row[1]


def require_index_mode_version(version: tuple[int, int, int], mode: str) -> None:
    if mode == "index" and version < (0, 8, 0):
        raise RuntimeError(
            f'pg_search = "index" needs pgvector 0.8.0 or newer (found '
            f"{'.'.join(map(str, version))}). "
            'Use pg_search = "exact", or upgrade the extension.'
        )


def column_type(conn, table: str, column: str) -> tuple[str, str, int | None]:
    """(type name, type schema, dimension or None) of a vector or halfvec column."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT t.typname, tn.nspname, a.atttypmod FROM pg_attribute a "
            "JOIN pg_type t ON t.oid = a.atttypid "
            "JOIN pg_namespace tn ON tn.oid = t.typnamespace "
            "WHERE a.attrelid = %s::regclass AND a.attname = %s AND NOT a.attisdropped",
            (_regclass(table), column),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError(f'column "{column}" of relation "{table}" does not exist')
    typename, schema, typmod = row
    if typename not in ("vector", "halfvec"):
        raise RuntimeError(
            f'Column "{column}" has type {typename}; hunches supports vector and halfvec.'
        )
    return typename, schema, typmod if typmod > 0 else None  # -1: no dimension declared


def table_estimates(
    conn, table: str, text_column: str
) -> tuple[int | None, int | None]:
    """(planner row estimate, average text width in bytes); None where there are no statistics."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT reltuples FROM pg_class WHERE oid = %s::regclass",
            (_regclass(table),),
        )
        row = cur.fetchone()
        rows = int(row[0]) if row and row[0] >= 0 else None  # -1: never analysed
        cur.execute(
            "SELECT max(s.avg_width) FROM pg_stats s "
            "JOIN pg_class c ON c.relname = s.tablename "
            "JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = s.schemaname "
            "WHERE c.oid = %s::regclass AND s.attname = %s",
            (_regclass(table), text_column),
        )
        row = cur.fetchone()
    return rows, row[0] if row and row[0] is not None else None


def search_pg_exact(
    vectors, floor: float, progress=None, stop: Stop | None = None
) -> tuple[list[list[tuple[str, str, float]]], bool]:
    """One pass over the table for every seed: ([hits per seed], capped), best first.

    Runs in the one read-only REPEATABLE READ transaction pg_connect opened. Step 1 returns
    ids only (a narrow sort), step 2 the text of the distinct ids. `capped` is True when some
    seed has exactly PG_TOP_K hits. The result size is limited by system.pg_max_result_mb
    (0 = none): refused up front from the planner statistics, or aborted while streaming.
    `progress(received, 0, "")` is called per row received (a zero total is unknown); `stop`
    is a Stop whose stop() cancels the running query, after which SearchCancelled is raised.
    """
    config = read_config()
    sys_ = system.read_system()
    limit_mb = sys_.pg_max_result_mb if sys_ else 512
    limit = limit_mb * MB
    conn = pg_connect(config)
    if stop:
        stop.conn = conn
    received = rows_in = 0

    def count(id_, text=""):
        nonlocal received, rows_in
        received += len(str(id_)) + len(text.encode()) + PG_ROW_OVERHEAD
        rows_in += 1
        if progress:
            progress(rows_in, 0, "")
        if limit and received > limit:
            _cancel(conn)
            conn.close()
            raise _too_large(
                f"Search has already received {received / MB:.1f} MB ({rows_in:,} rows),",
                limit_mb,
            )

    try:
        from psycopg import sql

        if stop and stop.stopped:
            raise SearchCancelled
        extension_version(conn)  # for its "not installed" error
        table_name = config.pg_table or ""  # pg_connect has checked it
        table = sql.Identifier(*table_name.split(".", 1))
        id_col = sql.Identifier(pg_setting(config, "pg_id_column"))
        text_col = sql.Identifier(pg_setting(config, "pg_text_column"))
        vec_col = sql.Identifier(pg_setting(config, "pg_vector_column"))
        typename, type_schema, _ = column_type(
            conn, table_name, pg_setting(config, "pg_vector_column")
        )
        step1 = sql.SQL(
            "WITH seeds AS MATERIALIZED (SELECT u.i - 1 AS i, u.q::{vtype} AS q "
            "FROM unnest(%s::text[]) WITH ORDINALITY AS u(q, i)), "
            "pairs AS (SELECT t.{id} AS id, d.i, d.sim FROM {table} t "
            "CROSS JOIN LATERAL (SELECT s.i, 1 - (t.{vec} OPERATOR({schema}.<=>) s.q) AS sim "
            "FROM seeds s OFFSET 0) d "
            "WHERE t.{vec} IS NOT NULL AND d.sim >= %s AND d.sim <> 'NaN'), "
            "ranked AS (SELECT *, row_number() OVER "
            "(PARTITION BY i ORDER BY sim DESC, id) AS rn FROM pairs) "
            "SELECT id, i, sim FROM ranked WHERE rn <= %s"
        ).format(
            vtype=sql.Identifier(type_schema, typename),
            id=id_col,
            table=table,
            vec=vec_col,
            schema=sql.Identifier(type_schema),
        )
        if limit:
            _, width = table_estimates(
                conn, table_name, pg_setting(config, "pg_text_column")
            )
            if width is not None:  # no statistics: nothing to check
                per_row = width + PG_ROW_OVERHEAD
                worst = len(vectors) * PG_TOP_K * per_row
                if worst > limit:
                    raise _too_large(
                        f"Search could return up to ~{worst / MB:.0f} MB "
                        f"({len(vectors)} seeds × {PG_TOP_K:,} hits × ~{per_row} bytes)",
                        limit_mb,
                    )
        literals = ["[" + ",".join(repr(float(x)) for x in v) + "]" for v in vectors]
        per_seed: list[list[tuple]] = [[] for _ in literals]
        with conn.cursor(name="hunches_pairs") as cur:
            cur.itersize = PG_BATCH
            cur.execute(step1, (literals, floor, PG_TOP_K))
            for id_, i, sim in cur:
                count(id_)
                per_seed[i].append((id_, sim))
        ids = list(dict.fromkeys(id_ for rows in per_seed for id_, _ in rows))
        texts = {}
        if ids:
            step2 = sql.SQL(
                "SELECT {id}, {text} FROM {table} WHERE {id} = ANY(%s)"
            ).format(id=id_col, text=text_col, table=table)
            with conn.cursor(name="hunches_texts") as cur:
                cur.itersize = PG_BATCH
                cur.execute(step2, (ids,))
                for id_, text in cur:
                    count(id_, text)
                    texts[id_] = text
        hits = []
        for rows in per_seed:
            rows.sort(key=lambda r: (-r[1], r[0]))
            for id_, _ in rows:
                if id_ not in texts:
                    raise RuntimeError(f"no text row for id {str(id_)!r}")
            hits.append([(str(id_), texts[id_], sim) for id_, sim in rows])
        return hits, any(len(rows) == PG_TOP_K for rows in per_seed)
    except SearchCancelled:
        raise
    except Exception as e:  # noqa: BLE001  the driver's own classes are not imported here
        if stop and stop.stopped:
            raise SearchCancelled from None
        raise RuntimeError(pg_message(e, config)) from None
    finally:
        conn.close()


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
