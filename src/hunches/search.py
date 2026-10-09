import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import numpy as np

from hunches import keys, system
from hunches.files import PG_DEFAULTS, Config, pg_setting, read_config

# Max results per QueryVectors request: 10,000 (100 per page, followed via nextToken).
# Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html
S3_TOP_K = 10_000
PG_TOP_K = 10_000
# hnsw.max_scan_tuples for index mode: the pgvector default (20,000; README, "Iterative Scan
# Options"), set explicitly so the result does not depend on the server's configuration.
# Raising it alone did not help (specs/005-pgvector/spec.md, "Verified in task 06").
PG_MAX_SCAN = 20_000
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


def pg_url_id(url: str) -> str:
    """16 hex characters naming a database URL: a hash of host, port, database and user.

    The password is left out, so the id (written to config.toml) reveals nothing secret and
    survives a password change; the same database and user always get the same id."""
    try:
        from psycopg.conninfo import conninfo_to_dict

        parts = conninfo_to_dict(url)
    except ImportError as e:
        raise ImportError(
            "The pgvector backend needs psycopg: pip install hunches[pg]"
        ) from e
    except Exception:  # noqa: BLE001  the driver's text could quote the password
        raise ValueError(
            "not a PostgreSQL URL (postgresql://user:password@host:port/database)"
        ) from None
    if not parts.get("host"):
        raise ValueError("the URL has no host")
    user = str(parts.get("user") or "")
    where = [
        str(parts["host"]).lower(),
        str(parts.get("port") or 5432),
        str(parts.get("dbname") or user),  # libpq's default database is the user name
        user,
    ]
    return hashlib.sha256(json.dumps(where).encode()).hexdigest()[:16]


def pg_url_name(url_id: str | None, url_var: str | None) -> str:
    """The environment variable / keyring entry holding the URL: an explicit pg_url_var,
    else one per pg_url_id, else the default HUNCHES_PG_URL."""
    if url_var:
        return url_var
    if url_id:
        return f"HUNCHES_PG_URL_{url_id.upper()}"
    return PG_DEFAULTS["pg_url_var"]


def _url_name(config: Config) -> str:
    return pg_url_name(config.pg_url_id, config.pg_url_var)


def pg_message(e: Exception, config: Config, token: str | None = None) -> str:
    """An exception's text with the URL, password and IAM token replaced by ***, plus a hint."""
    text = str(e)
    url = keys.resolve(_url_name(config)) or ""
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
    var = _url_name(config)
    url = keys.resolve(var)
    if not url and config.pg_url_id and not config.pg_url_var:
        raise ValueError(
            "The database URL is not saved on this computer: paste it in Project "
            f"settings (F3), or set {var} in the environment"
        )
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


def text_source(config: Config) -> tuple[str, str]:
    """(table, id column) the text is read from: pg_text_table in the two-table layout."""
    id_column = pg_setting(config, "pg_id_column")
    if config.pg_text_table:
        return config.pg_text_table, config.pg_text_id_column or id_column
    return config.pg_table or "", id_column


def _texts_query(config: Config):
    """SELECT id, text for a list of ids (the one parameter), from the text table."""
    from psycopg import sql

    table, id_column = text_source(config)
    return sql.SQL("SELECT {id}, {text} FROM {table} WHERE {id} = ANY(%s)").format(
        id=sql.Identifier(id_column),
        text=sql.Identifier(pg_setting(config, "pg_text_column")),
        table=sql.Identifier(*table.split(".", 1)),
    )


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
                conn, text_source(config)[0], pg_setting(config, "pg_text_column")
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
            with conn.cursor(name="hunches_texts") as cur:
                cur.itersize = PG_BATCH
                cur.execute(_texts_query(config), (ids,))
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


def is_approximate(config: Config) -> bool:
    """True when the pgvector search may hide hits above the floor (index mode)."""
    return config.backend == "pgvector" and pg_setting(config, "pg_search") == "index"


