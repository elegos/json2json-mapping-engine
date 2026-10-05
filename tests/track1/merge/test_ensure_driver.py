"""The merge driver installed by the tool, quietly (`cli/merge_driver.py`: `ensure`)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from cli import merge_driver as md
from cli import vcs

# the fixtures (git as test scaffolding, in `git()`) need the binary; the cases run on both backends
pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed"),
    pytest.mark.usefixtures("backend"),
]

RULES = """\
rules:
- id: r1
  description: one
  type: str
- id: r2
  description: two
  type: str
"""


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


def git_driver_only() -> None:
    """A case about git's own use of the driver: gitoxide has none (see `merge_driver.ensure`)."""
    if os.environ.get("J2JME_GIT_BACKEND") != "git":
        pytest.skip("the git backend installs the merge driver; gitoxide has none")


def git(where: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(where), *args], capture_output=True, text=True, check=check
    )


def config(where: Path) -> str:
    return git(
        where, "config", "--local", "--get", "merge.j2jme.driver", check=False
    ).stdout.strip()


def test_ensure_installs_quietly_and_only_once(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "main")
    git_backend = os.environ.get("J2JME_GIT_BACKEND") == "git"
    assert md.ensure(tmp_path) == {"installed": git_backend, "changed": True}
    # the attributes travel with the repository, whoever uses them; the command is the clone's own
    attrs = (tmp_path / ".gitattributes").read_text().splitlines()
    assert attrs == ["*.fn.yaml merge=j2jme", "*.fn merge=j2jme"]
    assert config(tmp_path) == (md.app_driver_line() if git_backend else "")
    assert md.ensure(tmp_path) == {"installed": git_backend, "changed": False}


def test_gitoxide_takes_a_driver_left_by_git_away(tmp_path: Path) -> None:
    """gitoxide stops the whole merge when a driver exits non-zero (a conflict, for git)."""
    if os.environ.get("J2JME_GIT_BACKEND") != "gix":
        pytest.skip("about the gitoxide backend")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "--local", "merge.j2jme.driver", "false")
    git(tmp_path, "config", "--local", "merge.j2jme.name", "J2JME")
    git(tmp_path, "config", "--local", "user.name", "someone")
    assert md.ensure(tmp_path) == {"installed": False, "changed": True}
    assert config(tmp_path) == ""
    assert git(tmp_path, "config", "--local", "--get", "user.name").stdout.strip() == "someone"


def test_ensure_rewrites_a_command_that_names_another_install(tmp_path: Path) -> None:
    git_driver_only()
    git(tmp_path, "init", "-q", "-b", "main")
    md.ensure(tmp_path, md.app_driver_line(python="/tmp/.mount_old/python3"))
    assert "/tmp/.mount_old/python3" in config(tmp_path)
    assert md.ensure(tmp_path) == {"installed": True, "changed": True}  # an AppImage mounts anew
    assert "/tmp/.mount_old" not in config(tmp_path)
    assert (tmp_path / ".gitattributes").read_text().count("merge=j2jme") == 2  # not repeated


def test_ensure_adds_a_missing_attribute_and_keeps_the_others(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".gitattributes").write_text("*.png binary\n")
    md.ensure(tmp_path)
    assert (tmp_path / ".gitattributes").read_text().splitlines() == [
        "*.png binary",
        "*.fn.yaml merge=j2jme",
        "*.fn merge=j2jme",
    ]


def test_ensure_does_nothing_outside_a_repository_or_without_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert md.ensure(tmp_path) == {"installed": False, "changed": False}
    assert not (tmp_path / ".gitattributes").exists()
    if os.environ.get("J2JME_GIT_BACKEND") == "git":  # the helper needs no git on the PATH
        monkeypatch.setenv("PATH", "")
        assert md.ensure(tmp_path) == {"installed": False, "changed": False}


def _commit(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)


def _branches(repo: Path, rel: str, ours: str, theirs: str) -> None:
    """`rel` committed as RULES, then `main` and `other` each changing it."""
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(RULES)
    _commit(repo, "base")
    git(repo, "checkout", "-q", "-b", "other")
    (repo / rel).write_text(RULES.replace("description: one", theirs))
    _commit(repo, "theirs")
    git(repo, "checkout", "-q", "main")
    (repo / rel).write_text(RULES.replace("  type: str\n- id: r2", ours + "\n- id: r2", 1))
    _commit(repo, "ours")


