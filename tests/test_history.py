import json

import pytest

from hunches import files, history

HELLO = "hello"
HELLO_SHA = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files.ensure_root()


def read(name):
    return files.read_text(name)


def log_lines():
    return (files.root() / "history" / "log.jsonl").read_text().splitlines()


def test_save_writes_file_object_and_log_entry():
    assert history.save("prompt", HELLO, "user", "YOU EDITED the prompt") is True
    assert read("prompt.md") == HELLO
    assert (files.root() / "history" / "objects" / HELLO_SHA).read_text() == HELLO
    (entry,) = history.entries("prompt")
    assert entry["seq"] == 1
    assert entry["kind"] == "edit"
    assert entry["artifact"] == "prompt"
    assert entry["before"] is None
    assert entry["after"] == HELLO_SHA
    assert entry["source"] == "user"
    assert entry["summary"] == "YOU EDITED the prompt"
    assert "ts" in entry
    assert "group" not in entry


def test_text_returns_what_was_saved():
    history.save("seeds", "a\nb\n", "user", "s")
    (entry,) = history.entries("seeds")
    assert history.text(entry["after"]) == "a\nb\n"
    assert history.text(None) is None
    assert history.text("0" * 64) is None


def test_noop_save_writes_no_entry():
    history.save("prompt", "one", "user", "first")
    assert history.save("prompt", "one", "user", "again") is False
    assert len(history.entries()) == 1
    assert len(log_lines()) == 1


def test_identical_content_stored_once():
    history.save("prompt", "x", "user", "1")
    history.save("seeds", "x", "user", "2")
    assert len(list((files.root() / "history" / "objects").iterdir())) == 1


def test_undo_and_redo_sequence_yields_each_content():
    history.save("prompt", "one", "user", "set one")
    history.save("prompt", "two", "user", "set two")
    history.save("prompt", "three", "user", "set three")
    assert history.undo("prompt") is not None
    assert read("prompt.md") == "two"
    history.undo("prompt")
    assert read("prompt.md") == "one"
    history.redo("prompt")
    assert read("prompt.md") == "two"
    history.redo("prompt")
    assert read("prompt.md") == "three"
    assert history.redo("prompt") is None
    assert read("prompt.md") == "three"


def test_undo_entry_shape():
    history.save("prompt", "one", "user", "a")
    history.save("prompt", "two", "user", "set two")
    entry = history.undo("prompt")
    assert entry is not None
    assert entry["source"] == "undo"
    assert entry["summary"] == "Undid: set two"
    assert entry["seq"] == 3
    redone = history.redo("prompt")
    assert redone is not None
    assert redone["source"] == "redo"
    assert redone["summary"] == "Redid: set two"


def test_can_undo_and_can_redo():
    assert not history.can_undo("prompt")
    assert not history.can_redo("prompt")
    history.save("prompt", "one", "user", "a")
    # the first version has nothing before it; undo never deletes a file
    assert not history.can_undo("prompt")
    history.save("prompt", "two", "user", "b")
    assert history.can_undo("prompt")
    assert not history.can_redo("prompt")
    history.undo("prompt")
    assert not history.can_undo("prompt")
    assert history.can_redo("prompt")


def test_undo_with_nothing_to_undo_returns_none():
    assert history.undo("seeds") is None
    assert history.redo("seeds") is None


def test_new_edit_after_undo_clears_redo():
    history.save("prompt", "one", "user", "a")
    history.save("prompt", "two", "user", "b")
    history.undo("prompt")
    history.save("prompt", "three", "user", "c")
    assert not history.can_redo("prompt")
    history.undo("prompt")
    assert read("prompt.md") == "one"


def test_stacks_are_per_artifact():
    history.save("seeds", "s1", "user", "a")
    history.save("seeds", "s2", "user", "b")
    history.save("prompt", "p1", "user", "c")
    history.save("prompt", "p2", "user", "d")
    history.undo("prompt")
    assert read("prompt.md") == "p1"
    assert read("seeds.csv") == "s2"
    assert history.can_undo("seeds")
    history.undo("seeds")
    assert read("seeds.csv") == "s1"
    assert read("prompt.md") == "p1"


def test_group_entries_undo_and_redo_together():
    history.save("seeds", "base", "user", "base")
    history.save("seeds", "base\na", "assistant", "add a", group="g1")
    history.save("seeds", "base\na\nb", "assistant", "add b", group="g1")
    history.save("seeds", "base\na\nb\nc", "assistant", "add c", group="g1")
    history.undo("seeds")
    assert read("seeds.csv") == "base"
    assert not history.can_undo("seeds")
    history.redo("seeds")
    assert read("seeds.csv") == "base\na\nb\nc"


