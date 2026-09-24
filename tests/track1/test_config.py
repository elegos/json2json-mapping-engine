import tomllib
from pathlib import Path

import pytest

from cli.config import MapperConfigError, load_config, parse_config

EXAMPLE_TOML = """
[project]
mode   = "driven"
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

[compiler]
decimal_mode = "round"

[test]
container_image = "container-registry.example.com/oracle-db"
container_tag   = "19.3.0-ee"
"""


def test_round_trips_architecture_example():
    config = parse_config(tomllib.loads(EXAMPLE_TOML))

    assert config.project.mode == "driven"
    assert config.project.target == "plsql"
    assert config.optimizer.loop_fusion is True
    assert config.optimizer.parallel_conflict == "exception"
    assert config.compiler.decimal_mode == "round"
    assert config.test.container_image == "container-registry.example.com/oracle-db"
    assert config.test.container_tag == "19.3.0-ee"

    plsql = config.target_config("plsql")
    assert plsql["schema"] == "MAPPING_OWNER"
    assert plsql["package"] == "MAPPING_RULES"
    assert plsql["fn_package"] == "MAPPING_FUNCTIONS"
    assert plsql["error_code"] == -20000


def test_rejects_target_missing_required_key():
    bad = EXAMPLE_TOML.replace("error_code = -20000", "")
    with pytest.raises(MapperConfigError, match="error_code"):
        parse_config(tomllib.loads(bad))


def test_rejects_active_target_without_section():
    bad = """
    [project]
    target = "cobol"
    """
    with pytest.raises(MapperConfigError, match="cobol"):
        parse_config(tomllib.loads(bad))


def test_rejects_invalid_parallel_conflict():
    bad = EXAMPLE_TOML.replace('parallel_conflict = "exception"', 'parallel_conflict = "bogus"')
    with pytest.raises(MapperConfigError, match="parallel_conflict"):
        parse_config(tomllib.loads(bad))


def test_defaults_when_sections_absent():
    config = parse_config({"target": {"plsql": {
        "schema": "S", "package": "P", "fn_package": "FP", "error_code": -20000,
    }}})
    assert config.project.mode == "driven"
    assert config.optimizer.loop_fusion is True
    assert config.compiler.decimal_mode == "round"
    assert config.test.container_image is None


def test_load_config_from_repo_root(tmp_path: Path):
    toml_path = tmp_path / "mapper.toml"
    toml_path.write_text(EXAMPLE_TOML)
    config = load_config(toml_path)
    assert config.path == toml_path
    assert config.raw["project"]["mode"] == "driven"


def test_load_config_missing_file(tmp_path: Path):
    with pytest.raises(MapperConfigError, match="no mapper.toml found"):
        load_config(tmp_path / "mapper.toml")
