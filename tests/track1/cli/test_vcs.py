"""Git mode of the desktop tool (`cli/vcs.py`): commit = check + build, pull with rebase, the
conflicts settled with the merge engine. Real repositories: a bare remote and two clones."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cli import artifacts_mode, vcs
from cli.project_create import GITIGNORE

FIXTURE = Path(__file__).resolve().parents[3] / "desktop/fixtures/tour-project"
ORDERS = "mappings/functional/orders.fn.yaml"
TEXT_FN = "fn/text.fn"

# the fixtures (git as test scaffolding, in `git()`) need the binary; the cases run on both backends
pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed"),
    pytest.mark.usefixtures("backend"),
]


@pytest.fixture(autouse=True)
def _git_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def git(where: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(where), *args], capture_output=True, text=True, check=True
    )
    return done.stdout


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    """Two clones of one remote, both with the tour project built and committed."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    a = tmp_path / "a"
    shutil.copytree(FIXTURE, a, ignore=shutil.ignore_patterns("build"))
    (a / ".gitignore").write_text(GITIGNORE)
    git(a, "init", "-q", "-b", "main")
    git(a, "remote", "add", "origin", str(remote))
    vcs.ensure_driver(a)  # what the tool does on opening: the attributes travel with the repository
    assert vcs.commit(a, "first")["committed"]  # builds, commits the sources and build/compiled
    git(a, "push", "-q", "-u", "origin", "main")
    subprocess.run(["git", "clone", "-q", str(remote), str(tmp_path / "b")], check=True)
    return a, tmp_path / "b"


def edit(project: Path, old: str, new: str, file: str = ORDERS) -> None:
    path = project / file
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new, 1))


def subject(project: Path) -> str:
    return git(project, "log", "-1", "--format=%s").strip()


def files_of_head(project: Path) -> list[str]:
    return git(project, "show", "--name-only", "--format=", "HEAD").split()


# --- state, summary ---------------------------------------------------------------------------


def test_state_of_a_clean_and_a_changed_project(pair: tuple[Path, Path]) -> None:
    a, _ = pair
    info = vcs.state(a)
    assert (info["branch"], info["upstream"], info["ahead"], info["behind"]) == (
        "main",
        "origin/main",
        0,
        0,
    )
    assert info["changes"] == [] and not info["rebasing"] and info["conflicts"] == []
    edit(a, "The order id, unchanged.", "The id.")
    (a / "fn" / "new.fn").write_text("def f(s: str) -> str:\n    return s\n")
    changes = {c["path"]: c for c in vcs.state(a)["changes"]}
    assert changes[ORDERS]["status"] == "M" and not changes[ORDERS]["generated"]
    assert changes["fn/new.fn"]["status"] == "?"


def test_state_without_git_or_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    assert vcs.state(tmp_path) == {"git": True, "repo": False}
    if backend == "git":  # the helper does not need git on the PATH: that is its point
        monkeypatch.setenv("PATH", "")
        assert vcs.state(tmp_path) == {"git": False, "repo": False}


def test_neither_git_nor_the_helper_is_no_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("J2JME_GIT_BACKEND", raising=False)
    monkeypatch.delenv("J2JME_GIT_HELPER", raising=False)
    assert vcs.state(tmp_path) == {"git": False, "repo": False}
    with pytest.raises(vcs.VcsError, match="git is not installed"):
        vcs.commit(tmp_path)


def test_diff_rules_names_the_rules_and_the_groups() -> None:
    old = {
        "rules": [
            {"id": "a", "source": {"path": "$.a"}, "description": "d"},
            {"id": "gone"},
            {
                "id": "obj",
                "kind": "object",
                "rules": [{"id": "n", "transform": {"expression": "x"}}],
            },
        ]
    }
    new = {
        "rules": [
            {"id": "a", "source": {"path": "$.b"}, "description": "e"},
            {"id": "added"},
            {
                "id": "obj",
                "kind": "object",
                "rules": [{"id": "n", "transform": {"expression": "y"}}],
            },
        ]
    }
    assert vcs.diff_rules(old, new) == {
        "added": ["added"],
        "removed": ["gone"],
        "changed": ["a (source, description)", "obj.n (transform)"],
    }


