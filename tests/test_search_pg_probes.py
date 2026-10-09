import pytest

from hunches import search


class Cur:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        self.rows = self.conn.answers.pop(0)
        if isinstance(self.rows, Exception):
            raise self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Conn:
    """Canned catalog rows, one answer per execute()."""

    def __init__(self, *answers):
        self.answers, self.executed = list(answers), []

    def cursor(self):
        return Cur(self)


@pytest.mark.parametrize(
    "found, parsed",
    [
        ("0.8.1", (0, 8, 1)),
        ("0.6.0", (0, 6, 0)),
        ("0.8.0rc1", (0, 8, 0)),
        ("0.7", (0, 7, 0)),
        ("1.10.2-beta", (1, 10, 2)),
    ],
)
def test_extension_version_parsing(found, parsed):
    conn = Conn([(found, "extensions")])
    assert search.extension_version(conn) == (parsed, "extensions")
    sql = conn.executed[0][0]
    assert "pg_extension" in sql and "extname = 'vector'" in sql
    assert "count(" not in sql.lower()


def test_extension_absent():
    with pytest.raises(RuntimeError) as e:
        search.extension_version(Conn([]))
    assert str(e.value) == (
        "The vector extension is not installed in this database "
        "(CREATE EXTENSION vector needs a DBA)."
    )


def test_index_mode_needs_080():
    with pytest.raises(RuntimeError) as e:
        search.require_index_mode_version((0, 6, 0), "index")
    assert str(e.value) == (
        'pg_search = "index" needs pgvector 0.8.0 or newer (found 0.6.0). '
        'Use pg_search = "exact", or upgrade the extension.'
    )
    search.require_index_mode_version((0, 7, 9), "exact")  # no check
    search.require_index_mode_version((0, 8, 0), "index")
    search.require_index_mode_version((1, 0, 0), "index")
    with pytest.raises(RuntimeError):
        search.require_index_mode_version((0, 7, 9), "index")


@pytest.mark.parametrize(
    "typename, dim", [("vector", 3), ("halfvec", 3072), ("vector", None)]
)
def test_column_type_accepted(typename, dim):
    conn = Conn([(typename, "extensions", dim if dim is not None else -1)])
    got = search.column_type(conn, "s.docs", "embedding")
    assert got == (typename, "extensions", dim)


def test_column_type_sparsevec_refused():
    with pytest.raises(RuntimeError) as e:
        search.column_type(Conn([("sparsevec", "extensions", 3)]), "t", "embedding")
    assert str(e.value) == (
        'Column "embedding" has type sparsevec; hunches supports vector and halfvec.'
    )


def test_column_missing():
    with pytest.raises(RuntimeError) as e:
        search.column_type(Conn([]), "s.docs", "nope")
    assert str(e.value) == 'column "nope" of relation "s.docs" does not exist'


def test_missing_table_text_passes_through():
    boom = ValueError('relation "nope.x" does not exist')
    with pytest.raises(ValueError, match='relation "nope.x" does not exist'):
        search.column_type(Conn(boom), "nope.x", "embedding")


@pytest.mark.parametrize(
    "table, quoted",
    [
        ("docs", '"docs"'),
        ("s.docs", '"s"."docs"'),
        ('we"ird', '"we""ird"'),
        ('a"b.c"d', '"a""b"."c""d"'),
    ],
)
def test_table_names_are_quoted_parameters(table, quoted):
    conn = Conn([("vector", "public", 3)])
    search.column_type(conn, table, "embedding")
    sql, params = conn.executed[0]
    assert params == (quoted, "embedding")
    assert "::regclass" in sql and "%s" in sql


def test_hostile_names_never_reach_the_sql_text():
    bad = 'x"; DROP TABLE t'
    conn = Conn([("vector", "public", 3)], [(10.0,)], [(5,)])
    search.column_type(conn, bad, bad)
    search.table_estimates(conn, bad, bad)
    for sql, params in conn.executed:
        assert "DROP" not in sql
        assert any("DROP" in p for p in params)


def test_table_estimates():
    conn = Conn([(1234.0,)], [(101,)])
    assert search.table_estimates(conn, "s.docs", "text") == (1234, 101)
    (sql1, p1), (sql2, p2) = conn.executed
    assert "reltuples" in sql1 and "count(" not in sql1.lower()
    assert p1 == ('"s"."docs"',)
    assert "pg_stats" in sql2 and "avg_width" in sql2
    assert p2 == ('"s"."docs"', "text")


def test_table_estimates_without_statistics():
    # never analysed: reltuples = -1 and no pg_stats row
    assert search.table_estimates(Conn([(-1.0,)], []), "t", "text") == (None, None)
    # rows known, width not
    assert search.table_estimates(Conn([(7.0,)], []), "t", "text") == (7, None)
