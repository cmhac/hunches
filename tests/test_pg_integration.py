"""Real-database tests for the pgvector backend (spec 005).

Skipped unless HUNCHES_TEST_PG_URL points at a PostgreSQL with the `vector` extension available
(the role needs CREATE on the database; a few tests also need CREATE DATABASE and skip without it).
Every test makes its own schema (or scratch database) and drops it afterwards; hunches itself
never writes. The `index` tests also need pgvector 0.8.0 or newer. Expected values come from numpy
or are written by hand, never from the code under test.
"""

import json
import os
import threading
import time
import uuid

import numpy as np
import pytest

from hunches import candidates, files, search

psycopg = pytest.importorskip("psycopg")

URL = os.environ.get("HUNCHES_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="HUNCHES_TEST_PG_URL is not set")

D = 16
SEED_TEXTS = [
    "alpha",
    "beta",
    "gamma",
    "alpha again",
]  # the last repeats the first vector


def lit(vector) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def version_of(conn) -> tuple[int, ...]:
    row = conn.execute(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()
    return tuple(int(p) for p in row[0].split(".")[:3])


@pytest.fixture(scope="module")
def admin():
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        print(
            "\nserver:",
            conn.execute("SHOW server_version").fetchone()[0],
            "pgvector:",
            ".".join(map(str, version_of(conn))),
        )
        yield conn


@pytest.fixture
def schema(admin):
    name = "hn_" + uuid.uuid4().hex[:10]
    admin.execute(f"CREATE SCHEMA {name}")
    yield name
    admin.execute(f"DROP SCHEMA {name} CASCADE")


@pytest.fixture
def scratch_db(admin):
    """A scratch database (dropped afterwards) as a libpq connection string."""
    name = "hn_" + uuid.uuid4().hex[:10]
    try:
        admin.execute(f"CREATE DATABASE {name}")
    except psycopg.Error as e:
        pytest.skip(f"cannot CREATE DATABASE: {e}")
    try:
        yield name, psycopg.conninfo.make_conninfo(URL, dbname=name)
    finally:
        admin.execute(f"DROP DATABASE {name} WITH (FORCE)")


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HUNCHES_PG_URL", URL or "")

    def use(**fields):
        base = {
            "assistant_model": "anthropic:claude-sonnet-5-5",
            "classifier_model": "anthropic:claude-haiku-4-5",
            "embedding_model": "m",
            "backend": "pgvector",
            **fields,
        }
        files.write_config(files.Config.model_validate(base))
        return files.read_config()

    return use


def corpus(n=300, dim=D):
    """(vectors, seed vectors): clustered, unnormalised, with a tie, two zero vectors and a
    duplicated seed. The generator seed is the first for which no similarity lies within 1e-4 of
    the 0.60 floor, so float32 (numpy) and float4 (pgvector) arithmetic cannot disagree about
    who is in."""
    for rng_seed in range(100):
        out = clustered(n, dim, rng_seed)
        if out:
            return out
    raise AssertionError("no generator seed keeps clear of the floor")


def clustered(n, dim, rng_seed):
    rng = np.random.default_rng(rng_seed)
    seeds = rng.normal(size=(3, dim)).astype(np.float32)
    seeds = np.vstack([seeds, seeds[0]])
    base = seeds[np.arange(n) % 3] + 0.9 * rng.normal(size=(n, dim))
    vectors = (base * rng.uniform(0.5, 3.0, size=(n, 1))).astype(np.float32)
    vectors[n - 1] = vectors[5]  # a tie: two rows with exactly one vector
    vectors = np.vstack([vectors, np.zeros((2, dim), np.float32)])
    unit = vectors / np.maximum(np.linalg.norm(vectors, axis=1), 1e-9)[:, None]
    sims = unit @ (seeds / np.linalg.norm(seeds, axis=1)[:, None]).T
    if np.abs(sims - candidates.FLOOR).min() <= 1e-4:
        return None
    assert 20 < (sims >= candidates.FLOOR).any(axis=1).sum() < n
    return vectors, seeds


def make_table(
    admin,
    schema,
    name,
    vectors,
    *,
    idtype="text",
    vtype="vector",
    index=None,
    partitioned=False,
    ext="",
):
    """Create schema.name(id, text, embedding) holding `vectors`; returns the ids as strings.
    `ext` is the schema prefix of the vector type when the extension is not on search_path."""
    dim = vectors.shape[1]
    vtype = ext + vtype
    ids = []
    for i in range(len(vectors)):
        ids.append(
            {
                "text": f"r{i:05d}",
                "bigint": i + 1,
                "uuid": uuid.UUID(int=i + 1),
            }[idtype]
        )
    by = " PARTITION BY HASH (id)" if partitioned else ""
    admin.execute(
        f"CREATE TABLE {schema}.{name} (id {idtype} PRIMARY KEY, text text, "
        f"embedding {vtype}({dim})){by}"
    )
    if partitioned:
        for r in range(3):
            admin.execute(
                f"CREATE TABLE {schema}.{name}_p{r} PARTITION OF {schema}.{name} "
                f"FOR VALUES WITH (MODULUS 3, REMAINDER {r})"
            )
    with admin.cursor() as cur:
        cur.executemany(
            f"INSERT INTO {schema}.{name} VALUES (%s, %s, %s::{vtype})",
            [
                (id_, f"text of {id_}", None if v is None else lit(v))
                for id_, v in zip(ids, vectors)
            ],
        )
    if index:
        ops = f"{vtype}_cosine_ops"  # the opclass lives in the extension's schema too
        admin.execute(
            f"CREATE INDEX ON {schema}.{name} USING {index} (embedding {ops})"
        )
    admin.execute(f"ANALYZE {schema}.{name}")
    return [str(i) for i in ids]


def local_corpus(tmp_path, ids, vectors):
    folder = tmp_path / "corpus"
    folder.mkdir(exist_ok=True)
    np.save(folder / "vectors.npy", vectors)
    rows = [{"id": i, "text": f"text of {i}"} for i in ids]
    (folder / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (folder / "meta.json").write_text(json.dumps({"embedding_model": "m"}))
    return folder


async def run_candidates(monkeypatch, seeds, config) -> dict[str, dict]:
    """build_candidates for `config`; candidates.jsonl rows by id."""
    files.write_text("seeds.csv", "seed\n" + "\n".join(SEED_TEXTS) + "\n")

    async def embed(_seeds, embedder=None):
        return [[float(x) for x in v] for v in seeds]

    monkeypatch.setattr(candidates, "embed_seeds", embed)
    await candidates.build_candidates()
    text = (files.root() / "candidates.jsonl").read_text()
    return {r["id"]: r for r in map(json.loads, text.splitlines())}


def assert_same(got, want, tol=1e-5, boundary=None):
    """Same ids, same best_seed, same max_similarity within tol. With `boundary` (half
    precision) ids may differ only when the row sits within `boundary` of the floor."""
    if boundary is None:
        assert got.keys() == want.keys()
    else:
        for i in got.keys() ^ want.keys():
            row = got.get(i) or want[i]
            assert abs(row["max_similarity"] - candidates.FLOOR) < boundary
    for i in got.keys() & want.keys():
        assert got[i]["best_seed"] == want[i]["best_seed"], i
        assert got[i]["max_similarity"] == pytest.approx(
            want[i]["max_similarity"], abs=tol
        ), i


async def compare(
    tmp_path, project, monkeypatch, schema, table, ids, vectors, seeds, **kw
):
    folder = local_corpus(tmp_path, ids, vectors)
    local = project(backend="local", corpus_dir=str(folder))
    want = await run_candidates(monkeypatch, seeds, local)
    pg = project(pg_table=f"{schema}.{table}", pg_search="exact")
    got = await run_candidates(monkeypatch, seeds, pg)
    assert len(want) > 20
    # the zero vectors never reach the pool
    assert not [i for i in got if i in (ids[-1], ids[-2])]
    assert_same(got, want, **kw)
    return got


@pytest.mark.parametrize("index", [None, "hnsw"], ids=["no-index", "hnsw"])
async def test_exact_equals_numpy(admin, schema, project, tmp_path, monkeypatch, index):
    vectors, seeds = corpus()
    ids = make_table(admin, schema, "docs", vectors, index=index)
    got = await compare(
        tmp_path, project, monkeypatch, schema, "docs", ids, vectors, seeds
    )
    # the tie: rows 5 and 299 share one vector, hence one similarity and one best seed
    a, b = got[ids[5]], got[ids[299]]
    assert a["max_similarity"] == b["max_similarity"]
    assert a["best_seed"] == b["best_seed"]
    # the duplicated seed (index 3) never beats the seed it repeats (index 0)
    assert "alpha again" not in {r["best_seed"] for r in got.values()}


@pytest.mark.parametrize("nseeds", [1, 4, 12])
async def test_exact_reads_the_table_once_and_uses_no_ann_index(
    admin, schema, project, monkeypatch, nseeds
):
    vectors, _ = corpus()
    make_table(admin, schema, "docs", vectors, index="hnsw")
    project(pg_table=f"{schema}.docs")
    seeds = np.random.default_rng(3).normal(size=(nseeds, D))
    recorded = []

    class Recording(psycopg.ServerCursor):
        def execute(self, query, params=None, **kw):
            recorded.append((query, params))
            return super().execute(query, params, **kw)

    connect = psycopg.connect

    def recording_connect(*args, **kw):
        conn = connect(*args, **kw)
        conn.server_cursor_factory = Recording
        return conn

    monkeypatch.setattr(psycopg, "connect", recording_connect)
    search.search_pg_exact(seeds, -1.0)
    step1, params = next((q, p) for q, p in recorded if "ranked" in q.as_string(None))
    plan = admin.execute(
        psycopg.sql.SQL("EXPLAIN (ANALYZE, FORMAT JSON) ") + step1, params
    ).fetchone()[0][0]["Plan"]
    nodes = []

    def walk(node):
        nodes.append(node)
        for child in node.get("Plans", []):
            walk(child)

    walk(plan)
    scans = [n for n in nodes if n.get("Relation Name") == "docs"]
    assert [(n["Node Type"], n["Actual Loops"]) for n in scans] == [("Seq Scan", 1)]
    assert not [n for n in nodes if "Index" in n["Node Type"]]


async def test_halfvec(admin, schema, project, tmp_path, monkeypatch):
    vectors, seeds = corpus()
    ids = make_table(admin, schema, "docs", vectors, vtype="halfvec", index="hnsw")
    # half precision: similarities within 3e-3, a row near the floor may fall either side
    await compare(
        tmp_path,
        project,
        monkeypatch,
        schema,
        "docs",
        ids,
        vectors,
        seeds,
        tol=3e-3,
        boundary=3e-3,
    )


@pytest.mark.parametrize("idtype", ["bigint", "uuid"])
async def test_integer_and_uuid_ids(
    admin, schema, project, tmp_path, monkeypatch, idtype
):
    vectors, seeds = corpus()
    ids = make_table(admin, schema, "docs", vectors, idtype=idtype)
    await compare(tmp_path, project, monkeypatch, schema, "docs", ids, vectors, seeds)


async def test_partitioned_table(admin, schema, project, tmp_path, monkeypatch):
    vectors, seeds = corpus()
    ids = make_table(admin, schema, "docs", vectors, partitioned=True)
    await compare(tmp_path, project, monkeypatch, schema, "docs", ids, vectors, seeds)
    report = search.check_store(files.read_config())
    assert report["errors"] == {}
    assert (report["type"], report["dimension"]) == ("vector", D)


async def test_view(admin, schema, project, tmp_path, monkeypatch):
    vectors, seeds = corpus()
    ids = make_table(admin, schema, "base", vectors)
    admin.execute(
        f"CREATE VIEW {schema}.docs AS SELECT id, text, embedding FROM {schema}.base"
    )
    await compare(tmp_path, project, monkeypatch, schema, "docs", ids, vectors, seeds)
    report = search.check_store(files.read_config())
    assert report["errors"] == {}
    assert report["sample"] is not None


async def test_extension_in_a_non_default_schema(
    scratch_db, project, tmp_path, monkeypatch
):
    _, conninfo = scratch_db
    monkeypatch.setenv("HUNCHES_PG_URL", conninfo)
    vectors, seeds = corpus()
    with psycopg.connect(conninfo, autocommit=True) as db:
        db.execute("CREATE SCHEMA extensions")
        db.execute("CREATE EXTENSION vector SCHEMA extensions")
        db.execute("CREATE SCHEMA hn")
        # the table's column type is extensions.vector; neither it nor `<=>` is on search_path
        make_table(db, "hn", "docs", vectors, ext="extensions.")
        assert db.execute("SHOW search_path").fetchone()[0] == '"$user", public'
        ids = [r[0] for r in db.execute("SELECT id FROM hn.docs ORDER BY id")]
    await compare(tmp_path, project, monkeypatch, "hn", "docs", ids, vectors, seeds)
    report = search.check_store(files.read_config())
    assert report["schema"] == "extensions"


async def test_very_low_floor_returns_every_pair_and_spills(
    admin, schema, project, monkeypatch
):
    monkeypatch.setattr(search, "PG_TOP_K", 50_000)  # above the 20,000 rows
    rng = np.random.default_rng(5)
    vectors = rng.normal(size=(20_000, D)).astype(np.float32)
    seeds = rng.normal(size=(4, D)).astype(np.float32)
    ids = make_table(admin, schema, "docs", vectors)
    project(pg_table=f"{schema}.docs")
    # a floor below every similarity: all 4 x 20,000 pairs pass
    hits, capped = search.search_pg_exact(seeds, -1.0)
    assert [len(h) for h in hits] == [20_000] * 4 and not capped
    assert {h[0] for h in hits[0]} == set(ids)
    # at the smallest work_mem (64kB) the ranking sort of those pairs goes to disk
    step1 = None
    with admin.transaction():
        admin.execute("SET LOCAL work_mem = '64kB'")
        step1 = admin.execute(
            f"EXPLAIN (ANALYZE, FORMAT JSON) SELECT id, i, sim FROM (SELECT id, i, sim, "
            f"row_number() OVER (PARTITION BY i ORDER BY sim DESC, id) AS rn FROM "
            f"(SELECT t.id, s.i, 1 - (t.embedding <=> s.q) AS sim FROM {schema}.docs t "
            f"CROSS JOIN (SELECT u.i - 1 AS i, u.q::vector AS q FROM "
            f"unnest(%s::text[]) WITH ORDINALITY u(q, i)) s) pairs) ranked "
            f"WHERE rn <= 10000",
            ([lit(s) for s in seeds],),
        ).fetchone()[0][0]["Plan"]
    found = []

    def walk(node):
        if node.get("Node Type") == "Sort":
            found.append((node["Sort Space Type"], node["Sort Space Used"]))
        for child in node.get("Plans", []):
            walk(child)

    walk(step1)
    print("\nlow-floor ranking sort (4 seeds x 20,000 rows, 64kB work_mem):", found)
    assert ("Disk", found[0][1]) in found


async def test_zero_vectors_are_excluded_even_below_a_floor_of_zero(
    admin, schema, project
):
    vectors = np.array([[1, 0], [0, 0], [0, 1], [-1, 0]], np.float32)
    ids = make_table(admin, schema, "docs", vectors, idtype="text")
    project(pg_table=f"{schema}.docs")
    hits, _ = search.search_pg_exact(np.array([[1.0, 0.0]]), -1.0)
    # the zero row has distance NaN; without the guard `1 - NaN >= -1` would let it in
    assert [(i, round(s, 6)) for i, _, s in hits[0]] == [
        (ids[0], 1.0),
        (ids[2], 0.0),
        (ids[3], -1.0),
    ]


def server_version(admin):
    return version_of(admin)


def make_big_table(db, n=100_000, dim=32, rng_seed=9):
    rng = np.random.default_rng(rng_seed)
    vectors = rng.normal(size=(n, dim)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1)[:, None]
    db.execute(
        "CREATE TABLE big (id text PRIMARY KEY, text text, embedding vector(32))"
    )
    with db.cursor() as cur, cur.copy("COPY big FROM STDIN") as copy:
        for i, v in enumerate(vectors):
            copy.write_row((f"r{i:06d}", f"t{i}", lit(v)))
    db.execute("CREATE INDEX ON big USING hnsw (embedding vector_cosine_ops)")
    db.execute("ANALYZE big")
    return vectors, rng.normal(size=dim).astype(np.float32)


def test_index_mode_against_exact(admin, scratch_db, project, monkeypatch):
    """Measures what an HNSW index returns against the truth, with the planner's own choice and
    with it made to use the index. Printed, and compared loosely: the numbers depend on the data
    and the pgvector version."""
    if version_of(admin) < (0, 8, 0):
        pytest.skip("index mode needs pgvector 0.8.0 or newer")
    name, conninfo = scratch_db
    monkeypatch.setenv("HUNCHES_PG_URL", conninfo)
    floor = 0.3
    with psycopg.connect(conninfo, autocommit=True) as db:
        db.execute("CREATE EXTENSION vector")
        vectors, query = make_big_table(db)
    q = query / np.linalg.norm(query)
    true_count = int((vectors @ q >= floor).sum())
    for planner in ("default", "forced-index"):
        if planner == "forced-index":
            # on a table this size the planner prefers a sequential scan, which is complete
            admin.execute(f"ALTER DATABASE {name} SET enable_seqscan = off")
        project(pg_table="big", pg_search="exact")
        exact, _ = search.search_pg_exact(np.array([query]), floor)
        project(pg_table="big", pg_search="index")
        index, _ = search.search(list(query), floor)
        with psycopg.connect(
            conninfo
        ) as db:  # the pgvector defaults: no iterative scan
            raw = db.execute(
                "SELECT id FROM big WHERE 1 - (embedding <=> %s::vector) >= %s "
                "ORDER BY embedding <=> %s::vector LIMIT 10000",
                (lit(query), floor, lit(query)),
            ).fetchall()
        print(
            f"\nindex mode vs exact [{planner} planner], 100,000 x 32 rows, one seed, floor "
            f"{floor}: true hits {true_count}; exact {len(exact[0])}; hunches index mode "
            f"{len(index)}; plain query with pgvector's defaults {len(raw)}"
        )
        assert len(exact[0]) == true_count
        # what index mode returns is a subset of the truth, with the same similarities
        truth = {i: s for i, _, s in exact[0]}
        assert all(
            i in truth and s == pytest.approx(truth[i], abs=1e-6) for i, _, s in index
        )
        assert [s for *_, s in index] == sorted((s for *_, s in index), reverse=True)
        assert {i for (i,) in raw} <= truth.keys()
        if planner == "forced-index":
            assert (
                len(raw) < true_count
            )  # the spec's claim: an index silently hides hits
            assert len(raw) <= len(index) <= true_count


def test_check_store_reports_a_real_table(admin, schema, project):
    vectors, _ = corpus()
    make_table(admin, schema, "plain", vectors)
    make_table(admin, schema, "indexed", vectors, index="hnsw")
    plain = search.check_store(project(pg_table=f"{schema}.plain"))
    assert plain["errors"] == {} and plain["warnings"] == []
    assert plain["indexes"] == []
    assert any(n.startswith("No index:") for n in plain["notes"])
    assert (plain["type"], plain["dimension"]) == ("vector", D)
    assert plain["sample"] == ("r00000", "text of r00000")
    assert plain["version"] == version_of(admin)
    from hunches.screens.pg import report

    shown = report(
        plain
    )  # the screen renders the real result (it once expected a string)
    assert f"pgvector {'.'.join(map(str, version_of(admin)))} in schema" in shown[0]
    indexed = search.check_store(project(pg_table=f"{schema}.indexed"))
    assert [i[1:] for i in indexed["indexes"]] == [("hnsw", "vector_cosine_ops")]
    assert not any(n.startswith("No index:") for n in indexed["notes"])


SLOW_VIEW = (
    "CREATE VIEW {schema}.slow AS SELECT id, text, "
    "CASE WHEN pg_sleep(0.02)::text = 'never' THEN NULL ELSE embedding END AS embedding "
    "FROM {schema}.base"
)


@pytest.fixture
def slow_table(admin, schema, project):
    """~10 s of work: 500 rows, 20 ms of pg_sleep per row."""
    vectors, _ = corpus()
    make_table(admin, schema, "base", vectors[:500])
    admin.execute(SLOW_VIEW.format(schema=schema))
    return f"{schema}.slow"


def test_stop_cancels_the_running_query(admin, slow_table, project):
    project(pg_table=slow_table)
    stop = search.Stop()
    timer = threading.Timer(1.0, stop.stop)
    timer.start()
    started = time.monotonic()
    with pytest.raises(search.SearchCancelled):
        search.search_pg_exact(np.ones((2, D)), 0.0, stop=stop)
    assert time.monotonic() - started < 6
    time.sleep(0.3)
    active = admin.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
        "AND pid <> pg_backend_pid() AND state = 'active'"
    ).fetchone()[0]
    assert active == 0


def test_statement_timeout_gives_the_hint(slow_table, project):
    project(pg_table=slow_table, pg_statement_timeout_s=1)
    with pytest.raises(RuntimeError) as e:
        search.search_pg_exact(np.ones((2, D)), 0.0)
    assert "canceling statement due to statement timeout" in str(e.value)
    assert "Fix: raise statement_timeout for this role" in str(e.value)
    assert os.environ["HUNCHES_PG_URL"] not in str(e.value)
