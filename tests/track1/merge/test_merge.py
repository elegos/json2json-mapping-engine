"""Rule-level 3-way merge (`transpiler/merge.py`) and the git driver (`cli/merge_driver.py`)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from cli.merge_driver import install, run_driver
from transpiler.merge import MergeError, merge3, merge_texts, text_merge

ROOT = Path(__file__).resolve().parents[3]


def base() -> dict[str, Any]:
    return {
        "name": "Orders",
        "id": "orders",
        "rules": [
            {"id": "oid", "kind": "field", "field": "OrderId", "type": "str",
             "source": {"path": "$.id"}, "transform": {}},
            {"id": "cust", "kind": "object", "output": "Customer", "rules": [
                {"id": "n", "kind": "field", "field": "Name", "type": "str",
                 "source": {"path": "name"}, "transform": {}},
                {"id": "c", "kind": "field", "field": "Code", "type": "str",
                 "source": {"path": "remarks"}, "transform": {}},
            ]},
            {"id": "ver", "kind": "field", "field": "MapVersion", "type": "int",
             "source": {"constant": 27}, "transform": {}},
        ],
    }  # fmt: skip


def rule(d: dict[str, Any], *ids: str) -> dict[str, Any]:
    rules = d["rules"]
    for i in ids:
        d = next(r for r in rules if r["id"] == i)
        rules = d.get("rules", [])
    return d


def test_different_rules_do_not_conflict() -> None:
    ours, theirs = base(), base()
    rule(ours, "oid")["description"] = "mine"
    rule(theirs, "ver")["source"]["constant"] = 28
    r = merge3(base(), ours, theirs)
    assert r.clean
    assert rule(r.data, "oid")["description"] == "mine"
    assert rule(r.data, "ver")["source"]["constant"] == 28


def test_nested_rules_merge_by_id() -> None:
    ours, theirs = base(), base()
    rule(ours, "cust", "n")["source"]["path"] = "full_name"
    rule(theirs, "cust", "c")["transform"] = {"expression": "split_first(value, '|')"}
    r = merge3(base(), ours, theirs)
    assert r.clean
    assert rule(r.data, "cust", "n")["source"]["path"] == "full_name"
    assert rule(r.data, "cust", "c")["transform"]["expression"] == "split_first(value, '|')"


def test_same_field_of_same_rule_conflicts_and_keeps_ours() -> None:
    ours, theirs = base(), base()
    rule(ours, "oid")["source"]["path"] = "$.a"
    rule(theirs, "oid")["source"]["path"] = "$.b"
    r = merge3(base(), ours, theirs)
    [c] = r.conflicts
    assert c.path == "rules[oid].source.path"
    assert (c.base, c.ours, c.theirs) == ("$.id", "$.a", "$.b")
    assert rule(r.data, "oid")["source"]["path"] == "$.a"


def test_choices_settle_a_conflict() -> None:
    ours, theirs = base(), base()
    rule(ours, "oid")["source"]["path"] = "$.a"
    rule(theirs, "oid")["source"]["path"] = "$.b"
    r = merge3(base(), ours, theirs, {"rules[oid].source.path": "theirs"})
    assert r.clean
    assert rule(r.data, "oid")["source"]["path"] == "$.b"


def test_same_change_on_both_sides_is_not_a_conflict() -> None:
    ours, theirs = base(), base()
    rule(ours, "ver")["source"]["constant"] = 30
    rule(theirs, "ver")["source"]["constant"] = 30
    assert merge3(base(), ours, theirs).clean


def test_rules_added_on_both_sides_are_both_kept() -> None:
    ours, theirs = base(), base()
    new_o = {"id": "o1", "kind": "field", "field": "A", "type": "str", "transform": {}}
    new_t = {"id": "t1", "kind": "field", "field": "B", "type": "str", "transform": {}}
    ours["rules"].insert(1, new_o)
    theirs["rules"].append(new_t)
    r = merge3(base(), ours, theirs)
    assert r.clean
    assert [x["id"] for x in r.data["rules"]] == ["oid", "o1", "cust", "ver", "t1"]


def test_a_rule_deleted_on_one_side_and_untouched_on_the_other_goes() -> None:
    ours, theirs = base(), base()
    ours["rules"] = [r for r in ours["rules"] if r["id"] != "ver"]
    rule(theirs, "oid")["description"] = "d"
    r = merge3(base(), ours, theirs)
    assert r.clean
    assert [x["id"] for x in r.data["rules"]] == ["oid", "cust"]


def test_a_rule_deleted_on_one_side_and_edited_on_the_other_conflicts() -> None:
    ours, theirs = base(), base()
    ours["rules"] = [r for r in ours["rules"] if r["id"] != "ver"]
    rule(theirs, "ver")["source"]["constant"] = 99
    r = merge3(base(), ours, theirs)
    [c] = r.conflicts
    assert c.path == "rules[ver]" and c.ours_missing and not c.theirs_missing
    assert [x["id"] for x in r.data["rules"]] == ["oid", "cust"]  # ours kept


def test_a_reorder_is_kept_with_the_other_sides_edit() -> None:
    ours, theirs = base(), base()
    ours["rules"].reverse()
    rule(theirs, "oid")["description"] = "d"
    r = merge3(base(), ours, theirs)
    assert r.clean
    assert [x["id"] for x in r.data["rules"]] == ["ver", "cust", "oid"]
    assert rule(r.data, "oid")["description"] == "d"


def test_rules_without_id_are_matched_by_what_they_write() -> None:
    def mk() -> dict[str, Any]:
        return {"name": "x", "id": "x", "rules": [
            {"kind": "field", "field": "A", "type": "str", "transform": {}},
            {"kind": "field", "field": "B", "type": "str", "transform": {}},
        ]}  # fmt: skip

    ours, theirs = mk(), mk()
    ours["rules"][0]["description"] = "a"
    theirs["rules"][1]["description"] = "b"
    r = merge3(mk(), ours, theirs)
    assert r.clean
    assert [x.get("description") for x in r.data["rules"]] == ["a", "b"]


def test_top_level_keys_merge_too() -> None:
    ours, theirs = base(), base()
    ours["paths"] = {"aliases": {"m": "$.metadata"}}
    theirs["name"] = "Orders v2"
    r = merge3(base(), ours, theirs)
    assert r.clean and r.data["paths"] == {"aliases": {"m": "$.metadata"}}
    assert r.data["name"] == "Orders v2"


def test_no_common_ancestor_conflicts_only_where_they_differ() -> None:
    ours, theirs = base(), base()
    rule(theirs, "oid")["description"] = "d"
    r = merge3(None, ours, theirs)
    assert [c.path for c in r.conflicts] == []  # one side only added a key: not a clash
    rule(ours, "oid")["description"] = "other"
    assert [c.path for c in merge3(None, ours, theirs).conflicts] == ["rules[oid].description"]


def test_merge_texts_roundtrips_and_rejects_non_yaml() -> None:
    text = yaml.safe_dump(base(), sort_keys=False)
    out, conflicts = merge_texts(text, text, text)
    assert conflicts == [] and yaml.safe_load(out) == base()
    with pytest.raises(MergeError):
        merge_texts(text, "a: [", text)


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@needs_git
def test_text_merge_marks_conflicts() -> None:
    merged, clean = text_merge("a\nb\nc\n", "a\nX\nc\n", "a\nY\nc\n")
    assert not clean and "<<<<<<< ours" in merged
    merged, clean = text_merge("a\nb\nc\n", "A\nb\nc\n", "a\nb\nC\n")
    assert clean and merged == "A\nb\nC\n"


def _write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_driver_merges_in_place(tmp_path: Path) -> None:
    ours, theirs = base(), base()
    rule(ours, "oid")["description"] = "mine"
    rule(theirs, "ver")["source"]["constant"] = 28
    _write(tmp_path / "o", base())
    _write(tmp_path / "a", ours)
    _write(tmp_path / "b", theirs)
    clean, note = run_driver(tmp_path / "o", tmp_path / "a", tmp_path / "b")
    assert clean and note == ""
    merged = yaml.safe_load((tmp_path / "a").read_text())
    assert rule(merged, "oid")["description"] == "mine"
    assert rule(merged, "ver")["source"]["constant"] == 28


@needs_git
def test_driver_leaves_markers_on_a_real_conflict(tmp_path: Path) -> None:
    ours, theirs = base(), base()
    rule(ours, "oid")["source"]["path"] = "$.a"
    rule(theirs, "oid")["source"]["path"] = "$.b"
    _write(tmp_path / "o", base())
    _write(tmp_path / "a", ours)
    _write(tmp_path / "b", theirs)
    clean, note = run_driver(tmp_path / "o", tmp_path / "a", tmp_path / "b")
    assert not clean and "rules[oid].source.path" in note
    assert "<<<<<<< ours" in (tmp_path / "a").read_text()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "GIT_CONFIG_GLOBAL": os.devnull}
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@needs_git
def test_git_merge_uses_the_driver(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    assert _git(repo, "init", "-q", "-b", "main").returncode == 0
    command = f"{sys.executable} -m cli.main"
    done = install(repo, command)
    assert len(done) == 3
    assert install(repo, command)[-1].startswith("git config")  # no second .gitattributes line
    assert (repo / ".gitattributes").read_text().count("merge=j2jme") == 1

    f = repo / "orders.fn.yaml"
    _write(f, base())
    _git(repo, "add", ".")
    assert _git(repo, "commit", "-q", "-m", "base").returncode == 0
    _git(repo, "checkout", "-q", "-b", "other")
    theirs = base()
    rule(theirs, "ver")["source"]["constant"] = 28
    _write(f, theirs)
    _git(repo, "commit", "-qam", "theirs")
    _git(repo, "checkout", "-q", "main")
    ours = base()
    rule(ours, "oid")["description"] = "mine"
    _write(f, ours)
    _git(repo, "commit", "-qam", "ours")

    merged = _git(repo, "merge", "other", "-m", "merge")
    assert merged.returncode == 0, merged.stdout + merged.stderr
    data = yaml.safe_load(f.read_text())
    assert rule(data, "oid")["description"] == "mine"
    assert rule(data, "ver")["source"]["constant"] == 28
