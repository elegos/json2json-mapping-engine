"""`mapper artifacts` and `cli/artifacts_mode.py`: commit build/compiled, or have CI build it."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import artifacts_mode as am
from cli.config import MapperConfigError
from cli.main import app
from cli.project_create import GITIGNORE, create_project
from cli.serve import handle
from tests.track1.cli.test_build_cli import (
    MAPPER_TOML,
    ORDER_INPUT_SCHEMA,
    ORDER_MAPPING,
    ORDER_OUTPUT_SCHEMA,
    PING_MAPPING,
)

runner = CliRunner()

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


def _project(root: Path) -> Path:
    """A built project, committed, with the .gitignore a new project gets."""
    (root / "mappings").mkdir(parents=True)
    (root / "schemas").mkdir()
    (root / "mapper.toml").write_text(MAPPER_TOML)
    (root / "mappings" / "ping.map.py").write_text(PING_MAPPING)
    (root / "mappings" / "order_event.map.py").write_text(ORDER_MAPPING)
    for kind, schema in (("input", ORDER_INPUT_SCHEMA), ("output", ORDER_OUTPUT_SCHEMA)):
        (root / "schemas" / f"order_event_{kind}.schema.json").write_text(json.dumps(schema))
    (root / ".gitignore").write_text(GITIGNORE)
    return root


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _project(tmp_path / "repo")
    git(root, "init", "-q", "-b", "main")
    monkeypatch.chdir(root)
    assert runner.invoke(app, ["build"]).exit_code == 0
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return root


def test_a_committed_project_says_so(repo: Path) -> None:
    found = am.state(repo)
    assert found.mode == "committed" and found.git
    assert "build/compiled/manifest.json" in found.tracked
    assert len(found.tracked) == 3  # two packages and the manifest


def test_ignore_stops_committing_and_keeps_the_files(repo: Path) -> None:
    before = am.ignore(repo)
    assert before.mode == "committed" and len(before.tracked) == 3
    text = (repo / ".gitignore").read_text()
    assert "!build/compiled/" not in text and "build/compiled/\n" in text
    assert "build/*" in text  # what was there stays
    assert (repo / "build/compiled/map_ping.sql").is_file()  # on disk
    status = git(repo, "status", "--porcelain")
    assert status.count("D  build/compiled/") == 3  # the removal is staged, not committed
    assert git(repo, "log", "--oneline").count("\n") == 1
    found = am.state(repo)
    assert found.mode == "ignored" and found.tracked == ()


def test_ignore_twice_changes_nothing(repo: Path) -> None:
    am.ignore(repo)
    once = (repo / ".gitignore").read_text()
    again = am.ignore(repo)
    assert again.mode == "ignored" and again.tracked == ()
    assert (repo / ".gitignore").read_text() == once
    assert once.splitlines().count("build/compiled/") == 1  # not added again


def test_check_then_only_builds(repo: Path) -> None:
    am.ignore(repo)
    shutil.rmtree(repo / "build" / "compiled")
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0 and "git-ignored" in result.output


def test_track_puts_it_back(repo: Path) -> None:
    am.ignore(repo)
    git(repo, "commit", "-qam", "stop committing")
    before = am.track(repo)
    assert before.mode == "ignored"
    text = (repo / ".gitignore").read_text()
    assert "!build/compiled/" in text and "build/*" in text
    assert "A  build/compiled/manifest.json" in git(repo, "status", "--porcelain")
    assert am.state(repo).mode == "committed"
    assert runner.invoke(app, ["check"]).exit_code == 0


def test_track_with_a_build_rule_that_cannot_reinclude(repo: Path) -> None:
    (repo / ".gitignore").write_text("*.log\nbuild/\n")  # `build/` ignores the folder as a whole
    am.track(repo)
    text = (repo / ".gitignore").read_text()
    assert "*.log" in text and "build/*" in text and "!build/compiled/" in text
    assert am.state(repo).mode == "committed"


def test_other_lines_of_gitignore_are_kept(repo: Path) -> None:
    (repo / ".gitignore").write_text("*.log\n" + GITIGNORE + "\n# mine\nsecrets/\n")
    am.ignore(repo)
    text = (repo / ".gitignore").read_text()
    assert "*.log" in text and "secrets/" in text and "# mine" in text


def test_a_project_without_gitignore_gets_one_and_can_go_back(tmp_path: Path) -> None:
    root = _project(tmp_path / "bare")
    (root / ".gitignore").unlink()
    git(root, "init", "-q", "-b", "main")
    am.ignore(root)
    assert (root / ".gitignore").read_text().strip().endswith("build/compiled/")
    am.track(root)
    assert am.state(root).mode == "committed"
    assert not (root / ".gitignore").read_text().strip()  # nothing of ours is left


def test_a_project_inside_a_bigger_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    top = tmp_path / "mono"
    top.mkdir()
    git(top, "init", "-q", "-b", "main")
    (top / "other.txt").write_text("x")
    root = _project(top / "mappings-project")
    monkeypatch.chdir(root)
    runner.invoke(app, ["build"])
    git(top, "add", ".")
    git(top, "commit", "-qm", "base")
    assert am.state(root).tracked  # the paths are relative to the project
    am.ignore(root)
    assert (root / ".gitignore").is_file() and not (top / ".gitignore").exists()
    assert am.state(root).mode == "ignored"
    assert git(top, "ls-files", "--", "other.txt").strip() == "other.txt"  # nothing else touched


def test_not_a_repository(tmp_path: Path) -> None:
    root = _project(tmp_path / "plain")
    assert am.state(root).mode == "unknown"
    with pytest.raises(MapperConfigError, match="not a git repository"):
        am.ignore(root)
    with pytest.raises(MapperConfigError, match="not a git repository"):
        am.track(root)


def test_new_projects_come_with_the_gitignore(tmp_path: Path) -> None:
    opts = {"schema": "OWNER", "error_code": -20000, "mapping_package_prefix": "M_"}
    create_project(tmp_path / "p", "plsql", opts)
    assert (tmp_path / "p" / ".gitignore").read_text() == GITIGNORE
    other = tmp_path / "q"
    other.mkdir()
    (other / ".gitignore").write_text("mine\n")
    create_project(other, "plsql", opts)
    assert (other / ".gitignore").read_text() == "mine\n"  # an existing one is left alone


def test_the_commands(repo: Path) -> None:
    status = runner.invoke(app, ["artifacts", "status"])
    assert status.exit_code == 0 and "committed: 3 file(s)" in status.output
    done = runner.invoke(app, ["artifacts", "ignore"])
    assert done.exit_code == 0 and "3 file(s) removed from the index" in done.output
    assert "already ignored" in runner.invoke(app, ["artifacts", "ignore"]).output
    assert (
        "ignored: build/compiled is built by CI"
        in runner.invoke(app, ["artifacts", "status"]).output
    )
    back = runner.invoke(app, ["artifacts", "track"])
    assert back.exit_code == 0 and "committed again" in back.output


def test_the_commands_outside_a_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_project(tmp_path / "plain"))
    assert "nothing says either way" in runner.invoke(app, ["artifacts", "status"]).output
    refused = runner.invoke(app, ["artifacts", "ignore"])
    assert refused.exit_code == 1 and "not a git repository" in refused.output


def test_the_worker_ops(repo: Path) -> None:
    asked = handle({"op": "artifacts_state", "project": str(repo)})
    assert asked["ok"] and asked["mode"] == "committed" and len(asked["tracked"]) == 3
    done = handle({"op": "artifacts_ignore", "project": str(repo)})
    assert done["before"]["mode"] == "committed"
    assert handle({"op": "artifacts_state", "project": str(repo)})["mode"] == "ignored"
    assert handle({"op": "artifacts_track", "project": str(repo)})["ok"]
    assert handle({"op": "artifacts_state", "project": str(repo)})["mode"] == "committed"
