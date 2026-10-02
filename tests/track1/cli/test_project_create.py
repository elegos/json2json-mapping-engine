import tomllib
from pathlib import Path

import pytest

from cli.config import MapperConfigError, load_config
from cli.project_create import FOLDERS, create_project


def test_a_new_project_loads_and_has_its_folders(tmp_path: Path) -> None:
    project = tmp_path / "new" / "proj"
    create_project(
        project, "plsql", {"schema": "OWNER", "error_code": -20000, "mapping_package_prefix": "M_"}
    )
    config = load_config(project / "mapper.toml")
    assert config.project.target == "plsql"
    assert (
        tomllib.loads((project / "mapper.toml").read_text())["target"]["plsql"]["schema"] == "OWNER"
    )
    assert all((project / f).is_dir() for f in FOLDERS)


def test_a_missing_required_option_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(MapperConfigError, match="schema"):
        create_project(tmp_path, "plsql")
    assert list(tmp_path.iterdir()) == []


def test_unknown_backend_and_existing_project_are_refused(tmp_path: Path) -> None:
    with pytest.raises(MapperConfigError, match="unknown target"):
        create_project(tmp_path, "cobol")
    create_project(
        tmp_path, "plsql", {"schema": "A", "error_code": -20000, "mapping_package_prefix": "M_"}
    )
    with pytest.raises(MapperConfigError, match="already has"):
        create_project(
            tmp_path, "plsql", {"schema": "B", "error_code": -20000, "mapping_package_prefix": "M_"}
        )


def test_what_the_backend_suggests_is_written_and_a_given_value_wins(tmp_path: Path) -> None:
    create_project(tmp_path / "a", "plsql", {"schema": "OWNER"})  # nothing else needed
    values = tomllib.loads((tmp_path / "a/mapper.toml").read_text())["target"]["plsql"]
    assert values["mapping_package_prefix"] == "J2JME_MAP_" and values["error_code"] == -20000
    create_project(tmp_path / "b", "plsql", {"schema": "O", "mapping_package_prefix": "X_"})
    assert (
        tomllib.loads((tmp_path / "b/mapper.toml").read_text())["target"]["plsql"][
            "mapping_package_prefix"
        ]
        == "X_"
    )
