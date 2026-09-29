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
[compiler.default_choices]
format = "round"
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
    (tmp_path / "schemas" / "input" / "order_event.json").write_text(json.dumps(ORDER_INPUT_SCHEMA))
    (tmp_path / "schemas" / "output" / "order_event.json").write_text(
        json.dumps(ORDER_OUTPUT_SCHEMA)
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


PKG = "build/compiled/mapping_rules.sql"


def test_build_produces_one_package_for_every_mapping(project: Path):
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    sql = (project / PKG).read_text()
    assert "CREATE OR REPLACE PACKAGE MAPPING_RULES AS" in sql
    assert "CREATE OR REPLACE PACKAGE BODY MAPPING_RULES AS" in sql
    assert "PROCEDURE map_ping (" in sql
    assert "PROCEDURE map_order_event_safe (" in sql
    assert not (project / "build/compiled/ping.sql").exists()


def test_same_rule_id_in_two_mappings_is_namespaced(project: Path):
    (project / "mappings" / "other.map.py").write_text(
        "from __mapping__ import *\n\n"
        "def order_id(root: Any) -> str:\n"
        "    return root.other\n\n"
        "out.OrderId = order_id(root)\n"
    )
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    sql = (project / PKG).read_text()
    assert "FUNCTION fn_order_event_order_id(" in sql
    assert "FUNCTION fn_other_order_id(" in sql
    # private by default: absent from the spec
    spec = sql.split("PACKAGE BODY")[0]
    assert "fn_" not in spec


def test_export_rule_functions_lists_them_in_the_spec(project: Path):
    toml = project / "mapper.toml"
    toml.write_text(
        toml.read_text().replace("export_rule_functions = false", "export_rule_functions = true")
    )
    runner.invoke(app, ["build"])
    spec = (project / PKG).read_text().split("PACKAGE BODY")[0]
    assert "FUNCTION fn_order_event_order_id(" in spec


def test_duplicate_mapping_id_is_a_build_error(project: Path):
    (project / "mappings" / "dup.map.py").write_text(
        'from __mapping__ import *\n\n__id__ = "ping"\n\nout.Status = "X"\n'
    )
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 1
    assert "duplicate mapping id 'ping'" in result.output


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
    assert "package: " in result.output


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
    sql_path = project / PKG
    sql_path.write_text(sql_path.read_text() + "\n-- tampered\n")
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1
    assert "out of sync" in result.output


def test_check_fails_when_compiled_output_is_missing(project: Path):
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1
    assert "missing" in result.output


def test_build_single_file_still_packages_every_mapping(project: Path):
    result = runner.invoke(app, ["build", "mappings/ping.map.py"])
    assert result.exit_code == 0, result.output
    assert "ping.map.py" in result.output
    assert "order_event.map.py" not in result.output
    sql = (project / PKG).read_text()
    assert "map_ping" in sql and "map_order_event" in sql
