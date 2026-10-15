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

BUILTIN_LIBRARY_VERSION = "1.1.0"


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
    # INSTR rejects an occurrence below 1: the part before the first separator starts at 0, and a
    # position below 1 has no part
    start_of_n = f"(CASE WHEN {n} = 1 THEN 0 ELSE INSTR({padded}, {sep}, 1, {n} - 1) END)"
    end_of_n = f"INSTR({padded}, {sep}, 1, {n})"
    return (
        f"(CASE WHEN {n} < 1 THEN NULL WHEN {end_of_n} = 0 THEN NULL ELSE "
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


# -- text without patterns, numbers, dates (library 1.1.0) -----------------------------------
# An empty text is NULL in Oracle: the empty results of the reference implementation are NULL here
# with no extra code. Each rendering says what the reference does for a missing value.


def _right_plsql(arg_exprs: list[str]) -> str:
    s, n = arg_exprs
    return f"(CASE WHEN {n} < 1 THEN NULL ELSE SUBSTR({s}, GREATEST(LENGTH({s}) - {n} + 1, 1)) END)"


def _substring_plsql(arg_exprs: list[str]) -> str:
    s, start = arg_exprs[:2]
    if len(arg_exprs) == 2:
        return f"SUBSTR({s}, GREATEST({start}, 1))"
    return f"SUBSTR({s}, GREATEST({start}, 1), {arg_exprs[2]})"  # a length below 1 is NULL


def _pad_plsql(function: str) -> Callable[[list[str]], str]:
    def render(arg_exprs: list[str]) -> str:
        s, width = arg_exprs[:2]
        fill = arg_exprs[2] if len(arg_exprs) == 3 else "' '"
        # LPAD / RPAD cut a longer text; the reference leaves it as it is
        return (
            f"(CASE WHEN LENGTH({s}) >= {width} THEN {s} ELSE {function}({s}, {width}, {fill}) END)"
        )

    return render


def _matches_plsql(arg_exprs: list[str]) -> str:
    """The whole text fits the pattern (a literal, in the portable subset: the pipeline has checked
    it): REGEXP_LIKE looks for a match anywhere, so the pattern is anchored."""
    s, pattern = arg_exprs
    if not pattern.startswith("'"):
        raise ValueError("the pattern of matches() must be a literal text")
    return f"(CASE WHEN {s} IS NULL THEN NULL WHEN REGEXP_LIKE({s}, '^(' || {pattern} || ')$') THEN TRUE ELSE FALSE END)"


def _starts_with_plsql(arg_exprs: list[str]) -> str:
    s, prefix = arg_exprs
    return f"(CASE WHEN SUBSTR({s}, 1, LENGTH({prefix})) = {prefix} THEN TRUE ELSE FALSE END)"


def _ends_with_plsql(arg_exprs: list[str]) -> str:
    s, suffix = arg_exprs
    return f"(CASE WHEN SUBSTR({s}, -LENGTH({suffix})) = {suffix} THEN TRUE ELSE FALSE END)"


_NLS_DOT = "'NLS_NUMERIC_CHARACTERS=''.,'''"


def _format_decimal_plsql(arg_exprs: list[str]) -> str:
    x, n = arg_exprs
    fmt = f"'FM999999999999999999990' || CASE WHEN {n} > 0 THEN '.' || RPAD('0', {n}, '0') END"
    return f"TRIM(TO_CHAR(ROUND({x}, {n}), {fmt}, {_NLS_DOT}))"


_NUMBER_TEXT_FORMAT = "'FM99999999999999999999990.99999999999999999999'"
_NUMBER_FORMAT = "'99999999999999999999D999999999999999999'"  # 20 + 18 digits


def to_string_of_kind(kind: str, x: str) -> str:
    """`to_string` of an expression whose PL/SQL type is `kind`: a number with the zero before the dot
    that Oracle's TO_CHAR drops (`.5`), and no exponent, a boolean as `true` / `false`, a list or object as
    compact JSON, a text as it is."""
    if kind == "NUMBER":
        # `TM9` drops the zero before the dot (`.5`); FM with a 0 there keeps it, and the
        # unused `9`s after the dot are not written, only the point itself is left to trim
        return f"RTRIM(TO_CHAR({x}, {_NUMBER_TEXT_FORMAT}, {_NLS_DOT}), '.')"
    if kind == "BOOLEAN":
        return f"(CASE WHEN {x} THEN 'true' WHEN NOT {x} THEN 'false' END)"
    if kind in ("OBJECT", "ARRAY"):
        return f"{x}.to_String"
    if kind == "DATE":
        return f"TO_CHAR({x}, 'YYYY-MM-DD')"
    return x


def to_number_of_kind(kind: str, x: str, inside_package: bool = False) -> str:
    """`to_number` of an expression whose PL/SQL type is `kind`: a number stays, a text is read
    as one (the decimal separator is always the dot, whatever the session says). Inside the
    functions package, which declares its own `to_number`, Oracle's is `STANDARD.TO_NUMBER`: the
    plain name would only see the package's."""
    if kind == "NUMBER":
        return x
    if kind == "VARCHAR2":
        name = "STANDARD.TO_NUMBER" if inside_package else "TO_NUMBER"
        return f"{name}(TRIM({x}), {_NUMBER_FORMAT}, {_NLS_DOT})"
    raise ValueError(f"a {kind.lower()} is not a number")


def _to_string_plsql(arg_exprs: list[str]) -> str:
    return to_string_of_kind("NUMBER", arg_exprs[0])


def _to_number_plsql(arg_exprs: list[str]) -> str:
    return to_number_of_kind("VARCHAR2", arg_exprs[0])


_FORMAT_DECIMAL_BODY = f"""\
IF p_x IS NULL THEN
        RETURN NULL;
    END IF;
    IF p_n < 0 THEN
        RAISE_APPLICATION_ERROR(-20999, 'the number of decimals cannot be negative');
    END IF;
    RETURN {_format_decimal_plsql(["p_x", "p_n"])};"""

# `to_string` / `to_number` of a value read from the document: the element is looked at, so a
# number, a text, a boolean, a list or an object all convert as `to_string_of_kind` says.
# the text of a JSON string element, without its quotes and with its escapes undone (`\\"`, `\\\\`,
# `\\/`, `\\n`, `\\t`, `\\r`; a `\\uXXXX` stays as written)
_JSON_TEXT_BODY = r"""DECLARE
        v_s VARCHAR2(32767) := p_el.to_String;
    BEGIN
        v_s := SUBSTR(v_s, 2, LENGTH(v_s) - 2);
        v_s := REPLACE(v_s, '\\', CHR(1));
        v_s := REPLACE(v_s, '\"', '"');
        v_s := REPLACE(v_s, '\/', '/');
        v_s := REPLACE(v_s, '\n', CHR(10));
        v_s := REPLACE(v_s, '\t', CHR(9));
        v_s := REPLACE(v_s, '\r', CHR(13));
        RETURN REPLACE(v_s, CHR(1), '\');
    END;"""

# `to_string` / `to_number` of a value read from the document: the element is looked at, so a
# number, a text, a boolean, a list or an object all convert as `to_string_of_kind` says.
_TO_STRING_BODY = f"""\
IF p_el IS NULL OR p_el.is_Null THEN
        RETURN NULL;
    ELSIF p_el.is_Number THEN
        RETURN {to_string_of_kind("NUMBER", "p_el.to_Number")};
    ELSIF p_el.is_Boolean THEN
        RETURN {to_string_of_kind("BOOLEAN", "p_el.to_Boolean")};
    ELSIF p_el.is_String THEN
        RETURN json_text(p_el);
    END IF;
    RETURN p_el.to_String;"""

_TO_NUMBER_BODY = f"""\
IF p_el IS NULL OR p_el.is_Null THEN
        RETURN NULL;
    ELSIF p_el.is_Number THEN
        RETURN p_el.to_Number;
    ELSIF p_el.is_String THEN
        RETURN {to_number_of_kind("VARCHAR2", "json_text(p_el)", inside_package=True)};
    END IF;
    RAISE_APPLICATION_ERROR(-20999, 'not a number: ' || p_el.to_String);"""

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

# the fraction of a second as written, or with `p_digits` digits (0: none)
_FRAC = (
    "(CASE WHEN p_digits IS NULL THEN v_frac WHEN p_digits < 1 THEN NULL "
    "ELSE SUBSTR(RPAD(NVL(v_frac, '0'), 9, '0'), 1, p_digits) END)"
)

_TO_UTC_BODY = (
    _TIMESTAMP_PIECES
    + """\
        RETURN TO_CHAR(SYS_EXTRACT_UTC(TO_TIMESTAMP_TZ(v_date || 'T' || v_time || v_zone,
                'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM')), 'YYYY-MM-DD"T"HH24:MI:SS')
            || NVL2(_FRAC_, '.' || _FRAC_, NULL) || 'Z';
    END;"""
).replace("_FRAC_", _FRAC)

_RFC3339_BODY = (
    _TIMESTAMP_PIECES
    + """\
        RETURN v_date || 'T' || v_time || NVL2(_FRAC_, '.' || _FRAC_, NULL)
            || CASE WHEN v_zone = '+00:00' THEN 'Z' ELSE v_zone END;
    END;"""
).replace("_FRAC_", _FRAC)

# a date or a date and time, written with a format: read from its pieces (as the timestamps are),
# the offset ignored
_FORMAT_DATE_BODY = (
    _TIMESTAMP_PIECES.replace(
        "v_zone VARCHAR2(10);", "v_zone VARCHAR2(10);\n        v_fmt VARCHAR2(200);"
    )
    + """\
        -- only the six tokens and separators, as the reference accepts (Oracle knows many more)
        v_fmt := REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(p_fmt),
            'YYYY'), 'HH24'), 'MM'), 'DD'), 'MI'), 'SS');
        -- (an empty text is NULL in Oracle: the lengths are taken with NVL)
        IF NVL(LENGTH(TRANSLATE(v_fmt, '#ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', '#')), 0)
                <> NVL(LENGTH(v_fmt), 0) THEN
            RAISE_APPLICATION_ERROR(-20999, 'not a date format: ' || p_fmt);
        END IF;
        RETURN TO_CHAR(TO_TIMESTAMP(v_date || ' ' || v_time, 'YYYY-MM-DD HH24:MI:SS'), p_fmt);
    END;"""
)

# a date and time written as a format, read in English, as ISO-8601 without a zone; only the tokens
# of the reference (Oracle knows many more) and a year, a month and a day
_PARSE_TIMESTAMP_BODY = """\
DECLARE
        v_fmt VARCHAR2(200);
        v_up VARCHAR2(200);
    BEGIN
        IF p_s IS NULL OR p_fmt IS NULL THEN
            RETURN NULL;
        END IF;
        v_up := UPPER(p_fmt);
        v_fmt := REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(v_up,
            'YYYY'), 'HH24'), 'HH12'), 'MON'), 'MM'), 'DD'), 'MI'), 'SS'), 'AM');
        -- (an empty text is NULL in Oracle: the lengths are taken with NVL)
        IF NVL(LENGTH(TRANSLATE(v_fmt, '#ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', '#')), 0)
                <> NVL(LENGTH(v_fmt), 0) THEN
            RAISE_APPLICATION_ERROR(-20999, 'not a date format: ' || p_fmt);
        END IF;
        IF INSTR(v_up, 'YYYY') = 0 OR INSTR(v_up, 'DD') = 0
                OR (INSTR(REPLACE(v_up, 'MON'), 'MM') = 0 AND INSTR(v_up, 'MON') = 0) THEN
            RAISE_APPLICATION_ERROR(-20999,
                'a date format needs a year, a month and a day: ' || p_fmt);
        END IF;
        RETURN TO_CHAR(TO_TIMESTAMP(p_s, p_fmt, 'NLS_DATE_LANGUAGE=ENGLISH'),
            'YYYY-MM-DD"T"HH24:MI:SS');
    END;"""

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
    "split_list": FunctionImpl(name="split_list", target_templates={"plsql": "NULL"}),
    "split_last": FunctionImpl(
        name="split_last",
        target_templates={
            "plsql": "(CASE WHEN INSTR({0}, {1}, -1) = 0 THEN {0} "
            "ELSE SUBSTR({0}, INSTR({0}, {1}, -1) + LENGTH({1})) END)"
        },
    ),
    "is_digits": FunctionImpl(
        name="is_digits",
        target_templates={
            "plsql": "(CASE WHEN {0} IS NULL THEN NULL "
            "WHEN REGEXP_LIKE({0}, '^[0-9]+$') THEN TRUE ELSE FALSE END)"
        },
    ),
    "days_between": FunctionImpl(
        name="days_between",
        target_templates={
            "plsql": "(TO_DATE(SUBSTR(TRIM({1}), 1, 10), 'YYYY-MM-DD') "
            "- TO_DATE(SUBSTR(TRIM({0}), 1, 10), 'YYYY-MM-DD'))"
        },
    ),
    "add_days": FunctionImpl(
        name="add_days",
        target_templates={
            "plsql": "TO_CHAR(TO_DATE(SUBSTR(TRIM({0}), 1, 10), 'YYYY-MM-DD') + TRUNC({1}), "
            "'YYYY-MM-DD')"
        },
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
    "to_number": FunctionImpl(name="to_number", target_templates={"plsql": _to_number_plsql}),
    "to_string": FunctionImpl(name="to_string", target_templates={"plsql": _to_string_plsql}),
    # rendered by the code generator, by the type of the value (or in the functions package)
    "is_empty": FunctionImpl(name="is_empty", target_templates={"plsql": "NULL"}),
    # these two live in the functions package only (statements, not one expression)
    "to_utc": FunctionImpl(name="to_utc", target_templates={"plsql": "NULL"}),
    "rfc3339_normalize": FunctionImpl(name="rfc3339_normalize", target_templates={"plsql": "NULL"}),
    "upper": FunctionImpl(name="upper", target_templates={"plsql": "UPPER({0})"}),
    "lower": FunctionImpl(name="lower", target_templates={"plsql": "LOWER({0})"}),
    "trim": FunctionImpl(name="trim", target_templates={"plsql": "TRIM({0})"}),
    "length": FunctionImpl(name="length", target_templates={"plsql": "LENGTH({0})"}),
    "substring": FunctionImpl(name="substring", target_templates={"plsql": _substring_plsql}),
    "left": FunctionImpl(name="left", target_templates={"plsql": "SUBSTR({0}, 1, {1})"}),
    "right": FunctionImpl(name="right", target_templates={"plsql": _right_plsql}),
    "pad_left": FunctionImpl(name="pad_left", target_templates={"plsql": _pad_plsql("LPAD")}),
    "pad_right": FunctionImpl(name="pad_right", target_templates={"plsql": _pad_plsql("RPAD")}),
    "contains": FunctionImpl(
        name="contains",
        target_templates={"plsql": "(CASE WHEN INSTR({0}, {1}) > 0 THEN TRUE ELSE FALSE END)"},
    ),
    "matches": FunctionImpl(name="matches", target_templates={"plsql": _matches_plsql}),
    "starts_with": FunctionImpl(name="starts_with", target_templates={"plsql": _starts_with_plsql}),
    "ends_with": FunctionImpl(name="ends_with", target_templates={"plsql": _ends_with_plsql}),
    "abs": FunctionImpl(name="abs", target_templates={"plsql": "ABS({0})"}),
    "floor": FunctionImpl(name="floor", target_templates={"plsql": "FLOOR({0})"}),
    "ceil": FunctionImpl(name="ceil", target_templates={"plsql": "CEIL({0})"}),
    # lives in the functions package only (statements, not one expression)
    "format_date": FunctionImpl(name="format_date", target_templates={"plsql": "NULL"}),
    "parse_timestamp": FunctionImpl(name="parse_timestamp", target_templates={"plsql": "NULL"}),
    "count": FunctionImpl(
        # Trivial (no accumulator needed) — max/min/sum/avg need a native
        # loop and are lowered specially by the Code Generator
        # (`_materialize_aggregate`), not routed through here.
        name="count",
        target_templates={"plsql": "(CASE WHEN {0} IS NULL THEN 0 ELSE {0}.get_size END)"},
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


# `is_empty` of a value read from the document: the element is looked at (a typed value is
# tested inline by the code generator, by its type).
_IS_EMPTY_BODY = """\
IF p_el IS NULL OR p_el.is_Null THEN
        RETURN TRUE;
    ELSIF p_el.is_String THEN
        -- to_String is the JSON text, quotes included: the empty string is '""', not NULL
        RETURN p_el.to_String = '""';
    ELSIF p_el.is_Number THEN
        RETURN COALESCE(p_zero, FALSE) AND p_el.to_Number = 0;
    END IF;
    RETURN FALSE;"""


_SPLIT_LIST_BODY = """\
IF p_s IS NULL OR p_sep IS NULL THEN
        RETURN NULL;
    END IF;
    DECLARE
        v_arr  JSON_ARRAY_T := JSON_ARRAY_T();
        v_pos  PLS_INTEGER := 1;
        v_next PLS_INTEGER;
        v_part VARCHAR2(32767);
    BEGIN
        LOOP
            v_next := INSTR(p_s, p_sep, v_pos);
            IF v_next = 0 THEN
                v_part := SUBSTR(p_s, v_pos);
            ELSE
                v_part := SUBSTR(p_s, v_pos, v_next - v_pos);
            END IF;
            IF v_part IS NULL THEN
                v_arr.append_Null;
            ELSE
                v_arr.append(v_part);
            END IF;
            EXIT WHEN v_next = 0;
            v_pos := v_next + LENGTH(p_sep);
        END LOOP;
        RETURN v_arr;
    END;"""


def truthy_py(value) -> bool:
    """Python truthiness, which is the language's (docs/ARCHITECTURE.md, §Truthiness)."""
    return bool(value)


LIBRARY_FUNCTIONS: dict[str, LibraryFunction] = {
    # not callable from a mapping: the conditions of the code generator use it
    "truthy": LibraryFunction(
        "p_el IN JSON_ELEMENT_T", "BOOLEAN", ["p_el"], lambda a: "NULL", body=_TRUTHY_BODY
    ),
    "is_empty": LibraryFunction(
        "p_el IN JSON_ELEMENT_T, p_zero IN BOOLEAN DEFAULT FALSE",
        "BOOLEAN",
        ["p_el", "p_zero"],
        lambda a: "NULL",
        body=_IS_EMPTY_BODY,
    ),
    "split_first": LibraryFunction(
        "p_s IN VARCHAR2, p_sep IN VARCHAR2",
        "VARCHAR2",
        ["p_s", "p_sep"],
        _split_first_plsql,
    ),
    # the parts of a text as a list, for a loop
    "split_list": LibraryFunction(
        "p_s IN VARCHAR2, p_sep IN VARCHAR2",
        "JSON_ARRAY_T",
        ["p_s", "p_sep"],
        lambda a: "NULL",
        body=_SPLIT_LIST_BODY,
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
    # not callable from a mapping: the text inside a JSON string element
    "json_text": LibraryFunction(
        "p_el IN JSON_ELEMENT_T", "VARCHAR2", ["p_el"], lambda a: "NULL", body=_JSON_TEXT_BODY
    ),
    # the value read from the document, as its element
    "to_string": LibraryFunction(
        "p_el IN JSON_ELEMENT_T", "VARCHAR2", ["p_el"], lambda a: "NULL", body=_TO_STRING_BODY
    ),
    "to_number": LibraryFunction(
        "p_el IN JSON_ELEMENT_T", "NUMBER", ["p_el"], lambda a: "NULL", body=_TO_NUMBER_BODY
    ),
    # the second argument may be left out: the fraction of a second as written
    "to_utc": LibraryFunction(
        "p_s IN VARCHAR2, p_digits IN NUMBER DEFAULT NULL",
        "VARCHAR2",
        ["p_s", "p_digits"],
        lambda a: "NULL",
        body=_TO_UTC_BODY,
    ),
    "rfc3339_normalize": LibraryFunction(
        "p_s IN VARCHAR2, p_digits IN NUMBER DEFAULT NULL",
        "VARCHAR2",
        ["p_s", "p_digits"],
        lambda a: "NULL",
        body=_RFC3339_BODY,
    ),
    "parse_timestamp": LibraryFunction(
        "p_s IN VARCHAR2, p_fmt IN VARCHAR2",
        "VARCHAR2",
        ["p_s", "p_fmt"],
        lambda a: "NULL",
        body=_PARSE_TIMESTAMP_BODY,
    ),
    "format_date": LibraryFunction(
        "p_s IN VARCHAR2, p_fmt IN VARCHAR2",
        "VARCHAR2",
        ["p_s", "p_fmt"],
        lambda a: "NULL",
        body=_FORMAT_DATE_BODY,
    ),
    # 2 or 3 arguments: the default is the third, NULL when absent
    "lookup": LibraryFunction(
        "p_key IN VARCHAR2, p_table IN JSON_OBJECT_T, p_default IN VARCHAR2 DEFAULT NULL",
        "VARCHAR2",
        ["p_key", "p_table", "p_default"],
        _lookup_plsql,
    ),
}

# Library functions another library function calls: deployed with it.
LIBRARY_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "to_string": ("json_text",),
    "to_number": ("json_text",),
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