def test_different_groups_do_not_merge():
    history.save("seeds", "0", "user", "0")
    history.save("seeds", "1", "assistant", "1", group="g1")
    history.save("seeds", "2", "assistant", "2", group="g2")
    history.undo("seeds")
    assert read("seeds.csv") == "1"


def test_group_recorded_in_entry():
    history.save("seeds", "0", "assistant", "0", group="g1")
    assert history.entries("seeds")[0]["group"] == "g1"


def test_sync_logs_external_edit_and_returns_it():
    history.save("prompt", "one", "user", "a")
    (files.root() / "prompt.md").write_text("changed in an editor")
    added = history.sync()
    assert len(added) == 1
    assert added[0]["source"] == "external"
    assert added[0]["artifact"] == "prompt"
    assert added[0]["before"] is not None
    assert history.text(added[0]["after"]) == "changed in an editor"
    assert history.sync() == []
    history.undo("prompt")
    assert read("prompt.md") == "one"


def test_save_does_not_overwrite_an_unlogged_outside_edit():
    history.save("prompt", "one", "user", "a")
    (files.root() / "prompt.md").write_text("outside")
    history.save("prompt", "two", "user", "b")
    history.undo("prompt")
    assert read("prompt.md") == "outside"


def test_external_delete_is_logged_and_can_be_undone():
    history.save("prompt", "one", "user", "a")
    (files.root() / "prompt.md").unlink()
    (added,) = history.sync()
    assert added["after"] is None
    history.undo("prompt")
    assert read("prompt.md") == "one"


def test_crash_between_file_write_and_log_append_is_recovered():
    history.save("prompt", "one", "user", "a")

    def boom(entry):
        raise OSError("died")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(history, "_append", boom)
        with pytest.raises(OSError):
            history.save("prompt", "two", "user", "b")
    assert read("prompt.md") == "two"
    (added,) = history.sync()
    assert added["source"] == "external"
    assert history.text(added["after"]) == "two"
    history.undo("prompt")
    assert read("prompt.md") == "one"


def test_project_without_log_gets_baseline_entries():
    (files.root() / "seeds.csv").write_text("s")
    (files.root() / "prompt.md").write_text("p")
    added = history.sync()
    assert [(e["artifact"], e["source"]) for e in added] == [
        ("seeds", "baseline"),
        ("prompt", "baseline"),
    ]
    assert history.entries("taxonomy") == []
    assert history.sync() == []
    # baseline is a real state: editing then undoing returns to it
    history.save("prompt", "p2", "user", "edit")
    history.undo("prompt")
    assert read("prompt.md") == "p"


def test_file_created_outside_after_baseline_is_external():
    (files.root() / "prompt.md").write_text("p")
    history.sync()
    (files.root() / "seeds.csv").write_text("s")
    (added,) = history.sync()
    assert added["source"] == "external"
    assert added["before"] is None


def test_empty_project_sync_logs_nothing():
    assert history.sync() == []
    assert history.entries() == []


def test_log_is_append_only_and_seq_increases():
    history.save("prompt", "one", "user", "a")
    before = log_lines()
    history.save("prompt", "two", "user", "b")
    history.undo("prompt")
    history.redo("prompt")
    after = log_lines()
    assert after[: len(before)] == before
    assert [json.loads(line)["seq"] for line in after] == [1, 2, 3, 4]


def test_is_current_is_the_newest_entry_of_its_file():
    history.save("prompt", "one", "user", "a")
    history.save("seeds", "s", "user", "b")
    history.save("prompt", "two", "user", "c")
    first, second = history.entries("prompt")
    assert history.is_current(second)
    assert not history.is_current(first)
    assert history.is_current(history.entries("seeds")[0])


def test_is_current_false_for_non_edit_entries():
    history.approval(1, "seeds_approved", {}, "Approved")
    assert not history.is_current(history.entries()[0])


def test_restore_makes_file_as_after_entry_and_is_undoable():
    history.save("prompt", "one", "user", "a")
    history.save("prompt", "two", "user", "b")
    history.save("prompt", "three", "user", "c")
    first = history.entries("prompt")[0]
    entry = history.restore("prompt", first["seq"])
    assert read("prompt.md") == "one"
    assert entry["source"] == "restore"
    assert entry["summary"] == "Restored: a"
    history.undo("prompt")
    assert read("prompt.md") == "three"


