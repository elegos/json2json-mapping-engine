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

from collections.abc import Callable
from dataclasses import dataclass
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
    architecture's default `format = "round"` (default_choices) financial convention —
    deliberately not Python's banker's-rounding `round()`."""
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def _trunc_py(value: float, digits: int) -> float:
    """Truncate toward zero to `digits` decimals (`choices.format: truncate`)."""
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


# -- text, numbers, conversions, timestamps ----------------------------------------------
# The regular expressions of `regexp_replace` / `regexp_group` are Oracle's (REGEXP_*): the
# project writes them in the dialect of its backend.


def _optional_last(template2: str, template3: str) -> Callable[[list[str]], str]:
    """A rendering for a function whose last argument may be left out."""

    def render(arg_exprs: list[str]) -> str:
        return (template2 if len(arg_exprs) == 2 else template3).format(*arg_exprs)

    return render


def _round_plsql(arg_exprs: list[str]) -> str:
    return f"ROUND({', '.join(arg_exprs)})"


def _remove_prefix_plsql(arg_exprs: list[str]) -> str:
    s, prefix = arg_exprs
    return (
        f"(CASE WHEN {prefix} IS NOT NULL AND SUBSTR({s}, 1, LENGTH({prefix})) = {prefix} "
        f"THEN SUBSTR({s}, LENGTH({prefix}) + 1) ELSE {s} END)"
    )


_NLS_DOT = "'NLS_NUMERIC_CHARACTERS=''.,'''"


def _format_decimal_plsql(arg_exprs: list[str]) -> str:
    x, n = arg_exprs
    fmt = f"'FM999999999999999999990' || CASE WHEN {n} > 0 THEN '.' || RPAD('0', {n}, '0') END"
    return f"TRIM(TO_CHAR(ROUND({x}, {n}), {fmt}, {_NLS_DOT}))"


def _to_string_plsql(arg_exprs: list[str]) -> str:
    return f"TO_CHAR({arg_exprs[0]}, 'TM9')"


_FORMAT_DECIMAL_BODY = f"""\
IF p_x IS NULL THEN
        RETURN NULL;
    END IF;
    IF p_n < 0 THEN
        RAISE_APPLICATION_ERROR(-20999, 'the number of decimals cannot be negative');
    END IF;
    RETURN {_format_decimal_plsql(["p_x", "p_n"])};"""

# A timestamp is read from its pieces; no time is midnight, no offset is UTC. `to_utc` moves the
# instant to UTC, `rfc3339_normalize` keeps its offset.
_TIMESTAMP_PIECES = r"""DECLARE
        v_date VARCHAR2(10) := REGEXP_SUBSTR(p_s, '^\s*(\d{4}-\d{2}-\d{2})', 1, 1, NULL, 1);
        v_time VARCHAR2(8);
        v_frac VARCHAR2(9);
        v_zone VARCHAR2(10);
    BEGIN
        IF p_s IS NULL THEN
            RETURN NULL;
        END IF;
        IF v_date IS NULL THEN
            RAISE_APPLICATION_ERROR(-20999, 'not an ISO-8601 / RFC3339 timestamp: ' || p_s);
        END IF;
        v_time := NVL(REGEXP_SUBSTR(p_s, '[T ](\d{2}:\d{2}(:\d{2})?)', 1, 1, 'i', 1), '00:00');
        IF LENGTH(v_time) = 5 THEN
            v_time := v_time || ':00';
        END IF;
        v_frac := REGEXP_SUBSTR(p_s, '\d{2}:\d{2}:\d{2}[.,](\d{1,9})', 1, 1, NULL, 1);
        v_zone := REGEXP_SUBSTR(p_s,
            '\d{2}:\d{2}(:\d{2}([.,]\d{1,9})?)?\s*(Z|[+-]\d{2}(:?\d{2})?)\s*$', 1, 1, 'i', 3);
        v_zone := CASE
            WHEN v_zone IS NULL OR UPPER(v_zone) = 'Z' THEN '+00:00'
            WHEN LENGTH(v_zone) = 3 THEN v_zone || ':00'
            WHEN LENGTH(v_zone) = 5 THEN SUBSTR(v_zone, 1, 3) || ':' || SUBSTR(v_zone, 4)
            ELSE v_zone END;
        v_date := TO_CHAR(TO_DATE(v_date, 'YYYY-MM-DD'), 'YYYY-MM-DD'); -- an invalid date raises
