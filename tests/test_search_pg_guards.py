import threading

import pytest

from hunches import files, keys, search, system

EXT_VERSION = ("0.8.1", "extensions")
MB = 1024 * 1024


class Cur:
    def __init__(self, conn, name):
        self.conn, self.name, self.itersize = conn, name, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        sql = query if isinstance(query, str) else query.as_string()
        self.conn.executed.append(sql)
        self.rows = self.conn.answers.pop(0)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        for row in self.rows:
            self.conn.consumed += 1
            yield row


class Conn:
    def __init__(self, *answers):
        self.answers, self.executed, self.closed = list(answers), [], False
        self.read_only = True
        self.consumed = 0
        self.cancels = 0
        self.stats = []

    def cursor(self, name=None):
        return Cur(self, name)

    def cancel_safe(self):
        self.cancels += 1

    def close(self):
        self.closed = True


def conn_for(step1, step2, rows=None, width=None):
    """Answers: version, type, the two estimate queries, step 1, step 2."""
    return Conn(
        [EXT_VERSION],
        [("vector", "extensions", 3)],
        [(-1 if rows is None else rows,)],
        [(width,)],
        step1,
        step2,
    )


def setup(monkeypatch, conn, limit_mb=None):
    files.write_config(
        files.Config.model_validate(
            {
                "assistant_model": "anthropic:claude-sonnet-5-5",
                "classifier_model": "anthropic:claude-haiku-4-5",
                "backend": "pgvector",
                "embedding_model": "m",
                "pg_table": "public.docs",
            }
        )
    )
    if limit_mb is not None:
        system.write_system(
            system.System(
                provider="anthropic",
                assistant_model="a",
                classifier_model="c",
                pg_max_result_mb=limit_mb,
            )
        )
    monkeypatch.setattr(search, "pg_connect", lambda config: conn)


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HUNCHES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("HUNCHES_PG_URL", raising=False)
    monkeypatch.setattr(keys, "_stored", lambda var: None)


def scans(conn):
    return [s for s in conn.executed if "unnest" in s or "ANY(" in s]


def test_preflight_refuses_before_any_scan(monkeypatch):
    # 30 seeds x 10,000 hits x (2048 + 128) bytes = 652,800,000 bytes = 622.56 MiB
    conn = conn_for([], [], rows=1000, width=2048)
    setup(monkeypatch, conn)
    with pytest.raises(RuntimeError) as e:
        search.search_pg_exact([[1.0, 0, 0]] * 30, 0.3)
    assert str(e.value) == (
        "Search could return up to ~623 MB (30 seeds × 10,000 hits × ~2176 bytes) "
        "which exceeds the result limit of 512 MB. Use fewer seeds or raise the limit "
        "in System settings (F5)."
    )
    assert scans(conn) == [] and len(conn.executed) == 4
    assert conn.closed and conn.cancels == 0


def test_preflight_passes_when_the_worst_case_fits(monkeypatch):
    # 10 seeds x 10,000 x 2176 = 217,600,000 bytes = 207.5 MiB
    conn = conn_for([], [], rows=1000, width=2048)
    setup(monkeypatch, conn)
    search.search_pg_exact([[1.0, 0, 0]] * 10, 0.3)
    assert len(scans(conn)) == 1


def test_no_statistics_skips_the_preflight(monkeypatch):
    conn = conn_for([], [], rows=None, width=None)
    setup(monkeypatch, conn)
    search.search_pg_exact([[1.0, 0, 0]] * 3000, 0.3)
    assert len(scans(conn)) == 1


def test_zero_limit_skips_the_preflight_and_its_queries(monkeypatch):
    conn = Conn([EXT_VERSION], [("vector", "extensions", 3)], [], [])
    setup(monkeypatch, conn, limit_mb=0)
    search.search_pg_exact([[1.0, 0, 0]] * 3000, 0.3)
    assert len(conn.executed) == 3  # version, type, step 1 (no hits, no step 2)
    assert not any("pg_stats" in s or "reltuples" in s for s in conn.executed)


def test_limit_is_read_from_system_json_each_search(monkeypatch):
    # 1 seed x 10,000 x 2176 = 20.75 MiB: over a 20 MB limit, under 21
    conn = conn_for([], [], rows=1000, width=2048)
    setup(monkeypatch, conn, limit_mb=20)
    with pytest.raises(RuntimeError, match=r"~21 MB .* result limit of 20 MB"):
        search.search_pg_exact([[1.0, 0, 0]], 0.3)
    conn = conn_for([], [], rows=1000, width=2048)
    setup(monkeypatch, conn, limit_mb=21)
    search.search_pg_exact([[1.0, 0, 0]], 0.3)
    assert len(scans(conn)) == 1


