"""Project functions (`fn/*.fn`) in the PL/SQL backend: what they say for PL/SQL is their code."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler.backends.base import CodeGenError
from compiler.backends.plsql.backend import PlsqlBackend
from compiler.function_linker import FunctionLinkError
from compiler.pipeline import compile_unit

MAPPING = (
    "from __mapping__ import *\n"
    "def a(root: Any) -> str | None:\n    return shout(root.s)\n"
    "out.A = a(root)\n"
)
CONFIG = {"schema": "S", "error_code": -20000, "mapping_package_prefix": "M_"}


def _project(tmp_path: Path, fn: str, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "fn").mkdir()
    (tmp_path / "fn/text.fn").write_text(fn)
    monkeypatch.chdir(tmp_path)


def test_a_project_function_is_rendered_from_its_plsql_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(
        tmp_path,
        'from __mapping__ import override\n\n@override(plsql="UPPER({s})")\n'
        "def shout(s: str) -> str:\n    ...\n",
        monkeypatch,
    )
    backend = PlsqlBackend(CONFIG)
    unit = compile_unit(MAPPING, "m", backend)
    sql = backend.assemble([unit])["m_m.sql"]
    assert "UPPER(p_root.get_String('s'))" in sql


def test_a_project_function_with_nothing_for_plsql_stops_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path, "def shout(s: str) -> str:\n    return s.upper()\n", monkeypatch)
    with pytest.raises((CodeGenError, FunctionLinkError), match="no implementation.*plsql"):
        compile_unit(MAPPING, "m", PlsqlBackend(CONFIG))


AGGREGATE = (
    "from __mapping__ import *\n"
    "def a(root: Any) -> float:\n    return avg(root.items, 'qty')\n"
    "out.Avg = a(root)\n"
)


def test_an_aggregate_is_a_loop_unless_the_project_overrides_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    backend = PlsqlBackend(CONFIG)
    sql = backend.assemble([compile_unit(AGGREGATE, "m", backend)])["m_m.sql"]
    assert "FOR v_aggk_" in sql
    _project(
        tmp_path,
        'from __mapping__ import override\n\n@override(plsql="MY_PKG.mean({items}, {field})")\n'
        "def avg(items: list[Any], field: str = '') -> Any:\n    ...\n",
        monkeypatch,
    )
    sql = backend.assemble([compile_unit(AGGREGATE, "m", backend)])["m_m.sql"]
    assert "MY_PKG.mean(p_root.get_Array('items'), 'qty')" in sql and "v_aggk_" not in sql
