import pytest

from hunches import keys, search
from hunches.files import Config

MODELS = {
    "backend": "pgvector",
    "embedding_model": "m",
    "assistant_model": "a:b",
    "classifier_model": "a:b",
}
URL = "postgresql://alice:s3cr%40t@db.example.com:5432/mydb"


class Cur:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        sql = query if isinstance(query, str) else query.as_string()
        self.conn.executed.append(sql)
        for needle, answer in self.conn.answers.items():
            if needle in sql:
                break
        else:
            raise AssertionError(f"unexpected SQL: {sql}")
        if isinstance(answer, Exception):
            raise answer
        self.rows = answer

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Savepoint:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.savepoints += 1
        return self

    def __exit__(self, *a):
        return False


class Conn:
    """Canned rows keyed by a fragment of the SQL they answer."""

    def __init__(self, **overrides):
        self.answers = {
            "pg_extension": [("0.8.1", "extensions")],
            "pg_stat_ssl": [(True,)],
            "atttypmod": [("vector", "extensions", 3)],
            "reltuples": [(1234.0,)],
            "pg_stats": [(60,)],
            "pg_index": [("docs_cos", "hnsw", "vector_cosine_ops")],
            "left(": [("a1", "The first sixty characters of the text")],
        }
        self.answers.update(overrides)
        self.executed, self.savepoints, self.closed = [], 0, False

    def cursor(self):
        return Cur(self)

    def transaction(self):
        return Savepoint(self)

    def close(self):
        self.closed = True


@pytest.fixture
def check(monkeypatch):
    monkeypatch.setattr(keys, "_stored", lambda var: None)
    monkeypatch.setenv("HUNCHES_PG_URL", URL)

    def run(conn, seeds=None, **config):
        config = Config.model_validate({**MODELS, "pg_table": "public.docs", **config})
        monkeypatch.setattr(search, "pg_connect", lambda c: conn)
        return search.check_store(config, seeds)

    return run


def test_full_report_exact_with_cosine_index(check):
    conn = Conn()
    got = check(conn)
    assert got["version"] == (0, 8, 1)
    assert got["schema"] == "extensions"
    assert got["encrypted"] is True
    assert (got["type"], got["dimension"]) == ("vector", 3)
    assert got["rows"] == 1234
    assert got["indexes"] == [("docs_cos", "hnsw", "vector_cosine_ops")]
    assert got["sample"] == ("a1", "The first sixty characters of the text")
    assert got["warnings"] == [] and got["notes"] == [] and got["errors"] == {}
    assert conn.closed


def test_no_count_and_only_selects(check):
    conn = Conn()
    check(conn, seeds=5)
    assert conn.executed
    for sql in conn.executed:
        assert "count(" not in sql.lower()
        assert sql.lstrip().upper().startswith("SELECT")


def test_sample_query_maps_the_configured_columns(check):
    conn = Conn()
    check(conn, pg_id_column="doc", pg_text_column="body")
    sample = next(s for s in conn.executed if "left(" in s)
    assert sample == 'SELECT "doc", left("body", 60) FROM "public"."docs" LIMIT 1'


@pytest.mark.parametrize(
    "row, expected",
    [([(True,)], True), ([(False,)], False), ([], None)],
)
def test_encryption(check, row, expected):
    assert check(Conn(pg_stat_ssl=row))["encrypted"] is expected


def test_halfvec_dimension(check):
    conn = Conn(
        atttypmod=[("halfvec", "extensions", 3072)],
        pg_index=[("h", "hnsw", "halfvec_cosine_ops")],
    )
    got = check(conn, pg_search="index")
    assert (got["type"], got["dimension"]) == ("halfvec", 3072)
    assert got["warnings"] == []  # halfvec_cosine_ops is the cosine class of halfvec


def test_sparsevec_warns_and_other_pieces_still_report(check):
    got = check(Conn(atttypmod=[("sparsevec", "extensions", 3)]))
    assert got["warnings"] == [
        'Column "embedding" has type sparsevec; hunches supports vector and halfvec.'
    ]
    assert got["type"] is None and got["errors"] == {}
    assert got["rows"] == 1234 and got["sample"] is not None


def test_missing_column_is_an_error_not_a_warning(check):
    got = check(Conn(atttypmod=[]))
    assert got["errors"] == {
        "column": 'column "embedding" of relation "public.docs" does not exist'
    }
    assert got["warnings"] == []


@pytest.mark.parametrize("mode", ["exact", "index"])
def test_cosine_index_present_has_no_warning(check, mode):
    assert check(Conn(), pg_search=mode)["warnings"] == []


