"""`[project] engine` of mapper.toml against the running engine (`cli/engine_version.py`)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import engine_version as ev
from cli import project_config
from cli._version import ENGINE_VERSION
from cli.config import MapperConfigError, load_config
from cli.main import app
from cli.project_create import create_project
from cli.serve import handle
from tests.track1.cli.test_build_cli import MAPPER_TOML, PING_MAPPING

runner = CliRunner()


@pytest.mark.parametrize(
    ("a", "b", "order"),
    [
        ("1.2.3", "1.2.3", 0),
        ("1.2.3", "1.2.4", -1),
        ("1.10.0", "1.9.9", 1),
        ("2.0.0", "1.99.99", 1),
        ("1.0.0-beta1", "1.0.0", -1),  # a release is newer than its pre-releases
        ("1.0.0", "1.0.0-rc.1", 1),
        ("1.0.0-alpha", "1.0.0-beta", -1),
        ("1.0.0-beta.2", "1.0.0-beta.11", -1),  # numeric identifiers compare as numbers
        ("1.0.0-1", "1.0.0-alpha", -1),  # numeric before alphanumeric
        ("1.0.0-alpha", "1.0.0-alpha.1", -1),  # fewer identifiers, older
        ("1.0.0-beta1", "1.0.0-beta1", 0),
    ],
)
def test_versions_are_ordered_as_semver_does(a: str, b: str, order: int) -> None:
    assert ev.compare(a, b) == order
    assert ev.compare(b, a) == -order


@pytest.mark.parametrize("bad", ["1.2", "v1.2.3", "01.2.3", "1.2.3+build", "latest", ""])
def test_what_is_not_a_version_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="not a version"):
        ev.parse(bad)


def _project(tmp_path: Path, engine: str | None) -> Path:
    line = f'engine = "{ENGINE_VERSION}"\n'
    assert line in MAPPER_TOML
    text = MAPPER_TOML.replace(line, "" if engine is None else f'engine = "{engine}"\n')
    (tmp_path / "mapper.toml").write_text(text)
    (tmp_path / "mappings").mkdir(exist_ok=True)
    (tmp_path / "mappings" / "ping.map.py").write_text(PING_MAPPING)
    return tmp_path


def test_status_names_what_the_tool_must_do(tmp_path: Path) -> None:
    assert ev.status(_project(tmp_path, None), "1.0.0").status == "unversioned"
    assert ev.status(_project(tmp_path, "1.0.0"), "1.0.0").status == "current"
    assert ev.status(_project(tmp_path, "1.0.0"), "1.1.0").status == "upgrade"
    assert ev.status(_project(tmp_path, "1.0.0"), "1.0.0-beta1").status == "older"
    found = ev.status(_project(tmp_path, "1.2.0"), "1.0.0")
    assert (found.project, found.tool) == ("1.2.0", "1.0.0")


def test_a_bad_engine_in_mapper_toml_is_a_config_error(tmp_path: Path) -> None:
    project = _project(tmp_path, "latest")
    with pytest.raises(MapperConfigError, match="engine"):
        load_config(project / "mapper.toml")
    with pytest.raises(MapperConfigError, match="engine"):
        ev.declared(project)


def test_upgrade_writes_the_version_and_keeps_the_comments(tmp_path: Path) -> None:
    project = _project(tmp_path, "1.0.0")
    (project / "mapper.toml").write_text(
        (project / "mapper.toml").read_text().replace("[optimizer]", "# keep me\n[optimizer]")
    )
    before = ev.upgrade(project, "1.1.0")
    assert before.status == "upgrade" and before.project == "1.0.0"
    text = (project / "mapper.toml").read_text()
    assert tomllib.loads(text)["project"]["engine"] == "1.1.0" and "# keep me" in text
    assert ev.upgrade(project, "1.1.0").status == "current"  # nothing more to do


def test_upgrade_adds_the_version_to_a_project_that_has_none(tmp_path: Path) -> None:
    project = _project(tmp_path, None)
    assert ev.upgrade(project, "1.0.0").status == "unversioned"
    assert ev.status(project, "1.0.0").status == "current"


def test_upgrade_never_moves_the_file_back(tmp_path: Path) -> None:
    project = _project(tmp_path, "2.0.0")
    before = (project / "mapper.toml").read_text()
    with pytest.raises(MapperConfigError, match="never moved back"):
        ev.upgrade(project, "1.0.0")
    assert (project / "mapper.toml").read_text() == before


def test_a_new_project_carries_the_tools_version(tmp_path: Path) -> None:
    create_project(
        tmp_path / "p",
        "plsql",
        {"schema": "OWNER", "error_code": -20000, "mapping_package_prefix": "M_"},
    )
    assert ev.declared(tmp_path / "p") == ENGINE_VERSION


def test_the_properties_form_cannot_change_the_version(tmp_path: Path) -> None:
    project = _project(tmp_path, "1.0.0")
    values = project_config.read(project)["values"]
    values["project"]["engine"] = "9.9.9"
    project_config.write(project, values)
    assert ev.declared(project) == "1.0.0"
    del values["project"]["engine"]  # a form that does not send it back: it is not deleted
    project_config.write(project, values)
    assert ev.declared(project) == "1.0.0"


def test_the_worker_answers_the_status_and_upgrades(tmp_path: Path) -> None:
    project = _project(tmp_path, "0.0.1")
    asked = handle({"op": "engine_status", "project": str(project)})
    assert asked == {
        "ok": True,
        "status": "upgrade",
        "project": "0.0.1",
        "tool": ENGINE_VERSION,
    }
    done = handle({"op": "engine_upgrade", "project": str(project)})
    assert done["status"] == "upgrade"
    assert ev.declared(project) == ENGINE_VERSION


# --- the CLI ---------------------------------------------------------------------------------


def test_a_tool_older_than_the_project_refuses_to_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_project(tmp_path, "99.0.0"))
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 1
    assert "newer than this tool" in result.output and "--allow-older-engine" in result.output
    assert not (tmp_path / "build").exists()


def test_the_risk_can_be_accepted_and_the_file_is_not_moved_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, "99.0.0")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["--allow-older-engine", "build"])
    assert result.exit_code == 0, result.output
    assert "warning: mapper.toml is at engine 99.0.0" in result.output
    assert ev.declared(project) == "99.0.0"
    again = runner.invoke(app, ["build"], env={"J2JME_ALLOW_OLDER_ENGINE": "1"})  # also by env
    assert again.exit_code == 0, again.output


def test_an_older_project_builds_with_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, "0.0.1")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    assert "warning: mapper.toml is at engine 0.0.1" in result.output
    assert "mapper upgrade" in result.output
    assert ev.declared(project) == "0.0.1"  # building does not rewrite it


def test_a_project_without_a_version_builds_with_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_project(tmp_path, None))
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0 and "without an engine version" in result.output


def test_a_project_at_the_tools_version_is_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_project(tmp_path, ENGINE_VERSION))
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0 and "warning" not in result.output


def test_the_upgrade_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path, "0.0.1")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 0 and f"0.0.1 -> {ENGINE_VERSION}" in result.output
    assert "already at engine" in runner.invoke(app, ["upgrade"]).output
    (project / "mapper.toml").write_text(
        (project / "mapper.toml").read_text().replace(ENGINE_VERSION, "99.0.0")
    )
    refused = runner.invoke(app, ["upgrade"])
    assert refused.exit_code == 1 and "never moved back" in refused.output
    assert json.dumps(ev.declared(project)) == '"99.0.0"'
