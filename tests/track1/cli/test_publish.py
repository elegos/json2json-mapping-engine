"""`mapper publish` and `[publish] dir` (`cli/publish.py`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import project_config, publish
from cli.config import MapperConfigError, parse_config
from cli.main import app
from cli.manifest import digest
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
    root = tmp_path / "proj"
    (root / "mappings").mkdir(parents=True)
    (root / "schemas").mkdir()
    (root / "mapper.toml").write_text(MAPPER_TOML)
    (root / "mappings" / "ping.map.py").write_text(PING_MAPPING)
    (root / "mappings" / "order_event.map.py").write_text(ORDER_MAPPING)
    for kind, schema in (("input", ORDER_INPUT_SCHEMA), ("output", ORDER_OUTPUT_SCHEMA)):
        (root / "schemas" / f"order_event_{kind}.schema.json").write_text(json.dumps(schema))
    monkeypatch.chdir(root)
    monkeypatch.delenv(publish.ENV_DIR, raising=False)
    return root


def _set_publish_dir(project: Path, value: str) -> None:
    toml = project / "mapper.toml"
    toml.write_text(toml.read_text() + f'\n[publish]\ndir = "{value}"\n')


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_the_default_is_the_build_folder(project: Path) -> None:
    result = runner.invoke(app, ["publish"])
    assert result.exit_code == 0, result.output
    assert "nothing to copy" in result.output
    assert (project / COMPILED / "manifest.json").is_file()


def test_to_publishes_the_set_with_the_manifest_of_the_build(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, ["publish", "--to", str(out)])
    assert result.exit_code == 0, result.output
    assert _names(out) == ["manifest.json", "map_order_event.sql", "map_ping.sql"]
    assert (out / "manifest.json").read_text() == (project / COMPILED / "manifest.json").read_text()
    assert publish.verify(out) == []
    assert (
        digest((out / "map_ping.sql").read_text())
        == json.loads((out / "manifest.json").read_text())["outputs"]["map_ping.sql"]
    )


def test_a_relative_dir_of_mapper_toml_is_relative_to_the_project(project: Path) -> None:
    _set_publish_dir(project, "deploy/sql")
    result = runner.invoke(app, ["publish"])
    assert result.exit_code == 0, result.output
    assert _names(project / "deploy" / "sql") == [
        "manifest.json",
        "map_order_event.sql",
        "map_ping.sql",
    ]


def test_an_absolute_dir_of_mapper_toml(project: Path, tmp_path: Path) -> None:
    _set_publish_dir(project, str(tmp_path / "elsewhere"))
    assert runner.invoke(app, ["publish"]).exit_code == 0
    assert (tmp_path / "elsewhere" / "manifest.json").is_file()


def test_the_order_of_precedence(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_publish_dir(project, "from_toml")
    monkeypatch.setenv(publish.ENV_DIR, str(tmp_path / "from_env"))
    assert runner.invoke(app, ["publish"]).exit_code == 0
    assert (tmp_path / "from_env" / "manifest.json").is_file()
    assert not (project / "from_toml").exists()  # a per-user choice beats the project's
    assert runner.invoke(app, ["publish", "--to", str(tmp_path / "from_flag")]).exit_code == 0
    assert (tmp_path / "from_flag" / "manifest.json").is_file()


def test_what_is_not_in_the_old_manifest_is_never_touched(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "README.txt").write_text("not ours")
    (out / "other_team.sql").write_text("-- not ours either")
    assert runner.invoke(app, ["publish", "--to", str(out)]).exit_code == 0
    (project / "mappings" / "ping.map.py").unlink()  # the package disappears from the set
    assert runner.invoke(app, ["publish", "--to", str(out)]).exit_code == 0
    assert _names(out) == [
        "README.txt",
        "manifest.json",
        "map_order_event.sql",
        "other_team.sql",
    ]
    assert publish.verify(out) == []


def test_a_failed_build_publishes_nothing_and_leaves_the_last_set(
    project: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    assert runner.invoke(app, ["publish", "--to", str(out)]).exit_code == 0
    before = (out / "manifest.json").read_text()
    (project / "mappings" / "ping.map.py").write_text("this is not python (\n")
    result = runner.invoke(app, ["publish", "--to", str(out)])
    assert result.exit_code == 1
    assert (out / "manifest.json").read_text() == before
    assert publish.verify(out) == []


def test_publishing_twice_gives_the_same_folder(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["publish", "--to", str(out)])
    first = {p.name: p.read_text() for p in out.iterdir()}
    runner.invoke(app, ["publish", "--to", str(out)])
    assert {p.name: p.read_text() for p in out.iterdir()} == first


def test_an_interrupted_publish_has_no_manifest(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    assert runner.invoke(app, ["publish", "--to", str(out)]).exit_code == 0
    real = publish._write_atomically
    calls = []

    def dying(path: Path, text: str) -> None:
        calls.append(path.name)
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        real(path, text)

    monkeypatch.setattr(publish, "_write_atomically", dying)
    result = runner.invoke(app, ["publish", "--to", str(out)])
    assert result.exit_code == 1 and "cannot write to" in result.output
    assert not (out / "manifest.json").exists()  # a reader sees an unfinished set
    assert "no readable manifest.json" in publish.verify(out)[0]


def test_verify_finds_a_file_changed_or_gone(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["publish", "--to", str(out)])
    (out / "map_ping.sql").write_text("-- edited by hand")
    (out / "map_order_event.sql").unlink()
    assert publish.verify(out) == [
        "map_order_event.sql is missing",
        "map_ping.sql changed since it was published",
    ]


def test_a_text_that_is_not_what_the_manifest_says_is_refused(tmp_path: Path) -> None:
    manifest = {"outputs": {"a.sql": digest("one")}}
    with pytest.raises(publish.PublishError, match="a.sql"):
        publish.publish({"a.sql": "two"}, manifest, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_a_manifest_naming_a_path_outside_the_folder_removes_nothing_outside(
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    victim = tmp_path / "precious.txt"
    victim.write_text("keep")
    (out / "manifest.json").write_text(json.dumps({"outputs": {"../precious.txt": "x"}}))
    publish.publish({"a.sql": "x"}, {"outputs": {"a.sql": digest("x")}, "sources": {}}, out)
    assert victim.read_text() == "keep"


def test_no_leftover_temporary_files(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["publish", "--to", str(out)])
    assert not [p for p in out.iterdir() if p.name.endswith(".part")]


def test_the_json_output(project: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["publish", "--to", str(tmp_path / "out"), "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["ok"] is True
    assert any(m.startswith("published: 2 file(s) and manifest.json") for m in report["messages"])


def test_the_config_of_publish() -> None:
    base = {
        "project": {},
        "target": {"plsql": {"schema": "S", "mapping_package_prefix": "M_", "error_code": -20000}},
    }
    assert parse_config({**base, "publish": {"dir": " out "}}).publish.dir == "out"
    assert parse_config({**base, "publish": {"dir": ""}}).publish.dir is None
    assert parse_config(base).publish.dir is None
    with pytest.raises(MapperConfigError, match="unknown key"):
        parse_config({**base, "publish": {"folder": "x"}})
    with pytest.raises(MapperConfigError, match="must be a path"):
        parse_config({**base, "publish": {"dir": 3}})


def test_the_properties_form_offers_publish_dir(project: Path) -> None:
    sections = {tuple(s["path"]): s for s in project_config.describe()["engine"]}
    assert [o["key"] for o in sections[("publish",)]["options"]] == ["dir"]
    values = project_config.read(project)["values"]
    values["publish"] = {"dir": "deploy"}
    assert project_config.check(values) == []
    project_config.write(project, values)
    assert 'dir = "deploy"' in (project / "mapper.toml").read_text()
