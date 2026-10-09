import sys
import types

import pytest
from botocore.exceptions import NoCredentialsError

from hunches import files, keys, search

URL = "postgresql://alice:s3cr%40t@db.example.com:5433/mydb"
IAM_URL = "postgresql://bob@inst.abc123.us-east-1.rds.amazonaws.com:5432/mydb"
TOKEN = "TOKEN-" + "x" * 40


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))


class FakeConn:
    def __init__(self, args, kwargs):
        self.args, self.kwargs = args, kwargs
        self.read_only = None
        self.isolation_level = None
        self.executed = []

    def cursor(self):
        return FakeCursor(self)


class FakePsycopg(types.ModuleType):
    class IsolationLevel:
        REPEATABLE_READ = "RR"

    def __init__(self, error=None):
        super().__init__("psycopg")
        self.error, self.conns = error, []

    def connect(self, *args, **kwargs):
        if self.error:
            raise self.error
        self.conns.append(FakeConn(args, kwargs))
        return self.conns[-1]


class FakeRds:
    def __init__(self, calls, error):
        self.calls, self.error = calls, error

    def generate_db_auth_token(self, **kw):
        if self.error:
            raise self.error
        self.calls.append(kw)
        return TOKEN


class FakeBoto3(types.ModuleType):
    def __init__(self, region="eu-west-1", error=None):
        super().__init__("boto3")
        self.region, self.error = region, error
        self.sessions, self.token_calls, self.clients = [], [], []
        boto = self

        class Session:
            def __init__(self, profile_name=None):
                boto.sessions.append(profile_name)
                self.region_name = boto.region

            def client(self, name, region_name=None):
                boto.clients.append((name, region_name))
                return FakeRds(boto.token_calls, boto.error)

        self.Session = Session


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HUNCHES_PG_URL", raising=False)
    monkeypatch.setattr(keys, "_stored", lambda var: None)


def setup(monkeypatch, url=URL, psycopg_error=None, **fields):
    fields = {"pg_table": "public.docs"} | fields
    files.write_config(
        files.Config.model_validate(
            {
                "assistant_model": "anthropic:claude-sonnet-5-5",
                "classifier_model": "anthropic:claude-haiku-4-5",
                "backend": "pgvector",
                "embedding_model": "m",
                **fields,
            }
        )
    )
    if url:
        monkeypatch.setenv("HUNCHES_PG_URL", url)
    fake = FakePsycopg(psycopg_error)
    monkeypatch.setitem(sys.modules, "psycopg", fake)
    return fake


