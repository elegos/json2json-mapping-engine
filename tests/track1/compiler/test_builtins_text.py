"""The text, conversion and timestamp built-ins: their reference semantics (`compiler/builtins.py`),
what the Python backend runs, and the PL/SQL they are rendered to."""

from __future__ import annotations

import pytest

from compiler import builtins as b
from compiler.backends.plsql.builtins import (
    BUILTIN_FUNCTIONS,
    LIBRARY_FUNCTIONS,
    to_number_of_kind,
    to_string_of_kind,
)


def test_replace_and_remove_prefix() -> None:
    assert b.replace("a-b-c", "-", "+") == "a+b+c"
    assert b.replace("a-b-c", "-") == "abc"  # no replacement removes
    assert b.replace("abc", "") == "abc"  # nothing to search for
    assert b.replace(None, "x") is None  # pyright: ignore[reportArgumentType]
    assert b.remove_prefix("pre_x", "pre_") == "x"
    assert b.remove_prefix("x", "pre_") == "x" and b.remove_prefix("x", "") == "x"


def test_regular_expressions_in_the_dialect_both_backends_share() -> None:
    assert b.regexp_replace("a1b22", r"\d+", "#") == "a#b#"
    assert b.regexp_replace("a1b22", r"\d+") == "ab"
    assert b.regexp_replace("john smith", r"(\w+) (\w+)", r"\2, \1") == "smith, john"
    assert b.regexp_group("ab-12", r"(\w+)-(\d+)", 2) == "12"
    assert b.regexp_group("ab-12", r"(\w+)-(\d+)", 0) == "ab-12"
    assert b.regexp_group("ab-12", r"(\w+)-(\d+)", 3) is None  # no such group
    assert b.regexp_group("nothing", r"\d+", 0) is None


def test_format_decimal_keeps_the_trailing_zeros_and_rounds_half_away_from_zero() -> None:
    assert b.format_decimal(2.5, 2) == "2.50"
    assert b.format_decimal(2.345, 2) == "2.35" and b.format_decimal(-2.345, 2) == "-2.35"
    assert b.format_decimal(7, 0) == "7"
    assert b.format_decimal(-0.001, 2) == "0.00"  # no negative zero
    with pytest.raises(ValueError, match="negative"):
        b.format_decimal(1, -1)


def test_conversions() -> None:
    assert b.to_number("12") == 12 and isinstance(b.to_number("12"), int)
    assert b.to_number(" 1.50 ") == 1.5 and b.to_number(3) == 3
    assert b.to_number("") is None and b.to_number(None) is None
    with pytest.raises(ValueError):
        b.to_number("abc")
    assert b.to_string(5) == "5" and b.to_string(5.0) == "5" and b.to_string(0.5) == "0.5"
    assert b.to_string(1e-07) == "0.0000001" and b.to_string(True) == "true"
    assert b.to_string({"a": [1]}) == '{"a":[1]}' and b.to_string(None) is None


def test_timestamps() -> None:
    assert b.to_utc("2026-10-03T09:30:15.250+02:00") == "2026-10-03T07:30:15.250Z"
    assert b.to_utc("2026-10-03 07:30Z") == "2026-10-03T07:30:00Z"
    assert b.to_utc("2026-10-03T23:30-0200") == "2026-10-04T01:30:00Z"  # across midnight
    assert b.to_utc("2026-10-03") == "2026-10-03T00:00:00Z"
    assert b.rfc3339_normalize("2026-10-03 09:30+0200") == "2026-10-03T09:30:00+02:00"
    assert b.rfc3339_normalize("2026-10-03T09:30:00+00:00") == "2026-10-03T09:30:00Z"
    for bad in ("yesterday", "2026-13-03T10:00:00Z"):
        with pytest.raises(ValueError):
            b.to_utc(bad)


def test_round_digits_are_optional() -> None:
    assert b.round(2.5) == 3 and b.round(2.345, 2) == 2.35


@pytest.mark.parametrize(
    "name",
    [
        "replace",
        "regexp_replace",
        "regexp_group",
        "remove_prefix",
        "format_decimal",
        "to_number",
        "to_string",
        "to_utc",
        "rfc3339_normalize",
    ],
)
def test_every_new_builtin_has_a_plsql_rendering(name: str) -> None:
    assert name in BUILTIN_FUNCTIONS