def test_restore_baseline_entry():
    (files.root() / "prompt.md").write_text("p")
    history.sync()
    history.save("prompt", "p2", "user", "edit")
    baseline = history.entries("prompt")[0]
    history.restore("prompt", baseline["seq"])
    assert read("prompt.md") == "p"


def test_restore_to_current_state_writes_nothing():
    history.save("prompt", "one", "user", "a")
    history.save("prompt", "two", "user", "b")
    last = history.entries("prompt")[-1]
    history.restore("prompt", last["seq"])
    assert len(history.entries()) == 2


def test_approval_entry_in_combined_timeline():
    history.save("prompt", "one", "user", "a")
    history.approval(5, "dev_done", {"prompt": "h"}, "Approved: Tuning loop")
    last = history.entries()[-1]
    assert last["kind"] == "approval"
    assert last["seq"] == 2
    assert last["stage"] == 5
    assert last["flag"] == "dev_done"
    assert last["inputs"] == {"prompt": "h"}
    assert last["summary"] == "Approved: Tuning loop"
    assert len(history.entries("prompt")) == 1


def test_approval_does_not_disturb_stacks():
    history.save("prompt", "one", "user", "a")
    history.save("prompt", "two", "user", "b")
    history.approval(5, "dev_done", {}, "Approved")
    history.undo("prompt")
    assert read("prompt.md") == "one"


# ---- taxonomy versions and NeedsVersion (task 02)


def tax(*names, mode="single"):
    return files.Taxonomy(
        mode=mode, labels=[files.Label(name=n, description=n.upper()) for n in names]
    )


def label_gold(*labels):
    files.write_gold(
        [
            files.GoldRow(id="1", text="t1", labels=list(labels), split="dev"),
            files.GoldRow(id="2", text="t2", labels=[], split="dev"),
        ]
    )


def taxonomy_names():
    return [x.name for x in files.read_taxonomy().labels]


def gold_labels():
    return [r.labels for r in files.read_gold()]


def save_taxonomy(*names):
    history.save("taxonomy", files.taxonomy_yaml(tax(*names)), "user", "labels")


def test_start_new_version_logs_edit_with_snapshot_and_version_entry():
    save_taxonomy("a", "b")
    label_gold("a")
    assert history.start_new_version(tax("c", "d"), "Taxonomy version 2 started") == 1
    assert taxonomy_names() == ["c", "d"]
    assert gold_labels() == [[], []]
    edit = history.entries("taxonomy")[-1]
    assert (edit["source"], edit["snapshot"]) == ("user", 1)
    assert edit["summary"] == "Taxonomy version 2 started"
    version = history.entries()[-1]
    assert (version["kind"], version["snapshot"]) == ("version", 1)
    assert version["summary"] == "Taxonomy version 2 started"


def test_undo_of_version_start_restores_version_and_gold_and_redo_returns():
    save_taxonomy("a", "b")
    label_gold("a")
    history.start_new_version(tax("c", "d"), "v2")
    undo = history.undo("taxonomy")
    assert undo
    assert taxonomy_names() == ["a", "b"]
    assert gold_labels() == [["a"], []]
    assert (undo["source"], undo["snapshot"]) == ("undo", 2)  # the new state, archived
    assert history.can_redo("taxonomy")
    with pytest.raises(
        history.NeedsVersion
    ) as e:  # version 1's labels are live: archived first
        history.redo("taxonomy")
    assert (e.value.kind, e.value.number) == ("restore", 3)
    redo = history.redo("taxonomy", confirmed=True)
    assert redo
    assert taxonomy_names() == ["c", "d"]
    assert gold_labels() == [[], []]
    assert (redo["source"], redo["snapshot"]) == ("redo", 3)
    assert (
        history.entries("taxonomy")[-1]["after"]
        == history.entries("taxonomy")[-3]["after"]
    )


def test_undo_of_version_start_with_new_gold_needs_confirmation_kind_restore():
    save_taxonomy("a", "b")
    label_gold("a")
    history.start_new_version(tax("c", "d"), "v2")
    label_gold("c")
    with pytest.raises(history.NeedsVersion) as e:
        history.undo("taxonomy")
    assert (e.value.kind, e.value.number) == ("restore", 2)
    assert [x.name for x in e.value.taxonomy.labels] == ["a", "b"]
    assert taxonomy_names() == ["c", "d"]  # nothing changed
    history.undo("taxonomy", confirmed=True)
    assert taxonomy_names() == ["a", "b"]
    assert gold_labels() == [["a"], []]  # labels kept, version 1's are back
    assert files.list_versions()[-1]["version"] == 2  # the labelled state is archived


