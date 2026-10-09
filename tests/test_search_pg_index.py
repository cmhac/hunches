import pytest

from hunches import files, keys, search


class Cur:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        sql = query if isinstance(query, str) else query.as_string()
        self.conn.executed.append((sql, params))
        self.rows = self.conn.answers.pop(0)
        if isinstance(self.rows, Exception):
            raise self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Conn:
    """Canned answers, one per execute(): version, type, then SETs and queries."""

    def __init__(self, *answers):
        self.answers, self.executed, self.closed = list(answers), [], False
        self.read_only = True

    def cursor(self, name=None):
        return Cur(self)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HUNCHES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("HUNCHES_PG_URL", raising=False)
    monkeypatch.setattr(keys, "_stored", lambda var: None)


def setup(monkeypatch, conn, **fields):
    files.write_config(
        files.Config.model_validate(
            {
                "assistant_model": "anthropic:claude-sonnet-5-5",
                "classifier_model": "anthropic:claude-haiku-4-5",
                "backend": "pgvector",
                "embedding_model": "m",
                "pg_table": "public.docs",
                "pg_search": "index",
                **fields,
            }
        )
    )
    monkeypatch.setattr(search, "pg_connect", lambda config: conn)


def conn_for(rows, version="0.8.1", typename="vector"):
    return Conn([(version, "extensions")], [(typename, "extensions", 3)], [], [], rows)


def test_old_pgvector_raises_before_any_set(monkeypatch):
    conn = conn_for([], version="0.6.0")
    setup(monkeypatch, conn)
    with pytest.raises(RuntimeError) as e:
        search.search([1.0, 2.0, 3.0], 0.3)
    assert str(e.value) == (
        'pg_search = "index" needs pgvector 0.8.0 or newer (found 0.6.0). '
        'Use pg_search = "exact", or upgrade the extension.'
    )
    assert not any("SET" in s for s, *_ in conn.executed)
    assert conn.closed


def test_sets_come_before_the_query_and_only_those(monkeypatch):
    conn = Conn([("0.8.1", "extensions")], [("vector", "extensions", 3)], [], [], [])
    setup(monkeypatch, conn)
    search.search([1.0, 2.0, 3.0], 0.3)
    stmts = [s for s, *_ in conn.executed]
    assert stmts[2] == "SET LOCAL hnsw.iterative_scan = relaxed_order"
    assert stmts[3] == f"SET LOCAL hnsw.max_scan_tuples = {search.PG_MAX_SCAN}"
    assert stmts[4].startswith("SELECT")
    assert len(stmts) == 5
    assert search.PG_MAX_SCAN == 20_000


def test_one_query_per_seed_with_the_vector_as_text(monkeypatch):
    conns = [
        Conn([("0.8.1", "extensions")], [("vector", "extensions", 3)], [], [], [])
        for _ in range(3)
    ]
    setup(monkeypatch, conns[0])
    it = iter(conns)  # search() opens one connection per call
    monkeypatch.setattr(search, "pg_connect", lambda config: next(it))
    for v in ([1.0, 2.0, 3.0], [0.5, 0.5, 0.5], [-1.0, 0.0, 2.0]):
        search.search(v, 0.3)
    queries = [e for c in conns for e in c.executed if e[0].startswith('SELECT "id"')]
    assert [q[1] for q in queries] == [
        (
            "[1.0,2.0,3.0]",
            "[1.0,2.0,3.0]",
            0.3,
            "[1.0,2.0,3.0]",
            "[1.0,2.0,3.0]",
            search.PG_TOP_K,
        ),
        (
            "[0.5,0.5,0.5]",
            "[0.5,0.5,0.5]",
            0.3,
            "[0.5,0.5,0.5]",
            "[0.5,0.5,0.5]",
            search.PG_TOP_K,
        ),
        (
            "[-1.0,0.0,2.0]",
            "[-1.0,0.0,2.0]",
            0.3,
            "[-1.0,0.0,2.0]",
            "[-1.0,0.0,2.0]",
            search.PG_TOP_K,
        ),
    ]


def test_results_are_resorted_best_first(monkeypatch):
    conn = Conn(
        [("0.8.1", "extensions")],
        [("vector", "extensions", 3)],
        [],
        [],
        [("b", "B", 0.5), ("a", "A", 0.9), ("c", "C", 0.7)],
    )
    setup(monkeypatch, conn)
    hits, capped = search.search([1.0, 2.0, 3.0], 0.3)
    assert hits == [("a", "A", 0.9), ("c", "C", 0.7), ("b", "B", 0.5)]
    assert capped is False