def test_the_line_the_tool_writes_merges_adjacent_edits_that_git_alone_cannot(
    tmp_path: Path,
) -> None:
    git_driver_only()
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    md.ensure(repo)
    _commit(repo, "attributes")
    # one side edits a line of a rule, the other the next line of it: git alone calls it a clash
    _branches(repo, "x.fn.yaml", "  type: int", "description: uno")
    done = git(repo, "merge", "-q", "other", "-m", "merge", check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    first = yaml.safe_load((repo / "x.fn.yaml").read_text())["rules"][0]
    assert (first["description"], first["type"]) == ("uno", "int")


def test_a_project_folder_only_gets_the_driver_in_its_own_paths(tmp_path: Path) -> None:
    git_driver_only()
    mono = tmp_path / "mono"
    project = mono / "mappings-project"
    project.mkdir(parents=True)
    git(mono, "init", "-q", "-b", "main")
    md.ensure(project)  # the project is a folder of a bigger repository
    assert (project / ".gitattributes").is_file() and not (mono / ".gitattributes").exists()
    _commit(mono, "attributes")

    # a file elsewhere in the repository: git's own merge, which calls adjacent edits a conflict
    _branches(mono, "other-team/y.fn.yaml", "  type: int", "description: uno")
    git(mono, "checkout", "-q", "main")
    clash = git(mono, "merge", "-q", "other", "-m", "merge", check=False)
    assert clash.returncode != 0
    git(mono, "merge", "--abort")

    # the same edits in the project's folder merge by rule
    git(mono, "checkout", "-q", "-B", "main", "HEAD~2")  # back to the base of the first test
    git(mono, "branch", "-q", "-D", "other")
    _branches(mono, "mappings-project/z.fn.yaml", "  type: int", "description: uno")
    done = git(mono, "merge", "-q", "other", "-m", "merge", check=False)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_dead_interpreter_falls_back_to_gits_own_merge(tmp_path: Path) -> None:
    git_driver_only()
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    md.ensure(repo, md.app_driver_line(python="/nonexistent/python3"))
    _commit(repo, "attributes")
    (repo / "t.fn").write_text("a\nb\nc\nd\ne\n")
    _commit(repo, "base")
    git(repo, "checkout", "-q", "-b", "other")
    (repo / "t.fn").write_text("a\nb\nc\nd\nE\n")
    _commit(repo, "theirs")
    git(repo, "checkout", "-q", "main")
    (repo / "t.fn").write_text("A\nb\nc\nd\ne\n")
    _commit(repo, "ours")
    done = git(repo, "merge", "-q", "other", "-m", "merge", check=False)
    assert done.returncode == 0  # git merged the two lines itself
    assert (repo / "t.fn").read_text() == "A\nb\nc\nd\nE\n"

    git(repo, "checkout", "-q", "-B", "main", "HEAD~2")
    git(repo, "checkout", "-q", "other")
    git(repo, "reset", "-q", "--hard", "HEAD")
    (repo / "t.fn").write_text("a\nb\nc\nd\nX\n")
    _commit(repo, "theirs2")
    git(repo, "checkout", "-q", "main")
    (repo / "t.fn").write_text("a\nb\nc\nd\nY\n")
    _commit(repo, "ours2")
    clash = git(repo, "merge", "-q", "other", "-m", "merge", check=False)
    assert clash.returncode != 0
    assert "<<<<<<<" in (repo / "t.fn").read_text()  # the markers git would have made


def test_pull_installs_the_driver_by_itself(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "remote", "add", "origin", str(remote))
    (repo / "mapper.toml").write_text("")
    _commit(repo, "base")
    git(repo, "push", "-q", "-u", "origin", "main")
    assert config(repo) == ""
    vcs.pull(repo)
    expected = md.app_driver_line() if os.environ.get("J2JME_GIT_BACKEND") == "git" else ""
    assert config(repo) == expected
    assert "merge=j2jme" in (repo / ".gitattributes").read_text()
