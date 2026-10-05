"""`build/compiled/manifest.json`: written by the build, compared by `mapper check`."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli._version import ENGINE_VERSION
from cli.main import app
from cli.manifest import compare, digest
from tests.track1.cli.test_build_cli import (
    COMPILED,
    MAPPER_TOML,
    ORDER_INPUT_SCHEMA,
    ORDER_MAPPING,
    ORDER_OUTPUT_SCHEMA,
    PING_MAPPING,
)

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "mappings").mkdir()
    (tmp_path / "schemas").mkdir()
    (tmp_path / "mapper.toml").write_text(MAPPER_TOML)
    (tmp_path / "mappings" / "ping.map.py").write_text(PING_MAPPING)
    (tmp_path / "mappings" / "order_event.map.py").write_text(ORDER_MAPPING)
    for kind, schema in (("input", ORDER_INPUT_SCHEMA), ("output", ORDER_OUTPUT_SCHEMA)):
        (tmp_path / "schemas" / f"order_event_{kind}.schema.json").write_text(json.dumps(schema))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _manifest(project: Path) -> dict:
    return json.loads((project / COMPILED / "manifest.json").read_text())


def test_the_build_writes_the_manifest(project: Path) -> None:
    assert runner.invoke(app, ["build"]).exit_code == 0
    m = _manifest(project)
    assert m["manifest"] == 1 and m["engine"] == ENGINE_VERSION and m["target"] == "plsql"
    assert set(m["sources"]) == {
        "mapper.toml",
        "mappings/ping.map.py",
        "mappings/order_event.map.py",
        "schemas/order_event_input.schema.json",
        "schemas/order_event_output.schema.json",
    }
    sql = project / COMPILED / "map_ping.sql"
    assert m["outputs"]["map_ping.sql"] == digest(sql.read_text())
    assert set(m["outputs"]) == {p.name for p in (project / COMPILED).glob("*.sql")}


def test_building_twice_gives_the_same_file(project: Path) -> None:
    runner.invoke(app, ["build"])
    first = (project / COMPILED / "manifest.json").read_text()
    runner.invoke(app, ["build"])
    assert (project / COMPILED / "manifest.json").read_text() == first


def test_the_project_functions_are_sources(project: Path) -> None:
    (project / "fn").mkdir()
    (project / "fn" / "text.fn").write_text("def f(s: str) -> str:\n    return s\n")
    runner.invoke(app, ["build"])
    assert "fn/text.fn" in _manifest(project)["sources"]


def test_a_checkout_with_crlf_hashes_the_same() -> None:
    assert digest("a\nb\n") == digest("a\r\nb\r\n") == digest(b"a\r\nb\r\n")


def test_check_fails_when_a_source_is_not_in_the_manifest(project: Path) -> None:
    runner.invoke(app, ["build"])
    (project / "fn").mkdir()
    (project / "fn" / "text.fn").write_text("def f(s: str) -> str:\n    return s\n")
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1
    assert "manifest: source fn/text.fn is not in it" in result.output


def test_check_fails_without_a_manifest(project: Path) -> None:
    runner.invoke(app, ["build"])
    (project / COMPILED / "manifest.json").unlink()
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1 and "manifest.json" in result.output


def test_a_different_engine_version_alone_is_only_a_warning(project: Path) -> None:
    runner.invoke(app, ["build"])
    path = project / COMPILED / "manifest.json"
    path.write_text(path.read_text().replace(ENGINE_VERSION, "0.0.1"))
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0, result.output
    assert "built by engine 0.0.1" in result.output  # stderr is mixed in by the runner


def test_compare_names_what_changed() -> None:
    old = {"engine": "1", "target": "plsql", "sources": {"a": "1", "b": "1"}, "outputs": {"x": "1"}}
    new = {"engine": "2", "target": "plsql", "sources": {"a": "2", "c": "1"}, "outputs": {"x": "1"}}
    problems, warnings = compare(old, new)
    assert problems == [
        "manifest: source c is not in it",
        "manifest: source b is gone",
        "manifest: source a changed",
    ]
    assert len(warnings) == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_with_the_artifacts_ignored_check_only_builds(project: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / ".gitignore").write_text("build/\n")
    result = runner.invoke(app, ["check"])  # nothing was built: not a problem here
    assert result.exit_code == 0, result.output
    assert "git-ignored" in result.output

    runner.invoke(app, ["build"])
    path = project / COMPILED / "manifest.json"
    path.write_text(path.read_text().replace(ENGINE_VERSION, "0.0.1"))
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0 and "built by engine 0.0.1" in result.output


def test_version_prints_the_engines() -> None:
    result = runner.invoke(app, ["version"])
    assert result.output.strip() == ENGINE_VERSION