# --- commit -----------------------------------------------------------------------------------


def test_commit_builds_and_commits_sources_and_generated_files_together(
    pair: tuple[Path, Path],
) -> None:
    a, _ = pair
    edit(a, "The order id, unchanged.", "The id of the order.")
    done = vcs.commit(a, "Reword the order id\n\nThe business asked for it.")
    assert done["committed"] and done["subject"] == "Reword the order id" and done["problems"] == []
    names = files_of_head(a)
    assert ORDERS in names and "build/compiled/manifest.json" in names  # one commit, both
    body = git(a, "log", "-1", "--format=%b")
    assert "The business asked for it." in body
    assert "orders: changed: oid (description)" in body
    assert vcs.state(a)["changes"] == []


def test_commit_with_nothing_changed(pair: tuple[Path, Path]) -> None:
    a, _ = pair
    done = vcs.commit(a, "again")
    assert done["ok"] and done["committed"] is False and done["message"] == "nothing to commit"


def test_a_failing_check_blocks_the_commit(pair: tuple[Path, Path]) -> None:
    a, _ = pair
    head = git(a, "rev-parse", "HEAD")
    edit(a, 'lookup(value, @countryCurrency, "N/A")', "no_such_function(value)")
    done = vcs.commit(a, "break it")
    assert done["ok"] is False and done["blocked"] and done["problems"]
    assert any("no_such_function" in p for p in done["problems"])
    assert git(a, "rev-parse", "HEAD") == head


def test_wip_commits_the_sources_without_generated_files(pair: tuple[Path, Path]) -> None:
    a, _ = pair
    edit(a, 'lookup(value, @countryCurrency, "N/A")', "no_such_function(value)")
    done = vcs.commit(a, "half way", wip=True)
    assert done["committed"] and done["subject"] == "WIP: half way" and done["problems"]
    assert files_of_head(a) == [ORDERS]
    assert subject(a) == "WIP: half way"


def test_only_the_projects_paths_are_committed(pair: tuple[Path, Path]) -> None:
    a, _ = pair
    (a / "unrelated.txt").write_text("not the project's")
    git(a, "add", "unrelated.txt")  # staged by someone else
    edit(a, "The order id, unchanged.", "The id.")
    assert vcs.commit(a, "x")["committed"]
    assert "unrelated.txt" not in files_of_head(a)
    assert "A  unrelated.txt" in git(a, "status", "--porcelain")  # still staged, not lost


def test_with_the_artifacts_ignored_none_are_built_or_committed(pair: tuple[Path, Path]) -> None:
    a, _ = pair
    artifacts_mode.ignore(a)
    git(a, "commit", "-qam", "stop committing the artifacts")
    edit(a, "The order id, unchanged.", "The id.")
    assert vcs.commit(a, "x")["committed"]
    assert files_of_head(a) == [ORDERS]


def test_a_commit_is_refused_while_a_rebase_is_stopped(pair: tuple[Path, Path]) -> None:
    a, b = pair
    edit(a, "The order id, unchanged.", "From A.")
    vcs.commit(a, "a")
    git(a, "push", "-q")
    edit(b, "The order id, unchanged.", "From B.")
    vcs.commit(b, "b")
    assert vcs.pull(b)["ok"] is False
    with pytest.raises(vcs.VcsError, match="rebase is in progress"):
        vcs.commit(b, "meanwhile")


# --- pull, conflicts --------------------------------------------------------------------------


