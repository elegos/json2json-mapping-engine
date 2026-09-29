"""Built-in function library, PL/SQL target (docs/ARCHITECTURE.md, §Built-in
functions).

Each built-in has a `python_impl` — the reference implementation, callable
and testable with standard Python tooling, independent of any target
runtime — and a PL/SQL rendering used by the Code Generator. `.fn` files
reference the same vocabulary; a project function of the same name
overrides the entry here entirely for its target (§Project functions and
overrides, resolution priority 1-2 beat this module's priority 3).

Versioning: the built-in library is versioned as a whole with the tool,
using SemVer (§Built-in functions) — `BUILTIN_LIBRARY_VERSION` below. Adding
a function is MINOR; changing a signature is MAJOR; fixing a target
rendering with no interface change is PATCH. Per-function `since` tracks the
library version a given built-in first appeared in, for future
compatibility tooling (the `.fn.yaml` dependency-tracking machinery that
consumes this is a Build CLI concern, M3, not built here).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from compiler.function_linker import FunctionImpl

BUILTIN_LIBRARY_VERSION = "1.0.0"


def _quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


# -- coalesce -----------------------------------------------------------------


def _coalesce_py(a, b):
    return b if a is None else a


# -- round ----------------------------------------------------------------------


def _round_py(value: float, digits: int) -> float:
    """Round-half-up (away from zero for negatives), matching the
    architecture's default `decimal_mode = "round"` financial convention —
    deliberately not Python's banker's-rounding `round()`."""
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def _trunc_py(value: float, digits: int) -> float:
    """Truncate toward zero to `digits` decimals (`format_mode: truncate`)."""
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_DOWN))


# -- concat (variadic) -----------------------------------------------------------


def _concat_py(*parts: str) -> str:
    return "".join(parts)


def _concat_plsql(arg_exprs: list[str]) -> str:
    if not arg_exprs:
        return "''"
    return "(" + " || ".join(arg_exprs) + ")"


# -- if_else --------------------------------------------------------------------


def _if_else_py(cond: bool, a, b):
    return a if cond else b


# -- split_first / split_nth -----------------------------------------------------


def _split_first_py(s: str, sep: str) -> str:
    return s.split(sep, 1)[0]


def _split_first_plsql(arg_exprs: list[str]) -> str:
    s, sep = arg_exprs
    return f"SUBSTR({s}, 1, INSTR({s} || {sep}, {sep}) - 1)"


def _split_nth_py(s: str, sep: str, n: int) -> str | None:
    parts = s.split(sep)
    return parts[n - 1] if 0 < n <= len(parts) else None


def _split_nth_plsql(arg_exprs: list[str]) -> str:
    s, sep, n = arg_exprs
    padded = f"({s} || {sep})"
    start_of_n = f"INSTR({padded}, {sep}, 1, {n} - 1)"
    end_of_n = f"INSTR({padded}, {sep}, 1, {n})"
    return (
        f"(CASE WHEN {end_of_n} = 0 THEN NULL ELSE "
        f"SUBSTR({padded}, {start_of_n} + LENGTH({sep}), {end_of_n} - {start_of_n} - LENGTH({sep})) "
        "END)"
    )


# -- lookup (variadic: 2 or 3 args) ----------------------------------------------


def _lookup_py(to_map, table: dict, default=None):
    return table.get(to_map, default)


def _lookup_plsql(arg_exprs: list[str]) -> str:
    if len(arg_exprs) == 2:
        to_map, table = arg_exprs
        default = "NULL"
    elif len(arg_exprs) == 3:
        to_map, table, default = arg_exprs
    else:
        raise ValueError(f"lookup() takes 2 or 3 arguments, got {len(arg_exprs)}")
    return f"(CASE WHEN {table}.has({to_map}) THEN {table}.get_String({to_map}) ELSE {default} END)"


# -- parse_date -------------------------------------------------------------------

_ORACLE_TO_STRPTIME = {
    "YYYY": "%Y",
    "MM": "%m",
    "DD": "%d",
    "HH24": "%H",
    "MI": "%M",
    "SS": "%S",
}


def _parse_date_py(s: str, fmt: str) -> date:
    py_fmt = fmt
    for oracle_token, py_token in _ORACLE_TO_STRPTIME.items():
        py_fmt = py_fmt.replace(oracle_token, py_token)
    return datetime.strptime(s, py_fmt).date()


BUILTIN_FUNCTIONS: dict[str, FunctionImpl] = {
    "coalesce": FunctionImpl(
        name="coalesce",
        target_templates={"plsql": "COALESCE({0}, {1})"},
    ),
    "round": FunctionImpl(
        name="round",
        target_templates={"plsql": "ROUND({0}, {1})"},
    ),
    "trunc": FunctionImpl(
        name="trunc",
        target_templates={"plsql": "TRUNC({0}, {1})"},
    ),
    "concat": FunctionImpl(
        name="concat",
        target_templates={"plsql": _concat_plsql},
    ),
    "if_else": FunctionImpl(
        name="if_else",
        target_templates={"plsql": "(CASE WHEN {0} THEN {1} ELSE {2} END)"},
    ),
    "split_first": FunctionImpl(
        name="split_first",
        target_templates={"plsql": _split_first_plsql},
    ),
    "split_nth": FunctionImpl(
        name="split_nth",
        target_templates={"plsql": _split_nth_plsql},
    ),
    "lookup": FunctionImpl(
        name="lookup",
        target_templates={"plsql": _lookup_plsql},
    ),
    "parse_date": FunctionImpl(
        name="parse_date",
        target_templates={"plsql": "TO_DATE({0}, {1})"},
    ),
    "count": FunctionImpl(
        # Trivial (no accumulator needed) — max/min/sum/avg need a native
        # loop and are lowered specially by the Code Generator
        # (`_materialize_aggregate`), not routed through here.
        name="count",
        target_templates={"plsql": "{0}.get_size"},
    ),
}

# Python reference implementations, kept alongside (not inside) FunctionImpl
# since FunctionImpl is target-rendering infrastructure shared with project
# `fn/` overrides, which may not have a Python body at all (target-only
# `@override`). Exposed for Track-1-style unit testing of the reference
# semantics, independent of any target.
BUILTIN_PYTHON_REFERENCE = {
    "coalesce": _coalesce_py,
    "round": _round_py,
    "trunc": _trunc_py,
    "concat": _concat_py,
    "if_else": _if_else_py,
    "split_first": _split_first_py,
    "split_nth": _split_nth_py,
    "lookup": _lookup_py,
    "parse_date": _parse_date_py,
    "count": len,
}

BUILTIN_SINCE_VERSION = {name: "1.0.0" for name in BUILTIN_FUNCTIONS}
