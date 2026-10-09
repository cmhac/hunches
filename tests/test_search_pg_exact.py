import uuid

import pytest

from hunches import files, keys, search

EXT_VERSION = ("0.8.1", "extensions")


class Cur:
    def __init__(self, conn, name):
        self.conn, self.name, self.itersize = conn, name, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        sql = query if isinstance(query, str) else query.as_string()
        self.conn.executed.append((sql, params, self.name, self.itersize))
        self.rows = self.conn.answers.pop(0)
        if isinstance(self.rows, Exception):
            raise self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class Conn:
    """Canned answers, one per execute(): version, column type, step 1, step 2."""

    def __init__(self, *answers):
        self.answers, self.executed, self.closed = list(answers), [], False
        self.read_only = True

    def cursor(self, name=None):
        return Cur(self, name)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
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
                **fields,
            }
        )
    )
    monkeypatch.setattr(search, "pg_connect", lambda config: conn)


def conn_for(step1, step2, typename="vector"):
    return Conn(
        [EXT_VERSION],
        [(typename, "extensions", 3)],
        step1,
        step2,
    )


def test_one_step1_query_for_any_number_of_seeds(monkeypatch):
    for n in (1, 3, 30):
        conn = conn_for([("a", 0, 0.9)], [("a", "A")])
        setup(monkeypatch, conn)
        vectors = [[float(i), 0.5, -1.0] for i in range(n)]
        hits, _ = search.search_pg_exact(vectors, 0.3)
        assert len(hits) == n and hits[0] == [("a", "A", 0.9)]
        step1 = [e for e in conn.executed if "unnest" in e[0]]
        assert len(step1) == 1
        _, params, name, itersize = step1[0]
        assert params[0] == [f"[{float(i)},0.5,-1.0]" for i in range(n)]
        assert params[1] == 0.3
        assert name is not None and itersize == search.PG_BATCH
        step2 = [e for e in conn.executed if "ANY(" in e[0]]
        assert len(step2) == 1 and step2[0][2] is not None
        assert len(conn.executed) == 4  # version, type, step 1, step 2


def test_step1_sql_shape(monkeypatch):
    conn = conn_for([], [], typename="halfvec")
    setup(monkeypatch, conn, pg_table="public.docs", pg_vector_column="emb")
    search.search_pg_exact([[1.0, 2.0, 3.0]], 0.3)
    sql = conn.executed[2][0]
    assert "WITH seeds AS MATERIALIZED" in sql
    assert "unnest(%s::text[]) WITH ORDINALITY" in sql
    assert 'u.q::"extensions"."halfvec"' in sql
    assert 'FROM "public"."docs" t CROSS JOIN LATERAL' in sql
    assert 'OPERATOR("extensions".<=>)' in sql
    assert "FROM seeds s OFFSET 0" in sql or "OFFSET 0" in sql
    assert 't."emb" IS NOT NULL' in sql
    assert "d.sim >= %s" in sql
    assert "d.sim <> 'NaN'" in sql
    assert "row_number() OVER (PARTITION BY i ORDER BY sim DESC, id)" in sql
    assert "rn <= %s" in sql
    assert conn.executed[2][1][2] == search.PG_TOP_K


def test_step2_sql_shape(monkeypatch):
    conn = conn_for([("a", 0, 0.9)], [("a", "text a")])
    setup(
        monkeypatch,
        conn,
        pg_table="docs",
        pg_id_column="doc id",
        pg_text_column="body",
    )
    search.search_pg_exact([[1.0, 2.0, 3.0]], 0.3)
    sql, params, _, _ = conn.executed[3]
    assert sql == 'SELECT "doc id", "body" FROM "docs" WHERE "doc id" = ANY(%s)'
    assert params == (["a"],)


def test_nothing_is_set_on_the_connection(monkeypatch):
    conn = conn_for([("a", 0, 0.9)], [("a", "t")])
    setup(monkeypatch, conn)
    search.search_pg_exact([[1.0, 2.0, 3.0]], 0.3)
    for sql, *_ in conn.executed:
        assert "SET " not in sql.upper().replace("OFFSET", "")
        assert "enable_" not in sql


def test_floor_inclusive_is_a_ge_comparison(monkeypatch):
    # the database does the filtering; a row exactly at the floor is returned as is
    conn = conn_for([("a", 0, 0.3)], [("a", "at the floor")])
    setup(monkeypatch, conn)
    hits, _ = search.search_pg_exact([[1.0, 0.0, 0.0]], 0.3)
    assert hits == [[("a", "at the floor", 0.3)]]
    assert ">= %s" in conn.executed[2][0] and conn.executed[2][1][1] == 0.3