def _search_pg_index(
    config: Config, query_vector: list[float], floor: float
) -> tuple[list[tuple[str, str, float]], bool]:
    """One ANN-index query for one seed; the caller (search) has checked the mode."""
    conn = pg_connect(config)
    try:
        from psycopg import sql

        version, _ = extension_version(conn)
        require_index_mode_version(version, "index")  # before any SET
        table_name = config.pg_table or ""  # pg_connect has checked it
        vec_name = pg_setting(config, "pg_vector_column")
        typename, type_schema, _ = column_type(conn, table_name, vec_name)
        dist = sql.SQL("1 - ({vec} OPERATOR({schema}.<=>) %s::{vtype})").format(
            vec=sql.Identifier(vec_name),
            schema=sql.Identifier(type_schema),
            vtype=sql.Identifier(type_schema, typename),
        )
        two_tables = bool(config.pg_text_table)
        query = sql.SQL(
            "SELECT {id}, {text}, {dist} AS sim FROM {table} "
            "WHERE {dist} >= %s AND {dist} <> 'NaN' "
            "ORDER BY {vec} OPERATOR({schema}.<=>) %s::{vtype} LIMIT %s"
        ).format(
            id=sql.Identifier(pg_setting(config, "pg_id_column")),
            # two tables: the text comes from a second query, as in exact step 2
            text=sql.SQL("NULL")
            if two_tables
            else sql.Identifier(pg_setting(config, "pg_text_column")),
            dist=dist,
            table=sql.Identifier(*table_name.split(".", 1)),
            vec=sql.Identifier(vec_name),
            schema=sql.Identifier(type_schema),
            vtype=sql.Identifier(type_schema, typename),
        )
        literal = "[" + ",".join(repr(float(x)) for x in query_vector) + "]"
        with conn.cursor() as cur:
            cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            cur.execute(f"SET LOCAL hnsw.max_scan_tuples = {int(PG_MAX_SCAN)}")
            cur.execute(query, (literal, literal, floor, literal, literal, PG_TOP_K))
            rows = cur.fetchall()
            if two_tables and rows:
                cur.execute(_texts_query(config), ([r[0] for r in rows],))
                texts = dict(cur.fetchall())
                missing = [r[0] for r in rows if r[0] not in texts]
                if missing:
                    raise RuntimeError(f"no text row for id {str(missing[0])!r}")
                rows = [(i, texts[i], sim) for i, _, sim in rows]
        # relaxed order: the index may return rows slightly out of order
        hits = sorted(
            ((str(i), t, float(sim)) for i, t, sim in rows), key=lambda h: -h[2]
        )
        return hits, len(rows) == PG_TOP_K
    except Exception as e:  # noqa: BLE001  the driver's own classes are not imported here
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

    if config.backend == "pgvector":
        if pg_setting(config, "pg_search") != "index":
            raise RuntimeError(
                "search() runs pg_search = 'index' only; exact search is search_pg_exact"
            )
        return _search_pg_index(config, query_vector, floor)

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


POOLER_HINT = (
    "The URL looks like a transaction pooler (port 6543 or a pooler. host). Long "
    "searches can be cut off there; consider the direct or session-mode URL."
)


