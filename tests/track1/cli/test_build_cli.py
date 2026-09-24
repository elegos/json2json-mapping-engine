import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()

MAPPER_TOML = """\
[project]
mode   = "bootstrap"
target = "plsql"

[optimizer]
loop_fusion       = true
parallel_conflict = "exception"

[target.plsql]
schema     = "MAPPING_OWNER"
package    = "MAPPING_RULES"
fn_package = "MAPPING_FUNCTIONS"
fn_prefix  = ""
fn_suffix  = ""
error_code = -20000
export_rule_functions = false

[compiler]
decimal_mode = "round"
"""

PING_MAPPING = 'from __mapping__ import *\n\n__id__ = "ping"\n\nout.Status = "OK"\n'

ORDER_INPUT_SCHEMA = {
    "title": "OrderEvent",
    "type": "object",
    "properties": {"id": {"type": "string"}},
    "required": ["id"],
}
ORDER_OUTPUT_SCHEMA = {
    "title": "OrderSummary",
    "type": "object",
    "properties": {"OrderId": {"type": "string"}},
    "required": ["OrderId"],
}
ORDER_MAPPING = (
    "from __mapping__ import *\n\n"
    '__id__ = "order_event"\n\n'
    "def order_id(root: OrderEvent) -> str:\n"
    "    return root.id\n\n"
    "out.OrderId = order_id(root)\n"
)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "mappings").mkdir()
    (tmp_path / "schemas" / "input").mkdir(parents=True)
    (tmp_path / "schemas" / "output").mkdir(parents=True)
    (tmp_path / "mapper.toml").write_text(MAPPER_TOML)
    (tmp_path / "mappings" / "ping.map.py").write_text(PING_MAPPING)
    (tmp_path / "mappings" / "order_event.map.py").write_text(ORDER_MAPPING)
    (tmp_path / "schemas" / "input" / "order_event.json").write_text(
        json.dumps(ORDER_INPUT_SCHEMA)
    )
    (tmp_path / "schemas" / "output" / "order_event.json").write_text(
        json.dumps(ORDER_OUTPUT_SCHEMA)
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_build_produces_compiled_sql_for_every_mapping(project: Path):
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    assert (project / "build/compiled/ping.sql").is_file()
    assert (project / "build/compiled/order_event.sql").is_file()
    assert "map_ping" in (project / "build/compiled/ping.sql").read_text()


def test_stubs_generates_schema_artifacts_and_ide_config(project: Path):
    result = runner.invoke(app, ["stubs"])
    assert result.exit_code == 0, result.output
    assert (project / "generated/stubs/order_event.pyi").is_file()
    assert (project / "generated/dataclasses/order_event.py").is_file()
    assert (project / "build/python/stubs/__mapping__.pyi").is_file()
    vscode_settings = json.loads((project / ".vscode/settings.json").read_text())
    assert vscode_settings["python.analysis.stubPath"] == "build/python/stubs"
    pyrightconfig = json.loads((project / "pyrightconfig.json").read_text())
    assert pyrightconfig["stubPath"] == "build/python/stubs"


def test_rebuild_with_no_changes_is_a_cache_hit(project: Path):
    runner.invoke(app, ["build"])
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    assert "up-to-date: mappings/ping.map.py" in result.output
    assert "up-to-date: mappings/order_event.map.py" in result.output
    assert "compiled:" not in result.output


def test_touching_mapper_toml_forces_full_rebuild(project: Path):
    runner.invoke(app, ["build"])
    toml_path = project / "mapper.toml"
    toml_path.write_text(toml_path.read_text().replace('"round"', '"truncate"'))
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    assert "compiled: mappings/ping.map.py" in result.output
    assert "compiled: mappings/order_event.map.py" in result.output


def test_check_passes_after_a_clean_build(project: Path):
    runner.invoke(app, ["build"])
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_check_fails_when_compiled_output_is_tampered(project: Path):
    runner.invoke(app, ["build"])
    sql_path = project / "build/compiled/ping.sql"
    sql_path.write_text(sql_path.read_text() + "\n-- tampered\n")
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1
    assert "out of sync" in result.output


def test_check_fails_when_compiled_output_is_missing(project: Path):
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1
    assert "missing" in result.output


def test_build_single_file(project: Path):
    result = runner.invoke(app, ["build", "mappings/ping.map.py"])
    assert result.exit_code == 0, result.output
    assert (project / "build/compiled/ping.sql").is_file()
    assert not (project / "build/compiled/order_event.sql").exists()


def test_driven_mode_gives_a_clear_error(project: Path):
    toml_path = project / "mapper.toml"
    toml_path.write_text(toml_path.read_text().replace('mode   = "bootstrap"', 'mode   = "driven"'))
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 1
    assert "driven" in result.output.lower()
    assert "not implemented" in result.output.lower() or "isn't implemented" in result.output.lower()


def test_invalid_mapper_toml_is_a_clear_error(project: Path):
    (project / "mapper.toml").write_text("[project]\ntarget = \"cobol\"\n")
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 1
    assert "cobol" in result.output