def test_psycopg_missing(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setitem(sys.modules, "psycopg", None)
    with pytest.raises(ImportError) as e:
        search.pg_connect(files.read_config())
    assert str(e.value) == "The pgvector backend needs psycopg: pip install hunches[pg]"


def test_url_unset(monkeypatch):
    setup(monkeypatch, url=None)
    with pytest.raises(ValueError) as e:
        search.pg_connect(files.read_config())
    assert str(e.value) == (
        "config.toml: pg_url_var HUNCHES_PG_URL is not set (environment or keyring)"
    )


def test_custom_url_var_named_in_message(monkeypatch):
    setup(monkeypatch, url=None, pg_url_var="MY_PG")
    with pytest.raises(ValueError, match="pg_url_var MY_PG is not set"):
        search.pg_connect(files.read_config())


def test_table_missing(monkeypatch):
    setup(monkeypatch, pg_table=None)
    with pytest.raises(ValueError) as e:
        search.pg_connect(files.read_config())
    assert str(e.value) == "config.toml: pg_table is required for pgvector"


def test_env_beats_keyring(monkeypatch):
    fake = setup(monkeypatch, url="postgresql://env/db")
    monkeypatch.setattr(keys, "_stored", lambda var: "postgresql://keyring/db")
    search.pg_connect(files.read_config())
    assert fake.conns[0].args == ("postgresql://env/db",)


def test_keyring_used_when_env_unset(monkeypatch):
    fake = setup(monkeypatch, url=None)
    monkeypatch.setattr(
        keys,
        "_stored",
        lambda var: "postgresql://keyring/db" if var == "HUNCHES_PG_URL" else None,
    )
    search.pg_connect(files.read_config())
    assert fake.conns[0].args == ("postgresql://keyring/db",)


def test_connect_is_read_only_and_never_prepares(monkeypatch):
    fake = setup(monkeypatch)
    conn = search.pg_connect(files.read_config())
    assert conn is fake.conns[0]
    assert conn.args == (URL,)
    assert conn.kwargs == {"prepare_threshold": None}  # autocommit stays off
    assert conn.read_only is True
    assert conn.isolation_level == "RR"
    assert conn.executed == []  # no timeout configured: nothing issued


@pytest.mark.parametrize("seconds,ms", [(30, 30000), (0, 0)])
def test_statement_timeout_set_local(monkeypatch, seconds, ms):
    setup(monkeypatch, pg_statement_timeout_s=seconds)
    conn = search.pg_connect(files.read_config())
    assert conn.executed == [(f"SET LOCAL statement_timeout = {ms}", None)]


def test_iam_token_arguments_and_password_kwarg(monkeypatch):
    fake = setup(
        monkeypatch,
        url=IAM_URL,
        pg_auth="rds_iam",
        pg_aws_region="us-east-2",
        pg_aws_profile="prof",
    )
    boto = FakeBoto3()
    monkeypatch.setitem(sys.modules, "boto3", boto)
    conn = search.pg_connect(files.read_config())
    assert boto.sessions == ["prof"]
    assert boto.clients == [("rds", "us-east-2")]
    assert boto.token_calls == [
        {
            "DBHostname": "inst.abc123.us-east-1.rds.amazonaws.com",
            "Port": 5432,
            "DBUsername": "bob",
            "Region": "us-east-2",
        }
    ]
    assert conn.args == (IAM_URL,)
    assert TOKEN not in conn.args[0]
    assert conn.kwargs == {
        "prepare_threshold": None,
        "password": TOKEN,
        "sslmode": "require",
    }
    assert fake.conns == [conn]


def test_iam_region_falls_back_to_session_and_port_defaults(monkeypatch):
    setup(monkeypatch, url="postgresql://bob@h.example.com/db", pg_auth="rds_iam")
    boto = FakeBoto3(region="eu-west-1")
    monkeypatch.setitem(sys.modules, "boto3", boto)
    search.pg_connect(files.read_config())
    assert boto.sessions == [None]
    assert boto.token_calls[0]["Region"] == "eu-west-1"
    assert boto.token_calls[0]["Port"] == 5432


def test_iam_keeps_existing_sslmode(monkeypatch):
    setup(monkeypatch, url=IAM_URL + "?sslmode=verify-full", pg_auth="rds_iam")
    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3())
    conn = search.pg_connect(files.read_config())
    assert conn.args == (IAM_URL + "?sslmode=verify-full",)
    assert "sslmode" not in conn.kwargs


def test_iam_no_region(monkeypatch):
    setup(monkeypatch, url=IAM_URL, pg_auth="rds_iam")
    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3(region=None))
    with pytest.raises(ValueError) as e:
        search.pg_connect(files.read_config())
    assert str(e.value) == "pg_aws_region is not set and boto3 found no default region"


def test_iam_no_credentials(monkeypatch):
    setup(monkeypatch, url=IAM_URL, pg_auth="rds_iam")
    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3(error=NoCredentialsError()))
    with pytest.raises(ValueError) as e:
        search.pg_connect(files.read_config())
    assert str(e.value) == "AWS: Unable to locate credentials"


def test_iam_boto3_missing(monkeypatch):
    setup(monkeypatch, url=IAM_URL, pg_auth="rds_iam")
    monkeypatch.setitem(sys.modules, "boto3", None)
    with pytest.raises(ImportError) as e:
        search.pg_connect(files.read_config())
    assert str(e.value) == "IAM authentication needs boto3: pip install hunches[rds]"


def test_connect_error_is_scrubbed(monkeypatch):
    err = RuntimeError(f'could not connect to "{URL}" password=s3cr@t')
    setup(monkeypatch, psycopg_error=err)
    with pytest.raises(RuntimeError) as e:
        search.pg_connect(files.read_config())
    msg = str(e.value)
    assert msg == 'could not connect to "***" password=***'


def test_iam_connect_error_scrubbed_and_hinted(monkeypatch):
    err = RuntimeError(
        f'PAM authentication failed for user "bob" ({TOKEN}) at {IAM_URL}'
    )
    setup(monkeypatch, url=IAM_URL, pg_auth="rds_iam", psycopg_error=err)
    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3())
    with pytest.raises(RuntimeError) as e:
        search.pg_connect(files.read_config())
    assert str(e.value) == (
        'PAM authentication failed for user "bob" (***) at ***\n'
        "Check: the database user has the rds_iam role, the AWS identity may "
        "rds-db:connect on this DbiResourceId/user, and the URL host is the "
        "instance endpoint (not a custom DNS name)."
    )