def big_ids(n):
    return [(f"{i:03d}" + "x" * 969, 0, 0.5) for i in range(n)]  # 972 chars each


def test_streaming_abort_in_step_1(monkeypatch):
    # each row counts 972 + 128 = 1,100 bytes; the 953rd row brings the total to
    # 1,048,300 (under 1 MiB = 1,048,576) and the 954th to 1,049,400 (over)
    conn = conn_for(big_ids(2000), [], width=None)
    setup(monkeypatch, conn, limit_mb=1)
    with pytest.raises(RuntimeError) as e:
        search.search_pg_exact([[1.0, 0, 0]], 0.3)
    assert str(e.value) == (
        "Search has already received 1.0 MB (954 rows), which exceeds the result "
        "limit of 1 MB. Use fewer seeds or raise the limit in System settings (F5)."
    )
    assert conn.consumed == 954  # the rest was not read
    assert conn.cancels == 1 and conn.closed


def test_streaming_counts_text_in_step_2(monkeypatch):
    # step 1 row: 1 + 128 = 129 bytes; step 2 row: 1 + 1,048,576 + 128 -> over 1 MiB
    conn = conn_for([("a", 0, 0.5)], [("a", "x" * MB)], width=None)
    setup(monkeypatch, conn, limit_mb=1)
    with pytest.raises(RuntimeError, match=r"\(2 rows\)"):
        search.search_pg_exact([[1.0, 0, 0]], 0.3)
    assert conn.cancels == 1 and conn.closed


def test_zero_limit_never_aborts_the_stream(monkeypatch):
    rows = big_ids(2000)
    conn = Conn(
        [EXT_VERSION], [("vector", "extensions", 3)], rows, [(r[0], "t") for r in rows]
    )
    setup(monkeypatch, conn, limit_mb=0)
    hits, _ = search.search_pg_exact([[1.0, 0, 0]], 0.3)
    assert len(hits[0]) == 2000 and conn.cancels == 0


def test_progress_counts_rows_over_both_steps(monkeypatch):
    conn = conn_for(
        [("a", 0, 0.9), ("b", 0, 0.8), ("a", 1, 0.7)],
        [("a", "A"), ("b", "B")],
    )
    setup(monkeypatch, conn)
    calls = []
    search.search_pg_exact([[1.0, 0, 0]] * 2, 0.3, progress=lambda *a: calls.append(a))
    assert calls == [(n, 0, "") for n in (1, 2, 3, 4, 5)]


class Blocking(Conn):
    """Step 1 blocks until cancel_safe() is called, then fails like Postgres does."""

    def __init__(self):
        self.cancelled = threading.Event()
        self.in_scan = threading.Event()
        super().__init__(
            [EXT_VERSION],
            [("vector", "extensions", 3)],
            [(-1,)],
            [(None,)],
            self.blocked_rows(),  # step 1 yields nothing until the query is cancelled
        )

    def blocked_rows(self):
        self.in_scan.set()
        assert self.cancelled.wait(5)
        raise RuntimeError("canceling statement due to user request")
        yield

    def cancel_safe(self):
        super().cancel_safe()
        self.cancelled.set()


def test_stop_from_another_thread_cancels_and_raises(monkeypatch):
    conn = Blocking()
    setup(monkeypatch, conn)
    stop = search.Stop()

    def stopper():
        assert conn.in_scan.wait(5)
        stop.stop()

    t = threading.Thread(target=stopper)
    t.start()
    with pytest.raises(search.SearchCancelled):
        search.search_pg_exact([[1.0, 0, 0]], 0.3, stop=stop)
    t.join()
    assert conn.cancels == 1 and conn.closed


def test_stop_before_the_connection_exists(monkeypatch):
    conn = conn_for([], [])
    setup(monkeypatch, conn)
    stop = search.Stop()
    stop.stop()
    with pytest.raises(search.SearchCancelled):
        search.search_pg_exact([[1.0, 0, 0]], 0.3, stop=stop)
    assert conn.cancels == 0 and conn.closed and scans(conn) == []


def test_cancel_falls_back_to_cancel_when_cancel_safe_is_missing(monkeypatch):
    class Old(Conn):
        cancelled = 0
        cancel_safe = None

        def cancel(self):
            self.cancelled += 1

    conn = Old()
    stop = search.Stop()
    stop.conn = conn
    stop.stop()
    assert conn.cancelled == 1