def test_plsql_renderings() -> None:
    plsql = lambda n, *a: BUILTIN_FUNCTIONS[n].render("plsql", list(a))  # noqa: E731
    assert plsql("replace", "s", "'-'") == "REPLACE(s, '-')"
    assert plsql("replace", "s", "'-'", "'+'") == "REPLACE(s, '-', '+')"
    assert plsql("regexp_replace", "s", "'a+'") == "REGEXP_REPLACE(s, 'a+')"
    assert plsql("regexp_group", "s", "'(a)'", "1") == "REGEXP_SUBSTR(s, '(a)', 1, 1, NULL, 1)"
    assert plsql("round", "x") == "ROUND(x)" and plsql("round", "x", "2") == "ROUND(x, 2)"
    assert plsql("to_number", "s").startswith("TO_NUMBER(TRIM(s), '9999")
    assert "'FM99999999999999999999990.9" in plsql("to_string", "n")
    # conversions follow the type of what they are given: idempotent whatever it is
    assert to_string_of_kind("VARCHAR2", "x") == "x"
    assert to_string_of_kind("NUMBER", "x").startswith("RTRIM(TO_CHAR(x, 'FM9")
    assert "'true'" in to_string_of_kind("BOOLEAN", "x")
    assert to_string_of_kind("OBJECT", "x") == "x.to_String"
    assert to_number_of_kind("NUMBER", "x") == "x"
    with pytest.raises(ValueError, match="boolean"):
        to_number_of_kind("BOOLEAN", "x")
    # the ones that are statements are in the functions package
    for name in ("remove_prefix", "format_decimal", "to_string", "to_utc", "rfc3339_normalize"):
        assert name in LIBRARY_FUNCTIONS
    assert "SYS_EXTRACT_UTC" in LIBRARY_FUNCTIONS["to_utc"].body_text()
    assert "SYS_EXTRACT_UTC" not in LIBRARY_FUNCTIONS["rfc3339_normalize"].body_text()


def test_the_limits_of_to_number_are_in_its_description() -> None:
    """What the explorer and the guide show: the limits must be said, not found out."""
    from compiler.function_registry import builtin_functions

    doc = builtin_functions()["to_number"].doc
    for limit in (
        "plain decimal",
        "exponent",
        "thousands",
        "decimal comma",
        "20 digits",
        "18",
        "boolean",
    ):
        assert limit in doc, limit
    assert b.to_number("1" * 20) == int("1" * 20) and b.to_number("." + "1" * 18) == float(
        "." + "1" * 18
    )
    for text in ("1e3", "1,200", "3,5", "$5", "12%", "", "-", "1.2.3", "1" * 21, "." + "1" * 19):
        if text in ("",):
            assert b.to_number(text) is None
        else:
            with pytest.raises(ValueError):
                b.to_number(text)


def test_the_functions_package_does_not_hide_an_oracle_function_it_calls() -> None:
    """A package that declares `to_number` sees only its own from the inside: a call to Oracle's
    must be qualified (`STANDARD.TO_NUMBER`), or the package does not compile and with it no mapping."""
    import re

    for name, function in LIBRARY_FUNCTIONS.items():
        bare = re.compile(rf"(?<![\w.]){name}\s*\(", re.IGNORECASE)
        body = function.body_text()
        assert not bare.search(body), f"{name}: the body calls {name}() unqualified"
    assert "STANDARD.TO_NUMBER(" in LIBRARY_FUNCTIONS["to_number"].body_text()


def test_a_library_function_that_calls_another_is_deployed_with_it() -> None:
    """`to_string` calls `json_text`: a package that declares the first without the second does
    not compile (PLS-00201), and with it no mapping."""

    from compiler.backends.plsql.backend import PlsqlBackend
    from compiler.pipeline import compile_unit

    backend = PlsqlBackend({"schema": "S", "error_code": -20000, "mapping_package_prefix": "M_"})
    source = "from __mapping__ import *\ndef a(root: Any) -> str | None:\n    return to_string(root.n)\nout.A = a(root)\n"
    unit = compile_unit(source, "m", backend)
    package = backend.assemble([unit])["j2jme_functions.sql"]
    assert package.count("FUNCTION json_text(") == 2  # in the spec and in the body


def test_is_empty() -> None:
    assert b.is_empty(None) and b.is_empty("")
    assert not b.is_empty(" ") and not b.is_empty("0") and not b.is_empty(False)
    assert not b.is_empty([]) and not b.is_empty({})
    assert not b.is_empty(0) and b.is_empty(0, True) and b.is_empty(0.0, True)
    assert not b.is_empty(5, True) and not b.is_empty(False, True)
