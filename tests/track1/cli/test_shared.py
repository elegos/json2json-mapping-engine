"""Shared-folder mode: the base per user, the merge when the disk changed, conflict copies."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from cli import fn_files, serve, shared

FIXTURE = Path(__file__).resolve().parents[3] / "desktop/fixtures/tour-project"
ORDERS = "mappings/functional/orders.fn.yaml"
TEXT_FN = "fn/text.fn"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The tour project in a folder, and this user's base folder (outside it)."""
    folder = tmp_path / "OneDrive" / "proj"
    shutil.copytree(FIXTURE, folder, ignore=shutil.ignore_patterns("build"))
    monkeypatch.setenv("J2JME_BASE_DIR", str(tmp_path / "bases"))
    return folder


def edit(project: Path, old: str, new: str, file: str = ORDERS) -> str:
    """The text of `file` with one change, not written."""
    text = (project / file).read_text()
    assert old in text, old
    return text.replace(old, new, 1)


def test_nothing_happens_without_a_base_folder(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("J2JME_BASE_DIR")
    shared.seen(project, ORDERS)
    assert shared.base_text(ORDERS) is None
    assert shared.prepare(project, ORDERS, "anything")["state"] == "same"


def test_a_file_never_seen_is_saved_as_it_is(project: Path) -> None:
    assert shared.prepare(project, ORDERS, edit(project, "unchanged.", "kept."))["state"] == "same"


def test_the_disk_as_it_was_seen_is_saved_as_it_is(project: Path) -> None:
    shared.seen(project, ORDERS)
    mine = edit(project, "unchanged.", "kept.")
    assert shared.prepare(project, ORDERS, mine)["state"] == "same"


def test_edits_of_different_rules_merge(project: Path) -> None:
    shared.seen(project, ORDERS)
    mine = edit(project, "The order id, unchanged.", "The id of the order.")
    # somebody else's version arrives through the sync
    (project / ORDERS).write_text(edit(project, "a constant.", "a fixed number."))
    answer = shared.prepare(project, ORDERS, mine)
    assert answer["state"] == "merged"
    assert "The id of the order." in answer["text"] and "a fixed number." in answer["text"]


def test_the_same_field_changed_on_both_sides_is_a_conflict_to_settle(project: Path) -> None:
    shared.seen(project, ORDERS)
    mine = edit(project, "The order id, unchanged.", "Mine.")
    (project / ORDERS).write_text(edit(project, "The order id, unchanged.", "Theirs."))
    answer = shared.prepare(project, ORDERS, mine)
    assert answer["state"] == "conflict" and answer["kind"] == "rules"
    (item,) = answer["items"]
    assert (item["mine"], item["remote"]) == ("Mine.", "Theirs.")
    keep_mine = shared.settle(project, ORDERS, mine, {item["path"]: "mine"})
    keep_theirs = shared.settle(project, ORDERS, mine, {item["path"]: "remote"})
    assert "Mine." in keep_mine["text"] and "Theirs." not in keep_mine["text"]
    assert "Theirs." in keep_theirs["text"] and "Mine." not in keep_theirs["text"]


def test_a_choice_left_out_is_refused(project: Path) -> None:
    shared.seen(project, ORDERS)
    mine = edit(project, "The order id, unchanged.", "Mine.")
    (project / ORDERS).write_text(edit(project, "The order id, unchanged.", "Theirs."))
    with pytest.raises(shared.merge_items.Unsettled):
        shared.settle(project, ORDERS, mine, {})


def test_function_files_merge_function_by_function(project: Path) -> None:
    shared.seen(project, TEXT_FN)
    mine = (project / TEXT_FN).read_text() + "\n\ndef mine(s: str) -> str:\n    return s\n"
    (project / TEXT_FN).write_text(
        (project / TEXT_FN).read_text() + "\n\ndef theirs(s: str) -> str:\n    return s\n"
    )
    answer = shared.prepare(project, TEXT_FN, mine)
    assert answer["state"] == "merged"
    assert "def mine" in answer["text"] and "def theirs" in answer["text"]
    assert "def first_word" in answer["text"]


def test_reading_and_saving_through_the_tool_keep_the_base(project: Path) -> None:
    fn_files.read_file(project, "text")
    assert shared.base_text(TEXT_FN) == (project / TEXT_FN).read_text()
    fn_files.write_file(project, "text", "def f(s: str) -> str:\n    return s\n")
    assert shared.base_text(TEXT_FN) == "def f(s: str) -> str:\n    return s\n"
    assert [p.name for p in (project / "fn").iterdir() if p.suffix == ".tmp"] == []


def test_scan_lists_what_changed_on_disk(project: Path) -> None:
    shared.seen(project, ORDERS)
    shared.seen(project, TEXT_FN)
    assert shared.scan(project) == {"changed": [], "copies": []}
    (project / TEXT_FN).write_text("def g(s: str) -> str:\n    return s\n")
    assert shared.scan(project)["changed"] == [TEXT_FN]


def test_conflict_copies_are_recognised_by_their_name(project: Path) -> None:
    orders = project / ORDERS
    for name in (
        "orders-LAPTOP-7.fn.yaml",
        "orders-PC.fn.yaml",
        "orders (1).fn.yaml",
        "orders (Ann's conflicted copy 2026-10-01).fn.yaml",
    ):
        (project / "mappings/functional" / name).write_text(orders.read_text())
    found = {c["copy"]: c["original"] for c in shared.scan(project)["copies"]}
    assert set(found) == {
        "mappings/functional/orders-LAPTOP-7.fn.yaml",  # a Windows machine name often has a dash
        "mappings/functional/orders-PC.fn.yaml",
        "mappings/functional/orders (1).fn.yaml",
        "mappings/functional/orders (Ann's conflicted copy 2026-10-01).fn.yaml",
    }
    assert set(found.values()) == {ORDERS}


def test_a_copy_merges_into_its_original_and_goes(project: Path) -> None:
    shared.seen(project, ORDERS)  # what both users started from
    copy = "mappings/functional/orders-PC.fn.yaml"
    (project / copy).write_text(edit(project, "a constant.", "a fixed number."))
    (project / ORDERS).write_text(edit(project, "The order id, unchanged.", "The id."))
    answer = shared.merge_copy(project, copy)
    assert answer["state"] == "merged" and answer["original"] == ORDERS
    done = shared.settle_copy(project, copy, {})
    assert not (project / copy).exists()
    on_disk = (project / ORDERS).read_text()
    assert "The id." in on_disk and "a fixed number." in on_disk and on_disk == done["text"]
    assert shared.base_text(ORDERS) == on_disk


def test_a_copy_can_be_thrown_away(project: Path) -> None:
    copy = project / "fn/text-PC.fn"
    copy.write_text("def x() -> int:\n    return 1\n")
    shared.discard_copy(project, "fn/text-PC.fn")
    assert not copy.exists()
    with pytest.raises(ValueError, match="not a conflict copy"):
        shared.discard_copy(project, TEXT_FN)


def test_the_worker_serves_the_shared_ops(project: Path, tmp_path: Path) -> None:
    bases = str(tmp_path / "other-bases")
    seen = serve.handle(
        {"op": "shared_seen", "project": str(project), "file": ORDERS, "base_dir": bases}
    )
    assert seen["ok"] is True
    (project / ORDERS).write_text(edit(project, "a constant.", "a fixed number."))
    scan: dict[str, Any] = serve.handle(
        {"op": "shared_scan", "project": str(project), "base_dir": bases}
    )
    assert scan["changed"] == [ORDERS]
    mine = edit(project, "The order id, unchanged.", "The id.")
    merged = serve.handle(
        {
            "op": "shared_prepare",
            "project": str(project),
            "file": ORDERS,
            "text": mine,
            "base_dir": bases,
        }
    )
    assert merged["state"] == "merged" and merged["tree"]["id"] == "orders"