def test_pull_brings_in_the_other_clones_work(pair: tuple[Path, Path]) -> None:
    a, b = pair
    edit(a, "The order id, unchanged.", "From A.")
    vcs.commit(a, "a")
    git(a, "push", "-q")
    edit(b, "Currency of the order's country; N/A when the country is unknown.", "From B.")
    vcs.commit(b, "b")
    assert vcs.state(b)["ahead"] == 1
    git(b, "fetch", "-q")
    assert vcs.state(b)["behind"] == 1
    assert vcs.pull(b) == {"ok": True, "conflicts": []}
    text = (b / ORDERS).read_text()
    assert "From A." in text and "From B." in text
    assert vcs.state(b)["ahead"] == 1 and vcs.state(b)["behind"] == 0
    assert vcs.state(b)["changes"] == []


def test_pull_with_a_dirty_tree_keeps_the_work_in_progress(
    pair: tuple[Path, Path], backend: str
) -> None:
    a, b = pair
    edit(a, "The order id, unchanged.", "From A.")
    vcs.commit(a, "a")
    git(a, "push", "-q")
    edit(b, "Currency of the order's country; N/A when the country is unknown.", "Unsaved in B.")
    if backend == "gix":
        # gitoxide has no stash: a file the pull changes must not hold unsaved work
        with pytest.raises(vcs.VcsError, match="commit or discard your changes first"):
            vcs.pull(b)
        assert "Unsaved in B." in (b / ORDERS).read_text()
        assert not vcs.state(b)["rebasing"]
        return
    assert vcs.pull(b)["ok"]
    text = (b / ORDERS).read_text()
    assert "From A." in text and "Unsaved in B." in text


def test_a_file_the_pull_does_not_touch_keeps_its_unsaved_work(pair: tuple[Path, Path]) -> None:
    a, b = pair
    edit(a, "The order id, unchanged.", "From A.")
    vcs.commit(a, "a")
    git(a, "push", "-q")
    edit(b, "parts = s.split()", "parts = s.strip().split()", TEXT_FN)  # not what the pull changes
    (b / "fn" / "brand_new.fn").write_text("def f(s: str) -> str:\n    return s\n")
    git(b, "add", "fn/brand_new.fn")  # staged by someone, and not part of the pull either
    assert vcs.pull(b)["ok"]
    assert "From A." in (b / ORDERS).read_text()
    assert "s.strip().split()" in (b / TEXT_FN).read_text()
    assert "A  fn/brand_new.fn" in git(b, "status", "--porcelain")


def test_adjacent_edits_of_one_rule_are_settled_by_the_tool(pair: tuple[Path, Path]) -> None:
    """Two edits of neighbouring lines of a rule: a text merge calls it a clash; no rule field
    changed on both sides, so the rule-level merge settles it (git by its driver, gitoxide by the
    tool), and nobody is asked."""
    a, b = pair
    edit(a, "    needs_review: true\n", "    needs_review: false\n")
    vcs.commit(a, "a")
    git(a, "push", "-q")
    edit(b, "    notes: 'functional: confirmed", "    notes: 'functional: reconfirmed")
    assert vcs.commit(b, "b")["committed"]
    done = vcs.pull(b)
    assert done == {"ok": True, "conflicts": []}, done
    text = (b / ORDERS).read_text()
    assert "needs_review: false" in text and "reconfirmed with the business" in text
    assert not vcs.state(b)["rebasing"] and vcs.state(b)["changes"] == []