"""

_TO_UTC_BODY = (
    _TIMESTAMP_PIECES
    + """\
        RETURN TO_CHAR(SYS_EXTRACT_UTC(TO_TIMESTAMP_TZ(v_date || 'T' || v_time || v_zone,
                'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM')), 'YYYY-MM-DD"T"HH24:MI:SS')
            || CASE WHEN v_frac IS NOT NULL THEN '.' || v_frac END || 'Z';
    END;"""
)

_RFC3339_BODY = (
    _TIMESTAMP_PIECES
    + """\
        RETURN v_date || 'T' || v_time || CASE WHEN v_frac IS NOT NULL THEN '.' || v_frac END
            || CASE WHEN v_zone = '+00:00' THEN 'Z' ELSE v_zone END;
    END;"""
)


BUILTIN_FUNCTIONS: dict[str, FunctionImpl] = {
    "coalesce": FunctionImpl(
        name="coalesce",
        target_templates={"plsql": "COALESCE({0}, {1})"},
    ),
    "round": FunctionImpl(
        name="round",
        target_templates={"plsql": _round_plsql},
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
    "replace": FunctionImpl(
        name="replace",
        target_templates={"plsql": _optional_last("REPLACE({0}, {1})", "REPLACE({0}, {1}, {2})")},
    ),
    "regexp_replace": FunctionImpl(
        name="regexp_replace",
        target_templates={
            "plsql": _optional_last("REGEXP_REPLACE({0}, {1})", "REGEXP_REPLACE({0}, {1}, {2})")
        },
    ),
    "regexp_group": FunctionImpl(
        name="regexp_group",
        target_templates={"plsql": "REGEXP_SUBSTR({0}, {1}, 1, 1, NULL, {2})"},
    ),
    "remove_prefix": FunctionImpl(
        name="remove_prefix", target_templates={"plsql": _remove_prefix_plsql}
    ),
    "format_decimal": FunctionImpl(
        name="format_decimal", target_templates={"plsql": _format_decimal_plsql}
    ),
    "to_number": FunctionImpl(name="to_number", target_templates={"plsql": "TO_NUMBER({0})"}),
    "to_string": FunctionImpl(name="to_string", target_templates={"plsql": _to_string_plsql}),
    # these two live in the functions package only (statements, not one expression)
    "to_utc": FunctionImpl(name="to_utc", target_templates={"plsql": "NULL"}),
    "rfc3339_normalize": FunctionImpl(name="rfc3339_normalize", target_templates={"plsql": "NULL"}),
    "count": FunctionImpl(
        # Trivial (no accumulator needed) — max/min/sum/avg need a native
        # loop and are lowered specially by the Code Generator
        # (`_materialize_aggregate`), not routed through here.
        name="count",
        target_templates={"plsql": "{0}.get_size"},
    ),
}


@dataclass(frozen=True)
class LibraryFunction:
    """A built-in that has no 1:1 PL/SQL counterpart. Mappings call it in the functions
    package (`[target.plsql] functions_package`); its body is the same expression the
    inline template renders, with the parameters as arguments."""

    params: str  # PL/SQL parameter list
    returns: str
    arg_names: list[str]
    render: Callable[[list[str]], str]
    # a body of statements, for a function that is not one expression
    body: str | None = None

    @property
    def spec(self) -> str:
        return f"{self.params}) RETURN {self.returns}"

    def body_text(self) -> str:
        return self.body or f"RETURN {self.body_expression()};"

    def body_expression(self) -> str:
        return self.render(self.arg_names)


# Not here: `if_else` (as a function both branches would be evaluated, the inline `CASE`
# is lazy), `concat` (variadic), `count` and the 1:1 ones (`coalesce`, `round`, `trunc`,
# `parse_date`), which stay inline.
_TRUTHY_BODY = """\
IF p_el IS NULL OR p_el.is_Null THEN
        RETURN FALSE;
    ELSIF p_el.is_Boolean THEN
        RETURN COALESCE(p_el.to_Boolean, FALSE);
    ELSIF p_el.is_Number THEN
        RETURN COALESCE(p_el.to_Number, 0) <> 0;
    ELSIF p_el.is_String THEN
        -- to_String is the JSON text, quotes included: the empty string is '""', not NULL
        RETURN p_el.to_String <> '""';
    ELSIF p_el.is_Array THEN
        RETURN TREAT(p_el AS JSON_ARRAY_T).get_size > 0;
    ELSIF p_el.is_Object THEN
        RETURN TREAT(p_el AS JSON_OBJECT_T).get_size > 0;
    END IF;
    RETURN TRUE;"""


def truthy_py(value) -> bool:
    """Python truthiness, which is the language's (docs/ARCHITECTURE.md, §Truthiness)."""
    return bool(value)


LIBRARY_FUNCTIONS: dict[str, LibraryFunction] = {
    # not callable from a mapping: the conditions of the code generator use it
    "truthy": LibraryFunction(
        "p_el IN JSON_ELEMENT_T", "BOOLEAN", ["p_el"], lambda a: "NULL", body=_TRUTHY_BODY
    ),
    "split_first": LibraryFunction(
        "p_s IN VARCHAR2, p_sep IN VARCHAR2",
        "VARCHAR2",
        ["p_s", "p_sep"],
        _split_first_plsql,
    ),
    "split_nth": LibraryFunction(
        "p_s IN VARCHAR2, p_sep IN VARCHAR2, p_n IN NUMBER",
        "VARCHAR2",
        ["p_s", "p_sep", "p_n"],
        _split_nth_plsql,
    ),
    "remove_prefix": LibraryFunction(
        "p_s IN VARCHAR2, p_prefix IN VARCHAR2",
        "VARCHAR2",
        ["p_s", "p_prefix"],
        _remove_prefix_plsql,
    ),
    "format_decimal": LibraryFunction(
        "p_x IN NUMBER, p_n IN NUMBER",
        "VARCHAR2",
        ["p_x", "p_n"],
        _format_decimal_plsql,
        body=_FORMAT_DECIMAL_BODY,
    ),
    # a number as text, with the leading zero Oracle's plain TO_CHAR drops (`.5`)
    "to_string": LibraryFunction("p_n IN NUMBER", "VARCHAR2", ["p_n"], _to_string_plsql),
    "to_utc": LibraryFunction(
        "p_s IN VARCHAR2", "VARCHAR2", ["p_s"], lambda a: "NULL", body=_TO_UTC_BODY
    ),
    "rfc3339_normalize": LibraryFunction(
        "p_s IN VARCHAR2", "VARCHAR2", ["p_s"], lambda a: "NULL", body=_RFC3339_BODY
    ),
    # 2 or 3 arguments: the default is the third, NULL when absent
    "lookup": LibraryFunction(
        "p_key IN VARCHAR2, p_table IN JSON_OBJECT_T, p_default IN VARCHAR2 DEFAULT NULL",
        "VARCHAR2",
        ["p_key", "p_table", "p_default"],
        _lookup_plsql,
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