def test_assembles_three_seeds_sorted_with_id_tiebreak(monkeypatch):
    step1 = [  # arrives unordered
        ("b", 1, 0.5),
        ("a", 0, 0.7),
        ("c", 0, 0.9),
        ("b", 0, 0.7),
        ("a", 2, 0.4),
        ("c", 1, 0.5),
        ("a", 1, 0.8),
    ]
    step2 = [("a", "A"), ("b", "B"), ("c", "C")]
    conn = conn_for(step1, step2)
    setup(monkeypatch, conn)
    hits, capped = search.search_pg_exact([[1.0, 0, 0]] * 3, 0.3)
    assert hits == [
        [("c", "C", 0.9), ("a", "A", 0.7), ("b", "B", 0.7)],
        [("a", "A", 0.8), ("b", "B", 0.5), ("c", "C", 0.5)],
        [("a", "A", 0.4)],
    ]
    assert capped is False
    assert sorted(conn.executed[3][1][0]) == ["a", "b", "c"]  # distinct ids


def test_capped_only_when_a_seed_reaches_the_cap(monkeypatch):
    monkeypatch.setattr(search, "PG_TOP_K", 2)
    rows = [("a", 0, 0.9), ("b", 0, 0.8), ("c", 1, 0.7)]
    texts = [("a", "A"), ("b", "B"), ("c", "C")]
    conn = conn_for(rows, texts)
    setup(monkeypatch, conn)
    _, capped = search.search_pg_exact([[1.0, 0, 0]] * 2, 0.3)
    assert capped is True
    assert conn.executed[2][1][2] == 2

    conn = conn_for(rows[:1] + rows[2:], [texts[0], texts[2]])
    setup(monkeypatch, conn)
    _, capped = search.search_pg_exact([[1.0, 0, 0]] * 2, 0.3)
    assert capped is False


def test_integer_ids_reach_step2_unconverted(monkeypatch):
    conn = conn_for([(7, 0, 0.9), (12, 0, 0.8)], [(12, "twelve"), (7, "seven")])
    setup(monkeypatch, conn)
    hits, _ = search.search_pg_exact([[1.0, 0, 0]], 0.3)
    assert sorted(conn.executed[3][1][0]) == [7, 12]
    assert all(type(i) is int for i in conn.executed[3][1][0])
    assert hits == [[("7", "seven", 0.9), ("12", "twelve", 0.8)]]


def test_uuid_ids_reach_step2_unconverted(monkeypatch):
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    conn = conn_for([(u, 0, 0.9)], [(u, "doc")])
    setup(monkeypatch, conn)
    hits, _ = search.search_pg_exact([[1.0, 0, 0]], 0.3)
    assert conn.executed[3][1][0] == [u]
    assert hits == [[("12345678-1234-5678-1234-567812345678", "doc", 0.9)]]


def test_missing_text_row_is_an_error(monkeypatch):
    conn = conn_for([("a", 0, 0.9), ("b", 0, 0.8)], [("a", "A")])
    setup(monkeypatch, conn)
    with pytest.raises(RuntimeError, match="no text row for id 'b'"):
        search.search_pg_exact([[1.0, 0, 0]], 0.3)
    assert conn.closed


def test_connection_closed_on_success_and_never_written(monkeypatch):
    conn = conn_for([], [])
    setup(monkeypatch, conn)
    search.search_pg_exact([[1.0, 0, 0]], 0.3)
    assert conn.closed and conn.read_only


def test_error_closes_the_connection_and_is_scrubbed(monkeypatch):
    monkeypatch.setenv("HUNCHES_PG_URL", "postgresql://u:hunter2@h/db")
    conn = Conn(
        [EXT_VERSION],
        [("vector", "extensions", 3)],
        Exception("canceling statement due to statement timeout hunter2"),
    )
    setup(monkeypatch, conn)
    with pytest.raises(RuntimeError) as e:
        search.search_pg_exact([[1.0, 0, 0]], 0.3)
    assert "hunter2" not in str(e.value)
    assert "Fix: raise statement_timeout" in str(e.value)
    assert conn.closed
    assert len(conn.executed) == 3  # nothing runs after the failed statement


def test_unsupported_column_type_refused_before_the_scan(monkeypatch):
    conn = Conn([EXT_VERSION], [("sparsevec", "extensions", 3)])
    setup(monkeypatch, conn)
    with pytest.raises(RuntimeError, match="has type sparsevec"):
        search.search_pg_exact([[1.0, 0, 0]], 0.3)
    assert conn.closed and len(conn.executed) == 2
