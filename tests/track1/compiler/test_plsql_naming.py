import pytest

from compiler.backends.base import CodeGenError
from compiler.backends.plsql.backend import PlsqlBackend
from compiler.backends.plsql.naming import PlsqlNaming
from compiler.pipeline import compile_source

_SOURCE = (
    "from __mapping__ import *\n\n"
    "@dataclass\n"
    "class Line:\n"
    "    Id: str\n\n"
    "@parallel(degree=2)\n"
    "def line(root: Any, src: Any) -> Line:\n"
    "    return Line(Id=src.id)\n\n"
    "for src in root.items:\n"
    "    out.Lines.append(line(root, src))\n"
)


def _artifact(**config) -> str:
    backend = PlsqlBackend({"package": "PKG", "error_code": -20000, **config})
    return compile_source(_SOURCE, "m", backend)


def test_default_names_are_unchanged():
    text = compile_source(_SOURCE, "m")
    assert "PROCEDURE map_m (" in text
    assert "PROCEDURE map_m_safe (" in text
    assert "FUNCTION map_m_fn " in text
    assert "FUNCTION fn_m_line(" in text


def test_prefix_and_suffix_decorate_entry_points_and_rule_functions():
    text = _artifact(fn_prefix="x_", fn_suffix="_v2")
    for name in ("x_map_m_v2", "x_map_m_safe_v2", "x_map_m_fn_v2", "x_fn_m_line_v2"):
        assert f" {name}" in text
    assert "x_map_m_v2(p_src, v_out);" in text


def test_schema_qualifies_created_packages_only():
    text = _artifact(schema="OWNER")
    assert "CREATE OR REPLACE PACKAGE OWNER.PKG AS" in text
    assert "CREATE OR REPLACE PACKAGE BODY OWNER.PKG AS" in text
    assert "END PKG;" in text


def test_fn_package_holds_rule_functions_and_is_deployed_first():
    text = _artifact(fn_package="FNS", schema="OWNER")
    fns, main = text.split("CREATE OR REPLACE PACKAGE OWNER.PKG AS")
    assert "CREATE OR REPLACE PACKAGE OWNER.FNS AS" in fns
    assert "FUNCTION fn_m_line(" in fns
    assert "FNS.fn_m_line(" in main
    assert "FUNCTION fn_m_line(" not in main


def test_fn_package_must_differ_from_package():
    with pytest.raises(CodeGenError):
        _artifact(fn_package="PKG")


def test_bad_identifier_parts_are_rejected():
    with pytest.raises(CodeGenError):
        PlsqlNaming.from_config({"fn_prefix": "1x"})
    with pytest.raises(CodeGenError):
        PlsqlNaming.from_config({"schema": "a b"})


def test_call_path_for_the_harness():
    naming = PlsqlNaming.from_config({"package": "PKG", "schema": "OWNER", "fn_suffix": "_v2"})
    assert naming.call_path("m", "_safe") == "OWNER.PKG.map_m_safe_v2"
