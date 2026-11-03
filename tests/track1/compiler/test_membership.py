"""`x in ("A", "B")` and `x not in (...)` with a literal list: the same answer on every backend."""

from __future__ import annotations

import pytest

from compiler.backends.plsql.codegen import CodeGenError
from compiler.pipeline import compile_source

SOURCE = """from __mapping__ import *

@dataclass
class Out:
    A: str
    B: str
    C: str

def a(root: Any) -> str | None:
    if root.kind in ("A", "B"):
        return "x"
    return "y"

def b(root: Any) -> str | None:
    if root.kind not in ("A", "B"):
        return "x"
    return "y"

def c(root: Any) -> str | None:
    if root.qty in (1, 2.5):
        return "x"
    return "y"

out.A = a(root)
out.B = b(root)
out.C = c(root)
"""


def test_a_literal_list_becomes_in_and_a_missing_value_is_in_nothing() -> None:
    sql = compile_source(SOURCE, "m")
    assert "COALESCE(p_root.get_String('kind') IN ('A', 'B'), FALSE)" in sql
    assert "(NOT COALESCE(p_root.get_String('kind') IN ('A', 'B'), FALSE))" in sql
    assert "COALESCE(p_root.get_Number('qty') IN (1, 2.5), FALSE)" in sql


@pytest.mark.parametrize("values", ["root.other", '("A", 1)', "(None,)"])
def test_only_a_list_of_texts_or_of_numbers_is_accepted(values: str) -> None:
    source = SOURCE.replace('root.kind in ("A", "B")', f"root.kind in {values}", 1)
    with pytest.raises(CodeGenError):
        compile_source(source, "m")