def test_a_conflict_is_listed_with_both_values_and_settled(pair: tuple[Path, Path]) -> None:
    a, b = pair
    edit(a, "The order id, unchanged.", "From A.")
    vcs.commit(a, "a")
    git(a, "push", "-q")
    edit(b, "The order id, unchanged.", "From B.")
    vcs.commit(b, "b")

    pulled = vcs.pull(b)
    assert pulled["ok"] is False and pulled["conflicts"] == [ORDERS]
    assert vcs.state(b)["rebasing"]

    listed = vcs.conflicts(b)
    # the generated files conflict too (their hashes): they are listed, and regenerated
    assert [c["kind"] for c in listed if c["file"].startswith("build/compiled/")] == ["generated"]
    [found] = [c for c in listed if c["kind"] != "generated"]
    assert found["file"] == ORDERS and found["kind"] == "rules"
    [item] = found["items"]
    assert item["path"] == "rules[oid].description"
    assert (item["base"], item["mine"], item["remote"]) == (
        "The order id, unchanged.",
        "From B.",
        "From A.",
    )

    with pytest.raises(vcs.VcsError, match="still to choose"):
        vcs.resolve(b, ORDERS, {})
    done = vcs.resolve(b, ORDERS, {"rules[oid].description": "mine"})
    assert done == {"ok": True, "conflicts": [], "done": True}
    assert "From B." in (b / ORDERS).read_text() and "From A." not in (b / ORDERS).read_text()
    assert not vcs.state(b)["rebasing"] and vcs.state(b)["ahead"] == 1
    assert subject(b) == "b"  # the commit was replayed, history stays linear
    assert vcs.state(b)["changes"] == []  # generated files were regenerated, not left conflicted


def test_the_other_side_can_be_chosen(pair: tuple[Path, Path]) -> None:
    a, b = pair
    edit(a, "The order id, unchanged.", "From A.")
    vcs.commit(a, "a")
    git(a, "push", "-q")
    edit(b, "The order id, unchanged.", "From B.")
    vcs.commit(b, "b")
    vcs.pull(b)
    done = vcs.resolve(b, ORDERS, {"rules[oid].description": "remote"})
    assert done["done"]
    assert "From A." in (b / ORDERS).read_text()


def test_generated_files_are_regenerated_not_merged(pair: tuple[Path, Path]) -> None:
    a, b = pair
    edit(a, "The order id, unchanged.", "From A.")
    vcs.commit(a, "a")
    git(a, "push", "-q")
    edit(b, "Currency of the order's country; N/A when the country is unknown.", "From B.")
    vcs.commit(b, "b")
    # both commits changed manifest.json (the hash of the mapping): git cannot merge that, the
    # sources it can, so the pull regenerates and carries on by itself
    assert vcs.pull(b) == {"ok": True, "conflicts": []}
    assert vcs.state(b)["conflicts"] == [] and not vcs.state(b)["rebasing"]
    assert "<<<<<<<" not in (b / "build/compiled/manifest.json").read_text()
    assert artifacts_mode.state(b).mode == "committed"
    # the regenerated manifest is the one of the merged sources
    assert vcs.state(b)["changes"] == []


def test_abort_gives_back_the_branch_as_it_was(pair: tuple[Path, Path]) -> None:
    a, b = pair
    edit(a, "The order id, unchanged.", "From A.")
    vcs.commit(a, "a")
    git(a, "push", "-q")
    edit(b, "The order id, unchanged.", "From B.")
    vcs.commit(b, "b")
    mine = git(b, "rev-parse", "HEAD")
    vcs.pull(b)
    assert vcs.abort(b) == {"ok": True}
    assert git(b, "rev-parse", "HEAD") == mine and not vcs.state(b)["rebasing"]
    assert "From B." in (b / ORDERS).read_text()
    with pytest.raises(vcs.VcsError, match="no rebase"):
        vcs.abort(b)


def test_a_conflict_in_a_function_is_settled_by_function(pair: tuple[Path, Path]) -> None:
    a, b = pair
    edit(a, "parts = s.split()", "parts = s.strip().split()", TEXT_FN)
    vcs.commit(a, "a")
    git(a, "push", "-q")
    edit(b, "parts = s.split()", "parts = s.split(None, 5)", TEXT_FN)
    vcs.commit(b, "b")
    assert vcs.pull(b)["conflicts"] == [TEXT_FN]
    [found] = [c for c in vcs.conflicts(b) if c["kind"] != "generated"]
    assert found["kind"] == "functions" and [i["path"] for i in found["items"]] == [
        "functions[first_word]"
    ]
    assert vcs.resolve(b, TEXT_FN, {"functions[first_word]": "mine"})["done"]
    assert "split(None, 5)" in (b / TEXT_FN).read_text()


