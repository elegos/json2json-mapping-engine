"""Conditions use Python's truthiness (docs/ARCHITECTURE.md, §Truthiness)."""

from __future__ import annotations

import pytest

from compiler.backends.plsql.builtins import LIBRARY_FUNCTIONS, truthy_py
from compiler.pipeline import compile_source

SOURCE = """from __mapping__ import *

@dataclass
class Out:
    A: str

def a(root: Any) -> str | None:
    n = root.qty
    if root.note and not root.flag:
        return "x"
    if n:
        return "y"
    if 1 < 2:
        return if_else(root.tag, "p", "q")
    return "z"

out.A = a(root)
"""


@pytest.fixture(scope="module")
def sql() -> str:
    return compile_source(SOURCE, "m")


def test_a_value_read_from_the_document_is_tested_by_the_shared_function(sql: str) -> None:
    assert "J2JME_FUNCTIONS.truthy(p_root.get('note'))" in sql
    assert "(NOT J2JME_FUNCTIONS.truthy(p_root.get('flag')))" in sql
    assert "CASE WHEN J2JME_FUNCTIONS.truthy(p_root.get('tag')) THEN 'p' ELSE 'q' END" in sql


def test_a_comparison_is_not_wrapped(sql: str) -> None:
    assert "IF (1 < 2) THEN" in sql


def test_the_shared_function_handles_every_json_type(sql: str) -> None:
    body = LIBRARY_FUNCTIONS["truthy"].body_text()
    for probe in ("is_Null", "is_Boolean", "is_Number", "is_String", "is_Array", "is_Object"):
        assert probe in body
    assert "FUNCTION truthy(p_el IN JSON_ELEMENT_T) RETURN BOOLEAN IS" in sql


def test_the_reference_is_python() -> None:
    falsy = [None, False, 0, 0.0, "", [], {}]
    truthy = [True, 1, 0.5, " ", "0", [0], {"a": None}]
    assert not any(truthy_py(v) for v in falsy)
    assert all(truthy_py(v) for v in truthy)


def test_truthy_is_not_callable_from_a_mapping() -> None:
    from compiler.backends.plsql.builtins import BUILTIN_FUNCTIONS

    assert "truthy" not in BUILTIN_FUNCTIONS