def check_store(config: Config, seeds: int | None = None) -> dict:
    """Read-only report on the configured table for Check store; does not raise.

    Each piece runs in its own savepoint, so a failing query (its scrubbed text goes in
    "errors" under the piece's name) does not hide the others. No count(*)."""
    from psycopg import sql

    out: dict = {
        "version": None,
        "schema": None,
        "encrypted": None,
        "type": None,
        "dimension": None,
        "rows": None,
        "indexes": [],
        "sample": None,
        "warnings": [],
        "notes": [],
        "errors": {},
    }
    try:
        conn = pg_connect(config)
    except Exception as e:  # noqa: BLE001  pg_connect has already scrubbed the text
        out["errors"]["connect"] = str(e)
        return out
    table = config.pg_table or ""
    column = pg_setting(config, "pg_vector_column")
    text_column = pg_setting(config, "pg_text_column")
    mode = pg_setting(config, "pg_search")
    parts = urlsplit(keys.resolve(_url_name(config)) or "")
    if parts.port == 6543 or "pooler." in (parts.hostname or ""):
        out["notes"].append(POOLER_HINT)

    def version():
        out["version"], out["schema"] = extension_version(conn)
        try:
            require_index_mode_version(out["version"], mode)
        except RuntimeError as e:
            out["warnings"].append(str(e))

    def encryption():
        with conn.cursor() as cur:
            cur.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
            row = cur.fetchone()
        out["encrypted"] = bool(row[0]) if row else None

    def vector_column():
        try:
            out["type"], _, out["dimension"] = column_type(conn, table, column)
        except RuntimeError as e:
            if not str(e).startswith(
                "Column "
            ):  # an unsupported type; else it is missing
                raise
            out["warnings"].append(str(e))

    def estimates():
        out["rows"] = table_estimates(conn, table, text_column)[0]

    def indexes():
        with conn.cursor() as cur:
            # indkey and indclass are parallel arrays; an expression index has attnum 0,
            # never matches the column, and so is not listed
            cur.execute(
                "SELECT i.relname, am.amname, oc.opcname FROM pg_index x "
                "JOIN pg_class i ON i.oid = x.indexrelid "
                "JOIN pg_am am ON am.oid = i.relam "
                "JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attname = %s "
                "AND NOT a.attisdropped "
                "CROSS JOIN LATERAL unnest(x.indkey::int2[], x.indclass::oid[]) "
                "AS k(attnum, opc) JOIN pg_opclass oc ON oc.oid = k.opc "
                "WHERE x.indrelid = %s::regclass AND k.attnum = a.attnum "
                "ORDER BY i.relname",
                (column, _regclass(table)),
            )
            out["indexes"] = [tuple(r) for r in cur.fetchall()]

    def sample():
        id_column = sql.Identifier(pg_setting(config, "pg_id_column"))
        vectors = sql.Identifier(*table.split(".", 1))
        if config.pg_text_table:
            # one joined row proves both tables, all four columns and comparable id types
            text_table, text_id = text_source(config)
            query = sql.SQL(
                "SELECT v.{}, left(t.{}, 60) FROM {} v JOIN {} t ON t.{} = v.{} LIMIT 1"
            ).format(
                id_column,
                sql.Identifier(text_column),
                vectors,
                sql.Identifier(*text_table.split(".", 1)),
                sql.Identifier(text_id),
                id_column,
            )
        else:
            query = sql.SQL("SELECT {}, left({}, 60) FROM {} LIMIT 1").format(
                id_column, sql.Identifier(text_column), vectors
            )
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()
        out["sample"] = (row[0], row[1] or "") if row else None

    try:
        for name, fn in [
            ("version", version),
            ("encryption", encryption),
            ("column", vector_column),
            ("estimates", estimates),
            ("indexes", indexes),
            ("sample", sample),
        ]:
            try:
                with conn.transaction():
                    fn()
            except Exception as e:  # noqa: BLE001  whatever the driver raises
                out["errors"][name] = pg_message(e, config)
    finally:
        conn.close()

    if config.pg_text_table and out["sample"] is None and "sample" not in out["errors"]:
        out["warnings"].append(
            "No row of the table has a matching row in the text table: check the "
            "id col and text id col."
        )
    rows = "?" if out["rows"] is None else out["rows"]
    if "indexes" not in out["errors"]:
        cosine = f"{out['type'] or 'vector'}_cosine_ops"  # halfvec has its own class
        if mode == "index" and not any(i[2] == cosine for i in out["indexes"]):
            out["warnings"].append(
                f'pg_search = "index" but no index on "{column}" uses {cosine}; '
                "the search orders by <=> (cosine), so Postgres would not use it."
            )
        if mode == "exact" and not out["indexes"]:
            out["notes"].append(
                f"No index: the search scans the whole table (~{rows} rows)."
            )
    if seeds is not None:
        pairs = "?" if out["rows"] is None else f"{seeds * out['rows']:,}"
        shown = "?" if out["rows"] is None else f"{out['rows']:,}"
        out["notes"].append(
            f"Worst case {pairs} pairs ({seeds} seeds x {shown} rows). A low floor on a "
            "large table sorts up to this many pairs on the server (spills to temporary "
            "files). Ask your DBA about temp_file_limit."
        )
    return out