def test_query_shape_floor_nan_schema_and_halfvec(monkeypatch):
    conn = Conn([("0.8.1", "extensions")], [("halfvec", "ext", 3)], [], [], [])
    setup(monkeypatch, conn, pg_table="s.docs", pg_vector_column="emb")
    search.search([1.0, 2.0, 3.0], 0.3)
    sql = conn.executed[4][0]
    assert sql == (
        'SELECT "id", "text", 1 - ("emb" OPERATOR("ext".<=>) %s::"ext"."halfvec") AS sim '
        'FROM "s"."docs" '
        'WHERE 1 - ("emb" OPERATOR("ext".<=>) %s::"ext"."halfvec") >= %s '
        'AND 1 - ("emb" OPERATOR("ext".<=>) %s::"ext"."halfvec") <> \'NaN\' '
        'ORDER BY "emb" OPERATOR("ext".<=>) %s::"ext"."halfvec" LIMIT %s'
    )


def test_capped_when_a_query_returns_exactly_the_cap(monkeypatch):
    monkeypatch.setattr(search, "PG_TOP_K", 2)
    rows = [("a", "A", 0.9), ("b", "B", 0.8)]
    setup(monkeypatch, conn_for(rows))
    assert search.search([1.0, 2.0, 3.0], 0.3)[1] is True
    setup(
        monkeypatch,
        Conn(
            [("0.8.1", "extensions")], [("vector", "extensions", 3)], [], [], rows[:1]
        ),
    )
    assert search.search([1.0, 2.0, 3.0], 0.3)[1] is False


def test_error_is_scrubbed_and_closes(monkeypatch):
    conn = conn_for(RuntimeError("boom"))
    setup(monkeypatch, conn)
    with pytest.raises(RuntimeError, match="boom"):
        search.search([1.0, 2.0, 3.0], 0.3)
    assert conn.closed


def test_exact_through_search_is_an_internal_error(monkeypatch):
    conn = conn_for([])
    setup(monkeypatch, conn, pg_search="exact")
    with pytest.raises(RuntimeError, match="search_pg_exact"):
        search.search([1.0, 2.0, 3.0], 0.3)
    assert conn.executed == []


def test_is_approximate():
    def cfg(**f):
        return files.Config.model_validate(
            {"assistant_model": "a:b", "classifier_model": "a:b", **f}
        )

    assert search.is_approximate(cfg(backend="pgvector", pg_search="index"))
    assert not search.is_approximate(cfg(backend="pgvector", pg_search="exact"))
    assert not search.is_approximate(cfg(backend="pgvector"))
    assert not search.is_approximate(cfg(backend="s3"))
    assert not search.is_approximate(cfg())


def test_two_tables_reads_the_text_in_a_second_query(monkeypatch):
    conn = Conn(
        [("0.8.1", "extensions")],
        [("vector", "extensions", 3)],
        [],
        [],
        [(2, None, 0.5), (1, None, 0.9)],
        [(1, "one"), (2, "two")],
    )
    setup(
        monkeypatch,
        conn,
        pg_id_column="item_id",
        pg_text_table="public.items",
        pg_text_column="body",
    )
    hits, capped = search.search([1.0, 2.0, 3.0], 0.3)
    assert conn.executed[4][0].startswith('SELECT "item_id", NULL, 1 - (')
    assert 'FROM "public"."docs"' in conn.executed[4][0]
    assert conn.executed[5] == (
        'SELECT "item_id", "body" FROM "public"."items" WHERE "item_id" = ANY(%s)',
        ([2, 1],),
    )
    assert hits == [("1", "one", 0.9), ("2", "two", 0.5)]
    assert capped is False


def test_two_tables_missing_text_row_is_an_error(monkeypatch):
    conn = Conn(
        [("0.8.1", "extensions")],
        [("vector", "extensions", 3)],
        [],
        [],
        [(1, None, 0.9)],
        [],
    )
    setup(monkeypatch, conn, pg_text_table="items")
    with pytest.raises(RuntimeError, match="no text row for id '1'"):
        search.search([1.0, 2.0, 3.0], 0.3)
    assert conn.closed


def test_two_tables_no_hits_skips_the_text_query(monkeypatch):
    conn = conn_for([])
    setup(monkeypatch, conn, pg_text_table="items")
    assert search.search([1.0, 2.0, 3.0], 0.3) == ([], False)
    assert len(conn.executed) == 5