def test_a_file_the_tool_cannot_settle(pair: tuple[Path, Path]) -> None:
    a, b = pair
    notes = "lookups/notes.txt"
    for repo, text in ((a, "A\n"), (b, "B\n")):
        (repo / "lookups").mkdir(exist_ok=True)
        (repo / notes).write_text(text)
    vcs.commit(a, "a")
    git(a, "push", "-q")
    vcs.commit(b, "b")
    assert vcs.pull(b)["conflicts"] == [notes]
    [found] = vcs.conflicts(b)
    assert found["kind"] == "text" and found["items"] == []
    with pytest.raises(vcs.VcsError, match="not a file the tool can settle"):
        vcs.resolve(b, notes, {})
    vcs.abort(b)


def test_pull_without_an_upstream_and_push(tmp_path: Path, pair: tuple[Path, Path]) -> None:
    a, b = pair
    lonely = tmp_path / "lonely"
    shutil.copytree(a, lonely, ignore=shutil.ignore_patterns(".git"))
    git(lonely, "init", "-q", "-b", "main")
    with pytest.raises(vcs.VcsError, match="no upstream"):
        vcs.pull(lonely)
    edit(a, "The order id, unchanged.", "From A.")
    vcs.commit(a, "a")
    assert vcs.push(a) == {"ok": True}
    assert vcs.pull(b)["ok"] and "From A." in (b / ORDERS).read_text()


def test_not_a_repository(tmp_path: Path) -> None:
    with pytest.raises(vcs.VcsError, match="not in a git repository"):
        vcs.commit(tmp_path)
    with pytest.raises(vcs.VcsError, match="not in a git repository"):
        vcs.pull(tmp_path)


def test_the_worker_ops(pair: tuple[Path, Path]) -> None:
    from cli.serve import handle

    a, b = pair
    assert handle({"op": "vcs_state", "project": str(a)})["branch"] == "main"
    edit(a, "The order id, unchanged.", "From A.")
    done = handle({"op": "vcs_commit", "project": str(a), "notes": "reword"})
    assert done["committed"] and done["subject"] == "reword"
    assert handle({"op": "vcs_push", "project": str(a)}) == {"ok": True}
    edit(b, "The order id, unchanged.", "From B.")
    handle({"op": "vcs_commit", "project": str(b), "notes": "mine"})
    pulled = handle({"op": "vcs_pull", "project": str(b)})
    assert pulled["ok"] is False and pulled["conflicts"] == [ORDERS]
    files = handle({"op": "vcs_conflicts", "project": str(b)})["files"]
    assert any(f["kind"] == "rules" for f in files)
    resolved = handle(
        {
            "op": "vcs_resolve",
            "project": str(b),
            "file": ORDERS,
            "choices": {"rules[oid].description": "remote"},
        }
    )
    assert resolved["done"] is True
    assert "From A." in (b / ORDERS).read_text()
    assert "lines" in handle({"op": "vcs_summary", "project": str(b)})
    git(b, "reset", "-q", "--hard", "HEAD~1")  # to have something to abort
    edit(b, "The order id, unchanged.", "From B2.")
    handle({"op": "vcs_commit", "project": str(b), "notes": "again"})
    edit(a, "From A.", "From A2.")
    handle({"op": "vcs_commit", "project": str(a), "notes": "a2"})
    handle({"op": "vcs_push", "project": str(a)})
    assert handle({"op": "vcs_pull", "project": str(b)})["ok"] is False
    assert handle({"op": "vcs_abort", "project": str(b)}) == {"ok": True}
