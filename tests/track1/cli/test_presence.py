"""Presence in a synced folder: one file per user and machine, only fresh ones count."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from cli import presence, serve


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("J2JME_USER", "ann")
    (tmp_path / "proj").mkdir()
    return tmp_path / "proj"


def other(project: Path, mapping: str, user: str, at: float) -> None:
    folder = project / ".j2jme/presence"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{mapping}.{user}.json").write_text(
        json.dumps({"mapping": mapping, "user": user, "at": at})
    )


def test_announcing_writes_one_file_of_my_own(project: Path) -> None:
    presence.announce(project, "orders")
    files = sorted(p.name for p in (project / ".j2jme/presence").iterdir())
    assert files == [f"orders.{presence.identity()}.json"]
    assert presence.identity().startswith("ann@")


def test_one_mapping_at_a_time(project: Path) -> None:
    presence.announce(project, "orders")
    presence.announce(project, "invoices")
    assert [p.name.split(".")[0] for p in (project / ".j2jme/presence").iterdir()] == ["invoices"]
    presence.announce(project, None)
    assert list((project / ".j2jme/presence").iterdir()) == []


def test_others_are_listed_and_I_am_not(project: Path) -> None:
    now = time.time()
    presence.announce(project, "orders")
    other(project, "orders", "bob@pc2", now - 10)
    found = presence.others(project, now)
    assert [(f["mapping"], f["user"]) for f in found] == [("orders", "bob@pc2")]
    assert 9 < found[0]["age"] < 11


def test_a_stale_or_unreadable_file_is_ignored(project: Path) -> None:
    now = time.time()
    other(project, "orders", "bob@pc2", now - presence.TTL - 1)  # closed or crashed
    (project / ".j2jme/presence/x.carl@pc3.json").write_text("{half")  # the sync is mid-file
    (project / ".j2jme/presence/y.dan@pc4.json").write_text('{"mapping": "y"}')  # no time
    assert presence.others(project, now) == []


def test_the_same_user_on_another_machine_is_somebody_else(project: Path) -> None:
    now = time.time()
    other(project, "orders", "ann@elsewhere", now)
    assert [f["user"] for f in presence.others(project, now)] == ["ann@elsewhere"]


def test_nothing_without_the_folder(project: Path) -> None:
    assert presence.others(project) == []
    presence.announce(project, None)  # nothing to remove, nothing created
    assert not (project / ".j2jme").exists()


def test_the_worker_announces_and_lists(project: Path) -> None:
    other(project, "orders", "bob@pc2", time.time())
    answer = serve.handle({"op": "presence_announce", "project": str(project), "mapping": "orders"})
    assert answer["ok"] and [e["user"] for e in answer["editing"]] == ["bob@pc2"]
    again = serve.handle({"op": "presence_list", "project": str(project)})
    assert [(e["mapping"], e["user"]) for e in again["editing"]] == [("orders", "bob@pc2")]