def test_index_mode_without_cosine_index_warns(check):
    conn = Conn(pg_index=[("docs_l2", "hnsw", "vector_l2_ops")])
    got = check(conn, pg_search="index")
    assert got["warnings"] == [
        (
            'pg_search = "index" but no index on "embedding" uses vector_cosine_ops; '
            "the search orders by <=> (cosine), so Postgres would not use it."
        )
    ]
    assert got["indexes"] == [("docs_l2", "hnsw", "vector_l2_ops")]


def test_index_mode_without_any_index_warns(check):
    got = check(Conn(pg_index=[]), pg_search="index")
    assert len(got["warnings"]) == 1 and "vector_cosine_ops" in got["warnings"][0]
    assert got["notes"] == []


def test_exact_mode_without_index_is_a_note_not_a_warning(check):
    got = check(Conn(pg_index=[]))
    assert got["notes"] == ["No index: the search scans the whole table (~1234 rows)."]
    assert got["warnings"] == []


def test_exact_mode_with_only_a_non_cosine_index_says_nothing(check):
    got = check(Conn(pg_index=[("docs_l2", "hnsw", "vector_l2_ops")]))
    assert got["notes"] == [] and got["warnings"] == []


@pytest.mark.parametrize("reltuples", [-1.0, -1])
def test_unknown_row_estimate_is_none_and_shown_as_question_mark(check, reltuples):
    got = check(Conn(reltuples=[(reltuples,)], pg_index=[]), seeds=4)
    assert got["rows"] is None
    assert got["notes"][0] == "No index: the search scans the whole table (~? rows)."
    assert got["notes"][1].startswith("Worst case ? pairs (4 seeds x ? rows).")


def test_worst_case_pairs_note(check):
    got = check(Conn(), seeds=10)
    assert got["notes"] == [
        (
            "Worst case 12,340 pairs (10 seeds x 1,234 rows). A low floor on a large "
            "table sorts up to this many pairs on the server (spills to temporary "
            "files). Ask your DBA about temp_file_limit."
        )
    ]


def test_no_pair_note_without_seeds(check):
    assert check(Conn())["notes"] == []


def test_index_mode_on_old_pgvector_reports_the_version_message(check):
    got = check(Conn(pg_extension=[("0.6.0", "public")]), pg_search="index")
    assert got["version"] == (0, 6, 0)
    assert got["warnings"][0] == (
        'pg_search = "index" needs pgvector 0.8.0 or newer (found 0.6.0). '
        'Use pg_search = "exact", or upgrade the extension.'
    )


def test_exact_mode_on_old_pgvector_has_no_version_warning(check):
    assert check(Conn(pg_extension=[("0.6.0", "public")]))["warnings"] == []


def test_pooler_hint_for_port_6543(check, monkeypatch):
    monkeypatch.setenv("HUNCHES_PG_URL", "postgresql://u:p@db.example.com:6543/x")
    got = check(Conn())
    assert got["notes"] == [search.POOLER_HINT]
    assert "direct or session-mode URL" in search.POOLER_HINT


def test_pooler_hint_for_pooler_host(check, monkeypatch):
    monkeypatch.setenv("HUNCHES_PG_URL", "postgresql://u:p@aws-0.pooler.supabase.com/x")
    assert check(Conn())["notes"] == [search.POOLER_HINT]


def test_no_pooler_hint_for_a_plain_url(check):
    assert search.POOLER_HINT not in check(Conn())["notes"]


def test_each_piece_reports_its_own_scrubbed_error(check):
    boom = RuntimeError(f"could not read {URL} (password s3cr@t)")
    conn = Conn(**{"left(": boom, "pg_index": boom})
    got = check(conn)
    assert got["errors"] == {
        "indexes": "could not read *** (password ***)",
        "sample": "could not read *** (password ***)",
    }
    assert got["version"] == (0, 8, 1) and got["rows"] == 1234
    assert got["sample"] is None and got["indexes"] == []
    assert conn.savepoints == 6  # every piece runs in its own savepoint


def test_connection_failure_is_the_only_report(monkeypatch):
    def refuse(config):
        raise RuntimeError("connection refused ***")

    monkeypatch.setattr(search, "pg_connect", refuse)
    got = search.check_store(Config.model_validate({**MODELS, "pg_table": "t"}), 3)
    assert got["errors"] == {"connect": "connection refused ***"}
    assert got["version"] is None and got["warnings"] == []
