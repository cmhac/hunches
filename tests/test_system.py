import json
import os
from pathlib import Path
from typing import Any

import platformdirs
import pytest

from hunches import system
from hunches.system import System


def make(**kw: Any) -> System:
    base: dict[str, Any] = {
        "provider": "anthropic",
        "assistant_model": "a:1",
        "assistant_thinking": "medium",
        "classifier_model": "c:1",
    }
    return System(**{**base, **kw})


def test_system_dir_honours_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HUNCHES_HOME", str(tmp_path / "x"))
    assert system.system_dir() == tmp_path / "x"


def test_system_dir_default_is_platformdirs(monkeypatch):
    monkeypatch.delenv("HUNCHES_HOME")
    assert system.system_dir() == Path(platformdirs.user_config_dir("hunches"))


def test_read_missing_is_first_run():
    assert system.read_system() is None


def test_round_trip_and_file_shape():
    s = make(
        recommendation_seen=1,
        s3_stores=[
            system.Store(
                name="n", bucket="b", index="i", region=None, embedding_model="e:1"
            )
        ],
    )
    system.write_system(s)
    assert system.read_system() == s
    raw = json.loads((system.system_dir() / "system.json").read_text())
    assert raw["version"] == 1
    assert raw["assistant_thinking"] == "medium"
    assert raw["s3_stores"][0] == {
        "name": "n",
        "bucket": "b",
        "index": "i",
        "region": None,
        "embedding_model": "e:1",
    }
    assert raw["projects"] == []


def test_refuses_to_overwrite_newer_version():
    path = system.system_dir() / "system.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 2, "future": True}))
    with pytest.raises(system.NewerSystemFile):
        system.write_system(make())
    assert json.loads(path.read_text()) == {"version": 2, "future": True}


def test_failed_write_leaves_old_file_and_no_temp(monkeypatch):
    system.write_system(make(assistant_model="old:1"))

    def boom(*a):
        raise OSError("disk")

    with monkeypatch.context() as m:
        m.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            system.write_system(make(assistant_model="new:1"))
    s = system.read_system()
    assert s is not None and s.assistant_model == "old:1"
    assert [p.name for p in system.system_dir().iterdir()] == ["system.json"]


@pytest.fixture
def clock(monkeypatch):
    """Controllable system._now(): set clock.t before each call."""

    class Clock:
        t = "2026-01-01T00:00:00Z"

    monkeypatch.setattr(system, "_now", lambda: Clock.t)
    return Clock


def test_add_project_is_absolute_deduped_and_stamped(tmp_path, clock):
    system.write_system(make())
    system.add_project(tmp_path / "p")
    clock.t = "2026-02-02T00:00:00Z"
    system.add_project(tmp_path / "p" / ".." / "p")
    s = system.read_system()
    assert s is not None
    assert [(p.path, p.last_opened) for p in s.projects] == [
        (str(tmp_path / "p"), "2026-01-01T00:00:00Z")
    ]


def test_remove_project(tmp_path):
    system.write_system(make())
    system.add_project(tmp_path / "a")
    system.add_project(tmp_path / "b")
    system.remove_project(tmp_path / "a")
    system.remove_project(tmp_path / "zzz")  # absent: no error
    s = system.read_system()
    assert s is not None and [p.path for p in s.projects] == [str(tmp_path / "b")]


def test_touch_and_by_recent(tmp_path, clock):
    system.write_system(make())
    system.add_project(tmp_path / "a")
    clock.t = "2026-01-02T00:00:00Z"
    system.add_project(tmp_path / "b")
    assert [p.path for p in system.projects_by_recent()] == [
        str(tmp_path / "b"),
        str(tmp_path / "a"),
    ]
    clock.t = "2026-01-03T00:00:00Z"
    system.touch_project(tmp_path / "a")
    recent = system.projects_by_recent()
    assert [p.path for p in recent] == [str(tmp_path / "a"), str(tmp_path / "b")]
    assert recent[0].last_opened == "2026-01-03T00:00:00Z"


def test_projects_by_recent_without_system_file():
    assert system.projects_by_recent() == []


def test_add_replaces_and_delete_store():
    system.write_system(make())
    system.add_store("s", "b1", "i1", None, "e:1")
    system.add_store("s", "b2", "i2", "eu-west-1", "e:2")
    system.add_store("t", "b3", "i3", None, "e:3")
    s = system.read_system()
    assert s is not None
    assert [
        (x.name, x.bucket, x.index, x.region, x.embedding_model) for x in s.s3_stores
    ] == [
        ("s", "b2", "i2", "eu-west-1", "e:2"),
        ("t", "b3", "i3", None, "e:3"),
    ]
    system.delete_store("s")
    system.delete_store("nope")
    s = system.read_system()
    assert s is not None and [x.name for x in s.s3_stores] == ["t"]


