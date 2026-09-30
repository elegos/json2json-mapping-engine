import pytest

from compiler.backends.base import CodeGenError
from compiler.backends.plsql.backend import PlsqlBackend
from compiler.backends.plsql.naming import PlsqlNaming
from compiler.pipeline import compile_source, compile_unit

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


def _files(**config) -> dict[str, str]:
    merged = {"mapping_package_prefix": "PKG_", "error_code": -20000, **config}
    backend = PlsqlBackend(
        {k: v for k, v in merged.items() if v is not None}
    )  # None = drop the key
    unit = compile_unit(_SOURCE, "m", backend)
    return backend.assemble([unit])


def _artifact(**config) -> str:
    return "\n".join(_files(**config).values())


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
    assert "CREATE OR REPLACE PACKAGE OWNER.PKG_M AS" in text
    assert "CREATE OR REPLACE PACKAGE BODY OWNER.PKG_M AS" in text
    assert "END PKG_M;" in text


def test_package_name_is_prefix_id_suffix_uppercased():
    assert list(_files(mapping_package_suffix="_x")) == ["pkg_m_x.sql"]
    files = _files(mapping_package_prefix="", mapping_package_suffix="_pkg")
    assert list(files) == ["m_pkg.sql"]


def test_explicit_packages_and_index_package():
    files = _files(
        mapping_package_prefix=None, mapping_packages={"m": "MY_PKG"}, mapping_index_package="IDX"
    )
    assert list(files) == ["my_pkg.sql", "idx.sql"]  # mapping packages, then the index
    assert "PACKAGE IDX AS" in files["idx.sql"]
    assert "RETURN MY_PKG.map_m_fn(p_src);" in files["idx.sql"]


def test_index_package_forwarders_keep_the_signature():
    idx = _files(mapping_index_package="IDX", schema="OWNER")["idx.sql"]
    spec, body = idx.split("PACKAGE BODY")
    assert "PROCEDURE map_m (\n        p_src IN  CLOB,\n        p_out OUT CLOB\n    );" in spec
    assert "FUNCTION map_m_fn (p_src IN CLOB) RETURN CLOB PARALLEL_ENABLE;" in spec
    assert "OWNER.PKG_M.map_m_safe(p_src, p_out, p_err);" in body


def test_choosing_both_ways_or_neither_is_an_error():
    both = {"mapping_packages": {"m": "A"}, "mapping_package_prefix": "P_"}
    with pytest.raises(CodeGenError, match="not both"):
        PlsqlNaming.from_config(both)
    with pytest.raises(CodeGenError, match="say how mappings map"):
        PlsqlNaming.from_config({}, strict=True)
    with pytest.raises(CodeGenError, match="both empty"):
        PlsqlNaming.from_config({"mapping_package_prefix": ""}, strict=True)


def test_packages_must_be_distinct():
    with pytest.raises(CodeGenError, match="share a package"):
        PlsqlNaming.from_config({"mapping_packages": {"a": "P", "b": "p"}})
    with pytest.raises(CodeGenError, match="functions_package or mapping_index_package"):
        _files(
            mapping_package_prefix=None, mapping_packages={"m": "IDX"}, mapping_index_package="idx"
        )


def test_unknown_mapping_in_the_explicit_table_is_an_error():
    with pytest.raises(CodeGenError, match="unknown mapping"):
        _files(mapping_package_prefix=None, mapping_packages={"m": "A", "ghost": "B"})


def test_bad_identifier_parts_are_rejected():
    with pytest.raises(CodeGenError):
        PlsqlNaming.from_config({"fn_prefix": "1x"})
    with pytest.raises(CodeGenError):
        PlsqlNaming.from_config({"schema": "a b"})


def test_call_path_for_the_harness():
    naming = PlsqlNaming.from_config(
        {"mapping_package_prefix": "PKG_", "schema": "OWNER", "fn_suffix": "_v2"}
    )
    assert naming.call_path("m", "_safe") == "OWNER.PKG_M.map_m_safe_v2"
    indexed = PlsqlNaming.from_config(
        {"mapping_package_prefix": "PKG_", "schema": "OWNER", "mapping_index_package": "IDX"}
    )
    assert indexed.call_path("m") == "OWNER.IDX.map_m"


_USES_LIBRARY = (
    "from __mapping__ import *\n\n"
    "def first(root: Any) -> str:\n"
    "    return split_first(root.ref, '|')\n\n"
    "out.First = first(root)\n"
)


def _library_files(**config) -> dict[str, str]:
    merged = {"mapping_package_prefix": "PKG_", "error_code": -20000, **config}
    backend = PlsqlBackend({k: v for k, v in merged.items() if v is not None})
    return backend.assemble([compile_unit(_USES_LIBRARY, "m", backend)])


def test_functions_package_exists_only_when_a_mapping_uses_it():
    assert list(_files()) == ["pkg_m.sql"]
    files = _library_files(schema="OWNER")
    assert list(files) == ["j2jme_functions.sql", "pkg_m.sql"]  # functions first
    assert "CREATE OR REPLACE PACKAGE OWNER.J2JME_FUNCTIONS AS" in files["j2jme_functions.sql"]
    assert "OWNER.J2JME_FUNCTIONS.split_first(" in files["pkg_m.sql"]
    assert "INSTR" not in files["pkg_m.sql"]  # no longer inline


def test_functions_package_name_is_configurable():
    files = _library_files(functions_package="MY_FNS")
    assert list(files) == ["my_fns.sql", "pkg_m.sql"]
    assert "MY_FNS.split_first(" in files["pkg_m.sql"]


def test_functions_package_only_holds_what_is_used():
    body = _library_files()["j2jme_functions.sql"]
    assert "split_first" in body and "split_nth" not in body and "lookup" not in body


def test_functions_package_cannot_be_a_mapping_or_index_package():
    with pytest.raises(CodeGenError, match="are the same"):
        PlsqlNaming.from_config({"mapping_index_package": "X", "functions_package": "x"})
    with pytest.raises(CodeGenError, match="functions_package or mapping_index_package"):
        _library_files(mapping_package_prefix=None, mapping_packages={"m": "J2JME_FUNCTIONS"})


def test_deploy_order_puts_functions_first_and_index_last():
    naming = PlsqlNaming.from_config({"mapping_index_package": "IDX"})
    names = ["idx.sql", "b.sql", "j2jme_functions.sql", "a.sql"]
    assert naming.deploy_order(names) == ["j2jme_functions.sql", "a.sql", "b.sql", "idx.sql"]
