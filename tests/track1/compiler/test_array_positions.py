"""A constant array position in a document path: `root.a.list[0].id`."""

from __future__ import annotations

import pytest

from compiler.pipeline import compile_source

SOURCE = """from __mapping__ import *

@dataclass
class Out:
    A: str
    B: int | None
    C: str | None

def a(root: Any) -> str:
    return root.tx.list[0].id

def b(root: Any) -> int | None:
    return root.tx.list[1].n

def c(root: Any) -> str | None:
    if root.tx.list[0].flag:
        return root.tx.tags[2]
    return None

out.A = a(root)
out.B = b(root)
out.C = c(root)
"""


@pytest.fixture(scope="module")
def sql() -> str:
    return compile_source(SOURCE, "m")


def test_fields_around_a_position_read_object_then_array_then_object(sql: str) -> None:
    assert "p_root.get_Object('tx').get_Array('list').get_String(0)" not in sql
    assert "p_root.get_Object('tx').get_Array('list').get_Object(0).get_String('id')" in sql


def test_the_last_step_may_be_a_position(sql: str) -> None:
    assert "p_root.get_Object('tx').get_Array('tags').get_String(2)" in sql


def test_numbers_and_truthiness_go_through_the_same_chain(sql: str) -> None:
    assert "p_root.get_Object('tx').get_Array('list').get_Object(1).get_Number('n')" in sql
    assert "truthy(p_root.get_Object('tx').get_Array('list').get_Object(0).get('flag'))" in sql


def test_a_position_must_be_a_constant() -> None:
    bad = SOURCE.replace("root.tx.list[0].id", "root.tx.list[len(root.tx.tags)].id")
    with pytest.raises(Exception, match="constant position"):
        compile_source(bad, "m")