def test_recommended_table():
    assert system.RECOMMENDED == {
        "anthropic": {
            "assistant": "anthropic:claude-sonnet-5-5",
            "thinking": "medium",
            "classifier": "anthropic:claude-haiku-4-5",
        },
        "openai": {
            "assistant": "openai:gpt-6-sol",
            "thinking": None,
            "classifier": "openai:gpt-6-luna",
        },
    }
    assert system.RECOMMENDED_REVISION == 1


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_recommended_ids_are_known_and_priced(provider):
    import typing

    from genai_prices import Usage, calc_price
    from pydantic_ai.models import KnownModelName

    known = typing.get_args(KnownModelName.__value__)
    for role in ("assistant", "classifier"):
        full = system.RECOMMENDED[provider][role]
        assert full in known
        assert full
        prefix, model = full.split(":", 1)
        price = calc_price(
            Usage(input_tokens=1000, output_tokens=1000), model, provider_id=prefix
        )
        assert price.total_price > 0


@pytest.fixture
def rev2(monkeypatch):
    monkeypatch.setattr(system, "RECOMMENDED_REVISION", 2)
    monkeypatch.setitem(
        system.RECOMMENDED,
        "anthropic",
        {"assistant": "a:2", "thinking": "high", "classifier": "c:2"},
    )


def test_changed_false_when_already_seen(rev2):
    system.write_system(make(recommendation_seen=2))
    s = system.read_system()
    assert s is not None
    assert system.recommended_changed(s) is False


def test_changed_silently_bumps_when_models_already_match(rev2):
    system.write_system(
        make(
            assistant_model="a:2",
            assistant_thinking="high",
            classifier_model="c:2",
            recommendation_seen=1,
        )
    )
    s = system.read_system()
    assert s is not None
    assert system.recommended_changed(s) is False
    s = system.read_system()
    assert s is not None and s.recommendation_seen == 2


def test_changed_true_when_models_differ_and_nothing_written(rev2):
    system.write_system(make(recommendation_seen=1))
    s = system.read_system()
    assert s is not None
    assert system.recommended_changed(s) is True
    s = system.read_system()
    assert s is not None and s.recommendation_seen == 1


def test_keep_mine_and_use_new_touch_only_system_file(rev2, tmp_path):
    project = tmp_path / "proj" / ".hunches"
    project.mkdir(parents=True)
    (project / "config.toml").write_text('assistant_model = "p:1"\n')

    system.write_system(make(recommendation_seen=1))
    system.keep_mine()
    s = system.read_system()
    assert s is not None
    assert (s.assistant_model, s.assistant_thinking, s.classifier_model) == (
        "a:1",
        "medium",
        "c:1",
    )
    assert s.recommendation_seen == 2

    system.write_system(make(recommendation_seen=1))
    system.use_new()
    s = system.read_system()
    assert s is not None
    assert (s.assistant_model, s.assistant_thinking, s.classifier_model) == (
        "a:2",
        "high",
        "c:2",
    )
    assert s.recommendation_seen == 2
    assert (project / "config.toml").read_text() == 'assistant_model = "p:1"\n'


def test_use_new_openai_has_no_thinking():
    system.write_system(
        make(provider="openai", assistant_thinking="medium", recommendation_seen=0)
    )
    system.use_new()
    s = system.read_system()
    assert s is not None
    assert (s.assistant_model, s.assistant_thinking, s.classifier_model) == (
        "openai:gpt-6-sol",
        None,
        "openai:gpt-6-luna",
    )


def test_rename_store_keeps_other_fields_and_refuses_a_taken_name():
    system.write_system(make())
    system.add_store("a", "b1", "i1", "us-east-1", "e1")
    system.add_store("b", "b2", "i2", None, "e2")
    system.rename_store("a", "c")
    current = system.read_system()
    assert current is not None
    stores = {s.name: s for s in current.s3_stores}
    assert set(stores) == {"b", "c"}
    assert (stores["c"].bucket, stores["c"].region) == ("b1", "us-east-1")
    with pytest.raises(ValueError):
        system.rename_store("c", "b")
    current = system.read_system()
    assert current is not None
    assert {s.name for s in current.s3_stores} == {"b", "c"}


def test_pg_max_result_mb_defaults_to_512_for_an_old_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HUNCHES_HOME", str(tmp_path))
    (tmp_path / "system.json").write_text(
        json.dumps(
            {
                "version": 1,
                "provider": "anthropic",
                "assistant_model": "a:1",
                "classifier_model": "c:1",
            }
        )
    )
    s = system.read_system()
    assert s is not None and s.pg_max_result_mb == 512 and s.version == 1


@pytest.mark.parametrize("mb", [0, 1, 2048])
def test_pg_max_result_mb_round_trips(tmp_path: Path, monkeypatch, mb):
    monkeypatch.setenv("HUNCHES_HOME", str(tmp_path))
    system.write_system(make(pg_max_result_mb=mb))
    s = system.read_system()
    assert s is not None and s.pg_max_result_mb == mb
    assert json.loads((tmp_path / "system.json").read_text())["pg_max_result_mb"] == mb
