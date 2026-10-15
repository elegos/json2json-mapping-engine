"""`matches(text, pattern)`: the whole text fits a pattern written in the subset of regular
expressions that every backend reads the same way."""

from __future__ import annotations

import pytest

from compiler.backends.base import CodeGenError
from compiler.builtins import matches
from compiler.pipeline import compile_source
from compiler.portable_regex import portable_regex_error

SOURCE = """from __mapping__ import *

@dataclass
class Out:
    A: str

def a(root: Any) -> str | None:
    if matches(root.code, "[A-Z]{3}[XYZ][0-9]{7}"):
        return "x"
    return "y"

out.A = a(root)
"""


@pytest.mark.parametrize(
    "pattern",
    ["[A-Z]{3}[XYZ][0-9]{7}", "(AB|CD)[0-9]+\\.", "x+y?z*", "[^0-9]+", ".{3}", "a{2,}", "é[a-z]"],
)
def test_the_portable_subset_is_accepted(pattern: str) -> None:
    assert portable_regex_error(pattern) is None


@pytest.mark.parametrize(
    ("pattern", "why"),
    [
        ("\\d+", "not portable"),
        ("\\b", "not portable"),
        ("^a", "whole text"),
        ("a$", "whole text"),
        ("a*?", "lazy"),
        ("a++", "possessive"),
        ("(?:a)", "(?...)"),
        ("[[:alpha:]]", "no [:class:]"),
        ("[a\\]]", "no \\"),
        ("a{2,1}", "wrong way round"),
        ("a|", "empty alternative"),
        ("|a", "empty alternative"),
        ("()", "empty group"),
        ("(a", "never closed"),
        ("a)", "no ( before"),
        ("+a", "repeats nothing"),
        ("", "empty"),
    ],
)
def test_what_a_dialect_reads_in_its_own_way_is_refused(pattern: str, why: str) -> None:
    assert why in (portable_regex_error(pattern) or "")


def test_python_matches_the_whole_text() -> None:
    assert matches("ABCX1234567", "[A-Z]{3}[XYZ][0-9]{7}") is True
    assert matches("ABCX12345678", "[A-Z]{3}[XYZ][0-9]{7}") is False  # not the whole text
    assert matches("xABCX1234567", "[A-Z]{3}[XYZ][0-9]{7}") is False
    assert matches("ab", "a|ab") is True  # the whole text, so the longer alternative
    assert matches(None, "a") is None and matches("", "a") is None  # an empty text is null


def test_plsql_anchors_the_pattern_and_keeps_a_missing_text_missing() -> None:
    sql = compile_source(SOURCE, "m")
    assert "REGEXP_LIKE(p_root.get_String('code'), '^(' || '[A-Z]{3}[XYZ][0-9]{7}' || ')$')" in sql
    assert "WHEN p_root.get_String('code') IS NULL THEN NULL" in sql


@pytest.mark.parametrize("pattern", ["root.other", '"\\\\d+"', '"^a"'])
def test_the_pattern_must_be_a_portable_literal(pattern: str) -> None:
    source = SOURCE.replace('"[A-Z]{3}[XYZ][0-9]{7}"', pattern)
    with pytest.raises(CodeGenError):
        compile_source(source, "m")


def test_the_check_of_a_functional_file_says_what_is_wrong_with_the_pattern() -> None:
    from transpiler.check import check_functional
    from transpiler.model import parse_functional

    schema = {"type": "object", "properties": {"code": {"type": "string"}}}
    out = {"type": "object", "properties": {"Ok": {"type": "string"}}}

    def problems(pattern: str) -> list[str]:
        rule = {
            "kind": "field", "id": "ok", "field": "Ok", "type": "str", "required": False,
            "transform": {"expression": f"if_else(matches($.code, {pattern}), 'y', 'n')"},
        }  # fmt: skip
        file = parse_functional({"name": "m", "id": "m", "rules": [rule]}, "m")
        return [i.message for i in check_functional(file, schema, out) if i.severity == "error"]

    assert problems("'[A-Z]+[0-9]{2}'") == []
    assert any("not portable" in p for p in problems("'\\\\d+'"))
    assert any("literal text" in p for p in problems("$.code"))