def test_non_auth_connect_error_gets_no_iam_hint(monkeypatch):
    setup(
        monkeypatch,
        url=IAM_URL,
        pg_auth="rds_iam",
        psycopg_error=RuntimeError("connection refused"),
    )
    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3())
    with pytest.raises(RuntimeError) as e:
        search.pg_connect(files.read_config())
    assert str(e.value) == "connection refused"


@pytest.mark.parametrize(
    "text,hint",
    [
        (
            "canceling statement due to conflict with recovery",
            (
                "Fix: run the search against the primary/writer endpoint, or a replica "
                "configured for long queries."
            ),
        ),
        (
            "canceling statement due to statement timeout",
            (
                "Fix: raise statement_timeout for this role, or set "
                "pg_statement_timeout_s in config.toml"
            ),
        ),
        (
            "different vector dimensions 1536 and 3072",
            (
                "Fix: embedding_model in .hunches/config.toml must be the model the "
                "table was embedded with."
            ),
        ),
    ],
)
def test_message_hints(monkeypatch, text, hint):
    setup(monkeypatch)
    config = files.read_config()
    assert search.pg_message(RuntimeError(text), config) == f"{text}\n{hint}"


def test_message_missing_table_unchanged_and_scrubbed(monkeypatch):
    setup(monkeypatch)
    config = files.read_config()
    text = 'relation "public.docs" does not exist'
    assert search.pg_message(RuntimeError(text), config) == text
    leaked = RuntimeError("bad s3cr@t and s3cr%40t")
    assert search.pg_message(leaked, config) == "bad *** and ***"


def test_url_id_ignores_the_password_and_query():
    url_id = search.pg_url_id(URL)
    assert len(url_id) == 16 and int(url_id, 16) >= 0
    for same in (
        "postgresql://alice:other-password@db.example.com:5433/mydb",
        "postgres://alice@DB.Example.com:5433/mydb?sslmode=require",
        "host=db.example.com port=5433 dbname=mydb user=alice password=x",
    ):
        assert search.pg_url_id(same) == url_id, same


def test_url_id_differs_by_host_port_database_and_user():
    ids = {
        search.pg_url_id(u)
        for u in (
            URL,
            "postgresql://alice:s3cr%40t@db2.example.com:5433/mydb",
            "postgresql://alice:s3cr%40t@db.example.com:5432/mydb",
            "postgresql://alice:s3cr%40t@db.example.com:5433/other",
            "postgresql://carol:s3cr%40t@db.example.com:5433/mydb",
        )
    }
    assert len(ids) == 5


def test_url_id_defaults_port_and_database_like_libpq():
    assert search.pg_url_id("postgresql://u@h") == search.pg_url_id(
        "postgresql://u@h:5432/u"
    )


@pytest.mark.parametrize(
    "bad", ["not a url s3cr3t", "postgresql://u:s3cr3t@/db", "user=u password=s3cr3t"]
)
def test_url_id_refuses_without_echoing_the_input(bad):
    with pytest.raises(ValueError) as e:
        search.pg_url_id(bad)
    assert "s3cr3t" not in str(e.value)


def test_url_name_prefers_an_explicit_var_then_the_id_then_the_default():
    assert search.pg_url_name("ab12", "MY_PG") == "MY_PG"
    assert search.pg_url_name("ab12", None) == "HUNCHES_PG_URL_AB12"
    assert search.pg_url_name(None, None) == "HUNCHES_PG_URL"


def test_connects_with_the_url_saved_under_the_id(monkeypatch):
    url_id = search.pg_url_id(URL)
    fake = setup(monkeypatch, url=None, pg_url_id=url_id)
    monkeypatch.setenv("HUNCHES_PG_URL", "postgresql://wrong@elsewhere/db")
    monkeypatch.setenv(f"HUNCHES_PG_URL_{url_id.upper()}", URL)
    search.pg_connect(files.read_config())
    assert fake.conns[0].args == (URL,)


def test_unsaved_url_id_says_where_to_paste_it(monkeypatch):
    setup(monkeypatch, url=None, pg_url_id="ab12")
    with pytest.raises(ValueError) as e:
        search.pg_connect(files.read_config())
    assert str(e.value) == (
        "The database URL is not saved on this computer: paste it in Project "
        "settings (F3), or set HUNCHES_PG_URL_AB12 in the environment"
    )