def test_undo_of_plain_label_edit_with_gold_needs_new_version():
    save_taxonomy("a", "b")
    save_taxonomy("a", "b", "c")
    label_gold("c")
    with pytest.raises(history.NeedsVersion) as e:
        history.undo("taxonomy")
    assert (e.value.kind, e.value.number) == ("new_version", 1)
    assert [x.name for x in e.value.taxonomy.labels] == ["a", "b"]
    assert taxonomy_names() == ["a", "b", "c"] and gold_labels() == [["c"], []]
    entry = history.undo("taxonomy", confirmed=True)
    assert entry
    assert taxonomy_names() == ["a", "b"]
    assert gold_labels() == [[], []]  # D12: cleared on the same items
    assert [r.id for r in files.read_gold()] == ["1", "2"]
    assert (entry["source"], entry["snapshot"]) == ("undo", 1)
    assert [v["version"] for v in files.list_versions()] == [1]
    assert history.can_redo("taxonomy")


def test_redo_and_restore_that_change_labels_with_gold_need_new_version():
    save_taxonomy("a", "b")
    save_taxonomy("a", "b", "c")
    history.undo("taxonomy")  # no gold yet: plain
    label_gold("a")
    with pytest.raises(history.NeedsVersion) as e:
        history.redo("taxonomy")
    assert e.value.kind == "new_version"
    seq = history.entries("taxonomy")[0]["seq"]
    history.restore("taxonomy", seq)  # same labels as now: plain, no prompt
    seq = history.entries("taxonomy")[1]["seq"]
    with pytest.raises(history.NeedsVersion):
        history.restore("taxonomy", seq)
    history.restore("taxonomy", seq, confirmed=True)
    assert taxonomy_names() == ["a", "b", "c"]
    assert gold_labels() == [[], []]


def test_description_only_undo_never_needs_a_version():
    save_taxonomy("a", "b")
    history.save(
        "taxonomy", files.taxonomy_yaml(tax("a", "b")).replace("A", "Z"), "user", "d"
    )
    label_gold("a")
    history.undo("taxonomy")
    assert gold_labels() == [["a"], []]
    assert files.read_taxonomy().labels[0].description == "A"


# ---- files.approve and State.inputs (task 03)


def test_old_state_json_without_inputs_loads():
    (files.root() / "state.json").write_text('{"seeds_approved": true}')
    state = files.read_state()
    assert state.seeds_approved is True
    assert state.inputs == {}


def test_approve_sets_flag_records_inputs_and_logs(monkeypatch):
    monkeypatch.setattr(
        files, "current_inputs", lambda flag: {"prompt": "h", "f": flag}
    )
    files.approve("dev_done", 5, "Approved: Tuning loop (dev accuracy 0.920)")
    state = files.read_state()
    assert state.dev_done is True
    assert state.inputs == {"dev_done": {"prompt": "h", "f": "dev_done"}}
    (entry,) = history.entries()
    assert entry["kind"] == "approval"
    assert entry["stage"] == 5
    assert entry["flag"] == "dev_done"
    assert entry["inputs"] == {"prompt": "h", "f": "dev_done"}
    assert entry["summary"] == "Approved: Tuning loop (dev accuracy 0.920)"


def test_approve_keeps_other_flags_and_inputs(monkeypatch):
    monkeypatch.setattr(files, "current_inputs", lambda flag: {"k": flag})
    files.approve("seeds_approved", 1, "Approved: seeds")
    files.approve("taxonomy_approved", 3, "Approved: taxonomy")
    state = files.read_state()
    assert state.seeds_approved and state.taxonomy_approved
    assert state.inputs == {
        "seeds_approved": {"k": "seeds_approved"},
        "taxonomy_approved": {"k": "taxonomy_approved"},
    }


def test_approve_seam_defaults_to_no_components():
    assert files.current_inputs("seeds_approved") == {}
    files.approve("seeds_approved", 1, "Approved")
    assert files.read_state().inputs == {"seeds_approved": {}}


def test_start_new_version_clears_inputs_with_the_flags(monkeypatch):
    monkeypatch.setattr(files, "current_inputs", lambda flag: {"k": "v"})
    files.write_taxonomy(tax("a", "b"))
    files.approve("seeds_approved", 1, "s")
    files.approve("taxonomy_approved", 3, "t")
    files.approve("dev_done", 5, "d")
    files.start_new_version(tax("c", "d"))
    state = files.read_state()
    assert not (state.taxonomy_approved or state.dev_done)
    assert state.seeds_approved
    assert state.inputs == {"seeds_approved": {"k": "v"}}
