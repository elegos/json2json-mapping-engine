"""The project-properties form's backend: descriptors, checks and comment-keeping writes."""

from __future__ import annotations

import io
import json
import shutil
import tomllib
from pathlib import Path

import pytest

from cli import project_config
from cli.config import MapperConfigError
from cli.serve import serve
from compiler.backends.base import Option, check_options
from compiler.backends.registry import backends

FIXTURE = Path(__file__).resolve().parents[3] / "desktop" / "fixtures" / "orders-project"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    shutil.copy(FIXTURE / "mapper.toml", tmp_path / "mapper.toml")
    return tmp_path


def test_every_backend_lists_the_keys_it_requires_and_defaults() -> None:
    for name, cls in backends().items():
        keys = {o.key for o in cls.options}
        assert set(cls.required_keys) <= keys, name
        assert set(cls.defaults) <= keys, name
        assert {o.key for o in cls.options if o.required} == set(cls.required_keys), name


def test_option_kinds_are_checked() -> None:
    options = (
        Option("n", "int"),
        Option("flag", "bool"),
        Option("mode", "choice", choices=("a", "b")),
        Option("t", "table"),
        Option("s", "string", required=True),
    )
    problems = dict(
        check_options(options, {"n": True, "flag": 1, "mode": "c", "t": {"k": 1}, "x": 1})
    )
    assert set(problems) == {"n", "flag", "mode", "t", "x", "s"}
    assert (
        check_options(options, {"s": "ok", "n": 3, "flag": False, "mode": "a", "t": {"k": "v"}})
        == []
    )


def test_unknown_key_in_a_target_section_is_a_config_error(project: Path) -> None:
    values = tomllib.loads((project / "mapper.toml").read_text())
    values["target"]["plsql"]["schemaa"] = "X"
    assert any(i["path"] == "target.plsql.schemaa" for i in project_config.check(values))


def test_read_describes_engine_sections_and_the_backends_options(project: Path) -> None:
    result = project_config.read(project)
    titles = [s["title"] for s in result["schema"]["engine"]]
    assert titles == ["Project", "Optimizer", "Default choices"]
    target = next(o for o in result["schema"]["engine"][0]["options"] if o["key"] == "target")
    assert "plsql" in target["choices"]
    keys = {o["key"] for o in result["schema"]["targets"]["plsql"]}
    assert {"schema", "error_code", "mapping_packages", "export_rule_functions"} <= keys
    assert result["values"]["target"]["plsql"]["schema"] == "MAPPING_OWNER"
    # what the integration tests need belongs to the target: `[target.plsql.test]`
    tests = {o["key"] for o in result["schema"]["target_tests"]["plsql"]}
    assert tests == {"container_image", "container_tag"}
    assert result["values"]["target"]["plsql"]["test"]["container_tag"] == "latest-23ai"


def test_the_test_table_of_a_target_is_checked(project: Path) -> None:
    values = project_config.read(project)["values"]
    values["target"]["plsql"]["test"]["container_tag"] = 3
    values["target"]["plsql"]["test"]["nope"] = "x"
    paths = {i["path"] for i in project_config.check(values)}
    assert {"target.plsql.test.container_tag", "target.plsql.test.nope"} <= paths


def test_a_cross_key_error_comes_from_the_backend(project: Path) -> None:
    values = project_config.read(project)["values"]
    del values["target"]["plsql"]["mapping_package_prefix"]
    issues = project_config.check(values)
    assert len(issues) == 1 and issues[0]["path"] == ""


def test_write_keeps_comments_and_touches_only_what_changed(project: Path) -> None:
    before = (project / "mapper.toml").read_text()
    values = project_config.read(project)["values"]
    values["target"]["plsql"]["schema"] = "OTHER"
    values["optimizer"]["loop_fusion"] = False
    project_config.write(project, values)
    after = (project / "mapper.toml").read_text()
    assert tomllib.loads(after) == values
    assert "# compilation target" in after and "# disable if side-effects are suspected" in after
    changed = [
        (a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True) if a != b
    ]
    assert len(changed) == 2


def test_write_removes_a_dropped_key_and_adds_a_new_one(project: Path) -> None:
    values = project_config.read(project)["values"]
    del values["target"]["plsql"]["fn_suffix"]
    values["target"]["plsql"]["functions_package"] = "MY_FUNCS"
    project_config.write(project, values)
    written = tomllib.loads((project / "mapper.toml").read_text())
    assert "fn_suffix" not in written["target"]["plsql"]
    assert written["target"]["plsql"]["functions_package"] == "MY_FUNCS"


def test_write_refuses_an_invalid_configuration_and_leaves_the_file(project: Path) -> None:
    before = (project / "mapper.toml").read_text()
    values = project_config.read(project)["values"]
    values["optimizer"]["parallel_conflict"] = "sometimes"
    with pytest.raises(MapperConfigError):
        project_config.write(project, values)
    assert (project / "mapper.toml").read_text() == before


def test_serve_config_ops(project: Path) -> None:
    lines = [
        {"id": 1, "op": "config_read", "project": str(project)},
        {"id": 2, "op": "config_check", "values": {"project": {"mode": "x"}}},
    ]
    out = io.StringIO()
    serve(io.StringIO("\n".join(json.dumps(x) for x in lines) + "\n"), out)
    first, second = (json.loads(x) for x in out.getvalue().splitlines())
    assert first["ok"] and first["values"]["project"]["target"] == "plsql"
    assert second["ok"] and any(i["path"] == "project.mode" for i in second["issues"])


def test_a_backend_limits_are_checked_with_its_own_words() -> None:
    from cli.project_config import check

    base = {"project": {"mode": "driven", "target": "plsql"}}

    def issues(**section: object) -> dict[str, str]:
        values = {**base, "target": {"plsql": {"schema": "OWNER", "error_code": -20000, **section}}}
        return {i["path"]: i["message"] for i in check(values)}

    assert issues(mapping_package_prefix="M_") == {}
    assert issues(mapping_package_prefix="M_", error_code=-200000)["target.plsql.error_code"] == (
        "must be between -20999 and -20000"
    )
    assert "target.plsql.error_code" in issues(mapping_package_prefix="M_", error_code=5)
    bad_schema = issues(mapping_package_prefix="M_", schema="1 bad")
    assert "Oracle identifier" in bad_schema["target.plsql.schema"]
    assert (
        "letters, digits"
        in issues(mapping_package_prefix="a b")["target.plsql.mapping_package_prefix"]
    )
