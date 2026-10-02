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
mapping_package_prefix = "MAP_"
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
    (tmp_path / "schemas").mkdir()
    (tmp_path / "mapper.toml").write_text(MAPPER_TOML)
    (tmp_path / "mappings" / "ping.map.py").write_text(PING_MAPPING)
    (tmp_path / "mappings" / "order_event.map.py").write_text(ORDER_MAPPING)
    (tmp_path / "schemas" / "order_event_input.schema.json").write_text(
        json.dumps(ORDER_INPUT_SCHEMA)
    )
    (tmp_path / "schemas" / "order_event_output.schema.json").write_text(
        json.dumps(ORDER_OUTPUT_SCHEMA)
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


COMPILED = "build/compiled"


def _sql(project: Path, name: str) -> str:
    return (project / COMPILED / f"{name}.sql").read_text()


def test_build_produces_one_package_per_mapping(project: Path):
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in (project / COMPILED).iterdir()) == [
        "map_order_event.sql",
        "map_ping.sql",
    ]
    ping = _sql(project, "map_ping")
    assert "CREATE OR REPLACE PACKAGE MAPPING_OWNER.MAP_PING AS" in ping
    assert "CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.MAP_PING AS" in ping
    assert "PROCEDURE map_ping (" in ping
    assert "map_order_event" not in ping
    assert "PROCEDURE map_order_event_safe (" in _sql(project, "map_order_event")


def _replace_in_toml(project: Path, old: str, new: str) -> None:
    toml = project / "mapper.toml"
    toml.write_text(toml.read_text().replace(old, new))


def _explicit_packages(project: Path, entries: str) -> None:
    """Swap the prefix for an explicit table (a table header ends the section's keys,
    so it goes last)."""
    toml = project / "mapper.toml"
    text = toml.read_text().replace('mapping_package_prefix = "MAP_"\n', "")
    toml.write_text(text + f"\n[target.plsql.mapping_packages]\n{entries}\n")


def test_rule_functions_live_in_their_own_mappings_package(project: Path):
    (project / "mappings" / "other.map.py").write_text(
        "from __mapping__ import *\n\n"
        "def order_id(root: Any) -> str:\n"
        "    return root.other\n\n"
        "out.OrderId = order_id(root)\n"
    )
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    other = _sql(project, "map_other")
    assert "FUNCTION fn_other_order_id(" in other
    assert "fn_order_event_" not in other
    # private by default: absent from the spec
    assert "fn_" not in other.split("PACKAGE BODY")[0]


def test_export_rule_functions_lists_them_in_the_spec(project: Path):
    _replace_in_toml(project, "export_rule_functions = false", "export_rule_functions = true")
    runner.invoke(app, ["build"])
    spec = _sql(project, "map_order_event").split("PACKAGE BODY")[0]
    assert "FUNCTION fn_order_event_order_id(" in spec


def test_index_package_forwards_to_every_mapping_and_is_deployed_last(project: Path):
    _replace_in_toml(
        project,
        'mapping_package_prefix = "MAP_"',
        'mapping_package_prefix = "MAP_"\nmapping_index_package = "MAPPINGS"',
    )
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    index = _sql(project, "mappings")
    assert "CREATE OR REPLACE PACKAGE MAPPING_OWNER.MAPPINGS AS" in index
    assert "MAPPING_OWNER.MAP_PING.map_ping(p_src, p_out);" in index
    assert "MAPPING_OWNER.MAP_ORDER_EVENT.map_order_event_safe(p_src, p_out, p_err);" in index
    from cli.build import compiled_sql
    from cli.config import load_config

    text = compiled_sql(load_config())
    assert text.rindex("PACKAGE MAPPING_OWNER.MAPPINGS AS") > text.rindex(
        "PACKAGE MAPPING_OWNER.MAP_PING AS"
    )


def test_explicit_package_table(project: Path):
    _explicit_packages(project, 'ping = "PING_PKG"\norder_event = "ORDERS_PKG"')
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    assert "PACKAGE MAPPING_OWNER.PING_PKG AS" in _sql(project, "ping_pkg")
    assert "PACKAGE MAPPING_OWNER.ORDERS_PKG AS" in _sql(project, "orders_pkg")


def test_a_mapping_missing_from_the_explicit_table_is_a_build_error(project: Path):
    _explicit_packages(project, 'ping = "PING_PKG"')
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 1
    assert "mapping 'order_event' has no package" in result.output


def test_unspecified_package_naming_is_a_config_error(project: Path):
    _replace_in_toml(project, 'mapping_package_prefix = "MAP_"\n', "")
    result = runner.invoke(app, ["build"])
    assert result.exit_code != 0
    assert "say how mappings map to packages" in result.output


def test_a_removed_mapping_removes_its_package_file(project: Path):
    runner.invoke(app, ["build"])
    (project / "mappings" / "ping.map.py").unlink()
    runner.invoke(app, ["build"])
    assert not (project / COMPILED / "map_ping.sql").exists()


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
    assert "packages: " in result.output


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
    sql_path = project / COMPILED / "map_ping.sql"
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
    assert (project / COMPILED / "map_ping.sql").is_file()
    assert (project / COMPILED / "map_order_event.sql").is_file()


def test_json_output_of_a_build(project: Path) -> None:
    (project / "mappings" / "ping.map.py").write_text(PING_MAPPING)
    result = runner.invoke(app, ["build", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True and payload["diagnostics"] == []
    assert any(line.startswith("compiled: ") for line in payload["messages"])


def test_json_output_of_a_failed_build(project: Path) -> None:
    (project / "mappings" / "ping.map.py").write_text("import os\n")
    result = runner.invoke(app, ["build", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["diagnostics"] and payload["diagnostics"][0]["severity"] == "error"


def test_json_diagnostic_carries_the_rule_path() -> None:
    from cli.main import _diagnostic

    d = _diagnostic("error", "mappings/functional/x.fn.yaml: rules[0].rules[2]: bad type")
    assert d == {
        "severity": "error",
        "file": "mappings/functional/x.fn.yaml",
        "rule": "rules[0].rules[2]",
        "message": "bad type",
    }
