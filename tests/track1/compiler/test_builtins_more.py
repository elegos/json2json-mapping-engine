# pyright: reportArgumentType=false
"""The built-ins that replace the patterns a functional would otherwise reach for (text case,
trimming, parts, padding, tests, rounding of a number, a date written in a format): their
reference semantics (`compiler/builtins.py`) and the PL/SQL they are rendered to."""

from __future__ import annotations

import pytest

from compiler import builtins as b
from compiler.backends.plsql.builtins import BUILTIN_FUNCTIONS, LIBRARY_FUNCTIONS
from compiler.function_registry import builtin_functions

NEW = [
    "upper", "lower", "trim", "length", "substring", "left", "right", "pad_left", "pad_right",
    "contains", "starts_with", "ends_with", "abs", "floor", "ceil", "format_date",
]  # fmt: skip


@pytest.mark.parametrize("name", NEW)
def test_every_new_builtin_is_in_the_registry_and_has_a_plsql_rendering(name: str) -> None:
    assert name in builtin_functions() and builtin_functions()[name].doc
    assert name in BUILTIN_FUNCTIONS


def test_case_and_trim() -> None:
    assert b.upper("aB-1") == "AB-1" and b.lower("aB-1") == "ab-1"
    assert b.upper(None) is None and b.upper("") is None
    assert b.trim("  a b ") == "a b" and b.trim("   ") is None and b.trim(None) is None
    assert b.trim("\ta\t") == "\ta\t"  # only spaces
    assert b.length("abc") == 3 and b.length("") is None and b.length(None) is None


def test_parts_of_a_text() -> None:
    assert b.substring("abcdef", 2, 3) == "bcd" and b.substring("abcdef", 4) == "def"
    assert b.substring("abcdef", 0, 2) == "ab" and b.substring("abcdef", -3, 2) == "ab"
    assert b.substring("abc", 4, 2) is None and b.substring("abc", 1, 0) is None
    assert b.substring(None, 1, 2) is None
    assert b.left("abcdef", 3) == "abc" and b.left("ab", 5) == "ab" and b.left("ab", 0) is None
    assert b.right("abcdef", 3) == "def" and b.right("ab", 5) == "ab" and b.right("ab", 0) is None
    assert b.left(None, 2) is None and b.right(None, 2) is None


def test_padding_never_cuts_a_longer_text() -> None:
    assert b.pad_left("42", 5, "0") == "00042" and b.pad_left("42", 5) == "   42"
    assert b.pad_left("123456", 5, "0") == "123456"
    assert b.pad_right("ab", 5, ".") == "ab..." and b.pad_right("abcdef", 3, ".") == "abcdef"
    assert b.pad_left(None, 5, "0") is None


def test_the_tests_are_false_for_a_missing_value() -> None:
    assert b.contains("a-b", "-") is True and b.contains("ab", "-") is False
    assert b.contains(None, "-") is False and b.contains("ab", "") is False
    assert b.starts_with("ab-1", "ab") is True and b.starts_with("ab", "abc") is False
    assert b.ends_with("ab-1", "-1") is True and b.ends_with(None, "x") is False
    assert b.starts_with("ab", None) is False


def test_numbers() -> None:
    assert b.abs(-2.5) == 2.5
    assert b.floor(-2.5) == -3 and b.ceil(-2.5) == -2 and b.floor(3) == 3 and b.ceil(3) == 3


def test_format_date() -> None:
    assert b.format_date("2026-10-03", "DD/MM/YYYY") == "03/10/2026"
    assert (
        b.format_date("2026-10-03T09:05:07+02:00", "YYYY-MM-DD HH24:MI:SS") == "2026-10-03 09:05:07"
    )
    assert b.format_date("2026-10-03", "hh24:mi") == "00:00"  # no time is midnight; any case
    assert b.format_date("2026-10-03", "YYYYMMDD") == "20261003"
    assert b.format_date(None, "YYYY") is None and b.format_date("2026-10-03", "") is None
    for bad in ("MON", "YY", "DD month", "YYYY-Q", "2026"):
        with pytest.raises(ValueError, match="not a date format"):
            b.format_date("2026-10-03", bad)
    with pytest.raises(ValueError):
        b.format_date("03/10/2026", "YYYY")  # the source is ISO-8601


def test_plsql_renderings_use_no_patterns() -> None:
    plsql = lambda n, *a: BUILTIN_FUNCTIONS[n].render("plsql", list(a))  # noqa: E731
    assert plsql("upper", "s") == "UPPER(s)" and plsql("trim", "s") == "TRIM(s)"
    assert plsql("substring", "s", "2", "3") == "SUBSTR(s, GREATEST(2, 1), 3)"
    assert plsql("substring", "s", "2") == "SUBSTR(s, GREATEST(2, 1))"
    assert plsql("left", "s", "3") == "SUBSTR(s, 1, 3)"
    assert "GREATEST(LENGTH(s) - n + 1, 1)" in plsql("right", "s", "n")
    # LPAD / RPAD cut a text that is longer than the width; the reference does not
    assert plsql("pad_left", "s", "5", "'0'").startswith("(CASE WHEN LENGTH(s) >= 5 THEN s")
    assert "RPAD(s, 5, ' ')" in plsql("pad_right", "s", "5")
    assert "ELSE FALSE" in plsql("contains", "s", "p")
    for name in NEW:
        assert "REGEXP" not in plsql(name, *["a"] * len(builtin_functions()[name].params)).upper()


def test_format_date_is_in_the_functions_package_and_checks_its_format() -> None:
    body = LIBRARY_FUNCTIONS["format_date"].body_text()
    assert "not a date format" in body and "TO_TIMESTAMP(v_date" in body
