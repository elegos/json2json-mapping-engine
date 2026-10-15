"""The built-in functions of the mapping language, as plain typed Python.

This file is the **registry** of the built-ins: their names, parameters, types and
documentation are read from it (with `ast`, see `compiler.function_registry`) by the type
checker, by the desktop tool's completion and by the `__mapping__.pyi` IDE stub. A function
added here shows up in all of them; the conformance test requires every backend to implement
it. The bodies are the reference semantics (what the Python backend will run, and what the
backends are tested against).

A project can add functions, or replace one of these, in its `fn/*.fn` files, which are
read the same way. `@special` marks a built-in whose result type depends on its arguments or
that is lowered by the backend in its own way (loops for aggregates): the type checker types
those by hand, the signature here is for completion and documentation.
"""

from __future__ import annotations

import builtins as _py
import json
import math
import re
from collections.abc import Mapping
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from compiler.function_registry import special


def _quantize(x: float, digits: int, mode: str) -> float:
    if x is None:
        return None  # type: ignore[return-value]
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-digits), rounding=mode))


def _total(values: list[Any]) -> Any:
    """The sum of numbers, as the decimal numbers of the database add them (0.1 + 0.2 is 0.3)."""
    if _py.any(isinstance(v, float) for v in values):
        return float(_py.sum(Decimal(repr(v)) for v in values))
    return _py.sum(values)


def _column(items: list[Any], field: str) -> list[Any]:
    """The values to aggregate: a missing one is left out, as SQL does."""
    values = [i.get(field) if field else i for i in items or []]
    return [v for v in values if v is not None]


def round(x: float, digits: int = 0) -> float:  # noqa: A001
    """`x` rounded to `digits` decimals (half away from zero); to a whole number without `digits`."""
    return _quantize(x, digits, ROUND_HALF_UP)


def trunc(x: float, digits: int) -> float:
    """`x` cut to `digits` decimals, without rounding."""
    return _quantize(x, digits, ROUND_DOWN)


def split_first(s: str, sep: str) -> str:
    """The text before the first `sep` (all of `s` when there is none); null when that is empty."""
    if s is None:
        return None  # type: ignore[return-value]
    return s.split(sep, 1)[0] or None  # type: ignore[return-value]


def split_nth(s: str, sep: str, n: int) -> str | None:
    """The `n`-th part (counted from 1) of `s` split at `sep`; null when there is no such part or
    it is empty (`split_nth("a||c", "|", 2)`)."""
    if s is None:
        return None
    parts = s.split(sep)
    return (parts[n - 1] or None) if 0 < n <= len(parts) else None


def split_last(s: str, sep: str) -> str | None:
    """The part of `s` after the last `sep` (all of `s` when it has none): `split_last("A-B-C",
    "-")` is `"C"`. Null for a missing `s` or an empty part."""
    if s is None or not sep:
        return None
    return s.rsplit(sep, 1)[-1] or None


def is_digits(s: str) -> bool | None:
    """Whether `s` is made of the digits 0-9 only (and is not empty): `is_digits("01234567890")`.
    Null for a missing `s`."""
    if not s:
        return None
    return s.isascii() and s.isdigit()


def parse_date(s: str, fmt: str) -> str:
    """The date written in `s` with format `fmt`; a date travels as text."""
    raise NotImplementedError  # the format dialect is the target's: each backend implements it


@special
def coalesce(*values: Any) -> Any:
    """The first value that is not null."""
    for value in values:
        if value is not None:
            return value
    return None


@special
def if_else(condition: Any, then: Any, otherwise: Any) -> Any:
    """`then` when `condition` is true (as in Python), otherwise `otherwise`."""
    return then if condition else otherwise


@special
def lookup(key: str, table: Mapping[str, Any], default: Any = None) -> Any:
    """The value of `table` for `key` (a lookup table, written `@name`); `default` when absent."""
    value = table.get(key, default)
    return None if value == "" else value


@special
def concat(*parts: Any) -> str:
    """The parts joined as text; a null part counts as empty, and null is the result when
    nothing is left."""
    return "".join("" if p is None else str(p) for p in parts) or None  # type: ignore[return-value]


@special
def count(items: list[Any]) -> int:
    """The number of elements of a list; `count(x for x in list if condition)` counts those that
    satisfy the condition."""
    return 0 if items is None else _py.len(items)


@special
def any(items: list[Any]) -> bool:  # noqa: A001
    """True when at least one element of a comprehension is true: `any(condition for x in list if
    filter)` (the `for` is the only way to write it). A missing value is false, as in any condition;
    an empty set is false. Another aggregate may stand in the condition."""
    return _py.any(bool(v) for v in items or [])


@special
def all(items: list[Any]) -> bool:  # noqa: A001
    """True when every element of a comprehension is true: `all(condition for x in list if
    filter)`. A missing value is false, so an element that has none makes it false; an empty set is
    true. Another aggregate may stand in the condition."""
    return _py.all(bool(v) for v in items or [])


@special
def max(items: list[Any], field: str = "") -> Any:  # noqa: A001
    """The greatest `field` of the elements of a list (the elements themselves without a field).
    `max(expression for x in list if condition)` takes it over a value computed for each element,
    leaving out those that fail the condition. Missing values are skipped; nothing left is null."""
    values = _column(items, field)
    return _py.max(values) if values else None


@special
def min(items: list[Any], field: str = "") -> Any:  # noqa: A001
    """The smallest `field` of the elements of a list (see `max` for the form with a condition)."""
    values = _column(items, field)
    return _py.min(values) if values else None


@special
def sum(items: list[Any], field: str = "") -> Any:  # noqa: A001
    """The sum of the `field` of the elements of a list (see `max` for the form with a condition);
    missing values are skipped, nothing left is 0."""
    return _total(_column(items, field))


@special
def avg(items: list[Any], field: str = "") -> Any:
    """The average of the `field` of the elements of a list (see `max` for the form with a
    condition); nothing left is null."""
    values = _column(items, field)
    return float(Decimal(repr(_total(values))) / _py.len(values)) if values else None


@special
def join(items: list[Any], sep: str = "") -> str | None:
    """The texts of a list written one after the other with `sep` between them;
    `join((expression for x in list if condition), sep)` (the comprehension in parentheses) joins a value computed for each element
    that satisfies the condition. Missing and empty values are left out; nothing left is null."""
    parts = [to_string(v) for v in _column(items, "")]
    return (sep or "").join(p for p in parts if p) or None


# -- text ---------------------------------------------------------------------------
# A null text gives a null result, as in SQL.


def replace(source: str, search: str, replacement: str = "") -> str:
    """`source` with every `search` replaced by `replacement` (removed when there is none)."""
    if source is None:
        return None  # type: ignore[return-value]
    if not search:
        return source
    return source.replace(search, replacement or "") or None  # type: ignore[return-value]


def regexp_replace(source: str, pattern: str, replacement: str = "") -> str:
    """`source` with every match of `pattern` replaced by `replacement` (`\\1` is the first group); the
    matches are removed when there is no replacement. The pattern is in the dialect of the backend
    that runs the mapping (Python's `re`, Oracle's `REGEXP_*`): keeping to what the target accepts is
    the project's responsibility, and the one place where backends are not interchangeable."""
    if source is None:
        return None  # type: ignore[return-value]
    return re.sub(pattern, replacement or "", source) or None  # type: ignore[return-value]


def regexp_group(source: str, pattern: str, nth: int) -> str | None:
    """The `nth` group of the first match of `pattern` in `source` (0 is the whole match);
    null when there is no match or no such group. The pattern is in the dialect of the backend that
    runs the mapping, as for `regexp_replace`."""
    if source is None:
        return None
    match = re.search(pattern, source)
    if match is None or nth > match.re.groups:
        return None
    return match.group(nth) or None


def remove_prefix(source: str, prefix: str) -> str:
    """`source` without `prefix` at its start; unchanged when it does not start with it."""
    if source is None:
        return None  # type: ignore[return-value]
    result = source[len(prefix) :] if prefix and source.startswith(prefix) else source
    return result or None  # type: ignore[return-value]


def upper(s: str) -> str | None:
    """`s` in capitals. Letters with a special upper-case form (such as the German ß) follow the
    database's language settings on PL/SQL and Python's rules on Python."""
    if s is None:
        return None
    return s.upper() or None


def lower(s: str) -> str | None:
    """`s` in lower case (see `upper` for letters with a special form)."""
    if s is None:
        return None
    return s.lower() or None


def trim(s: str) -> str | None:
    """`s` without the spaces at its start and end (only spaces, not tabs or line breaks);
    null when nothing is left."""
    if s is None:
        return None
    return s.strip(" ") or None


def length(s: str) -> int | None:
    """The number of characters of `s`; null for a missing or empty text."""
    if not s:
        return None
    return _py.len(s)


def substring(s: str, start: int, length: int | None = None) -> str | None:
    """The characters of `s` from position `start` (the first character is 1; a start below 1 is
    1), `length` of them, or all the rest without `length`. Null when `length` is below 1 or
    nothing is left: `substring("abcdef", 2, 3)` is `"bcd"`."""
    if s is None or start is None:
        return None
    if length is not None and length < 1:
        return None
    begin = _py.max(start, 1) - 1
    end = None if length is None else begin + length
    return s[begin:end] or None


def left(s: str, n: int) -> str | None:
    """The first `n` characters of `s` (all of it when it is shorter); null when `n` is below 1."""
    if s is None or n is None or n < 1:
        return None
    return s[:n] or None


def right(s: str, n: int) -> str | None:
    """The last `n` characters of `s` (all of it when it is shorter); null when `n` is below 1."""
    if s is None or n is None or n < 1:
        return None
    return s[_py.max(_py.len(s) - n, 0) :] or None


def pad_left(s: str, width: int, fill: str = " ") -> str | None:
    """`s` with `fill` repeated at its start until it is `width` characters long (unchanged when it
    already is; the zero padding of a code is `pad_left(@.n, 5, "0")`). `fill` is one character."""
    if s is None or width is None or not fill:
        return None
    return (fill * width)[: _py.max(width - _py.len(s), 0)] + s


def pad_right(s: str, width: int, fill: str = " ") -> str | None:
    """`s` with `fill` repeated at its end until it is `width` characters long (unchanged when it
    already is). `fill` is one character."""
    if s is None or width is None or not fill:
        return None
    return s + (fill * width)[: _py.max(width - _py.len(s), 0)]


def contains(s: str, part: str) -> bool:
    """True when `part` occurs in `s`; false when either is missing or empty."""
    return bool(s) and bool(part) and part in s


def starts_with(s: str, prefix: str) -> bool:
    """True when `s` starts with `prefix`; false when either is missing or empty."""
    return bool(s) and bool(prefix) and s.startswith(prefix)


def ends_with(s: str, suffix: str) -> bool:
    """True when `s` ends with `suffix`; false when either is missing or empty."""
    return bool(s) and bool(suffix) and s.endswith(suffix)


# -- numbers and conversions ------------------------------------------------------------


def format_decimal(x: float, n: int) -> str:
    """`x` rounded (half away from zero) to `n` decimals and written with all of them,
    trailing zeros included: `format_decimal(2.5, 2)` is `"2.50"`."""
    if x is None:
        return None  # type: ignore[return-value]
    if n < 0:
        raise ValueError("the number of decimals cannot be negative")
    text = format(_decimal(x).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP), "f")
    return text[1:] if text.startswith("-") and not text.strip("-0.") else text


@special
def abs(x: float) -> float:  # noqa: A001
    """The absolute value of `x`; null for a missing one. A whole number stays one."""
    return None if x is None else _py.abs(x)  # type: ignore[return-value]


def floor(x: float) -> int:
    """The greatest whole number not above `x`: `floor(-2.5)` is `-3`."""
    return None if x is None else float(math.floor(x))  # type: ignore[return-value]


def ceil(x: float) -> int:
    """The smallest whole number not below `x`: `ceil(-2.5)` is `-2`."""
    return None if x is None else float(math.ceil(x))  # type: ignore[return-value]


def _decimal(x: Any) -> Decimal:
    try:
        return Decimal(str(x).strip())
    except InvalidOperation:
        raise ValueError(f"not a number: {x!r}") from None


def is_empty(value: Any, zero_is_empty: bool = False) -> bool:
    """True when `value` is missing, null or an empty text; with `zero_is_empty`, a number that is
    0 counts as empty too (by default 0 is a valid number). A boolean, a list and an object are not
    empty: `count` tells whether a list has elements."""
    if value is None or value == "":
        return True
    return (
        bool(zero_is_empty)
        and isinstance(value, int | float)
        and not isinstance(value, bool)
        and value == 0
    )


def to_number(x: Any) -> float | None:
    """`x` as a number. A number stays as it is. A text must be a plain decimal number:

    - an optional sign, digits, and an optional fraction written with a dot (`-12`, `3.75`, `.5`);
    - spaces around it are ignored; an empty text gives null;
    - NOT accepted (an error, and the rule fails): an exponent (`1e3`), thousands separators
      (`1,200`), a decimal comma (`3,5`), a currency or percent sign, any other text;
    - at most 20 digits before the dot and 18 after it (38 in all, the limit of the Oracle format the PL/SQL
      backend reads with; a longer number is an error on every backend);
    - a boolean is an error, and a missing value gives null.
    The text is read the same way whatever the database session's number settings are."""
    if x is None or isinstance(x, bool):
        if isinstance(x, bool):
            raise ValueError("a boolean is not a number")
        return None
    if isinstance(x, int | float):
        return x
    text = str(x).strip()
    if not text:
        return None
    if not re.fullmatch(r"[+-]?(\d{1,20}(\.\d{0,18})?|\.\d{1,18})", text):
        raise ValueError(f"not a number: {x!r}")  # a plain decimal: no exponent, no separators
    value = Decimal(text)
    return int(value) if re.fullmatch(r"[+-]?\d+", text) else float(value)


def to_string(x: Any) -> str | None:
    """`x` as text, whatever its type (the result is the same on every backend):

    - a number is written in plain decimal, never with an exponent; a whole number without
      decimals (`5`, not `5.0`), and a fraction with its leading zero (`0.5`);
    - a boolean is `true` or `false`; a list or an object is compact JSON (`[1,"a"]`);
    - a text stays as it is, and a missing value gives null."""
    if x is None or isinstance(x, str):
        return x or None
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        value = Decimal(str(x))
        return str(int(value)) if value == value.to_integral_value() else format(value, "f")
    return json.dumps(x, separators=(",", ":"), ensure_ascii=False)


# -- timestamps -----------------------------------------------------------------------------

_TIMESTAMP = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"
    r"(?:[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d{1,9}))?)?\s*(Z|z|[+-]\d{2}(?::?\d{2})?)?)?"
)


def _timestamp(text: str) -> tuple[Any, str, int]:
    """(the local date and time to the second, the fraction as written, the offset in minutes)
    of an ISO-8601 / RFC3339 timestamp; no time is midnight and no offset is UTC."""
    from datetime import datetime

    match = _TIMESTAMP.fullmatch(text.strip())
    if match is None:
        raise ValueError(f"not an ISO-8601 / RFC3339 timestamp: {text!r}")
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    local = datetime(
        int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0)
    )
    offset = 0
    if zone and zone not in ("Z", "z"):
        digits = zone[1:].replace(":", "")
        offset = (int(digits[:2]) * 60 + int(digits[2:] or 0)) * (-1 if zone[0] == "-" else 1)
    return local, fraction or "", offset


def _fraction_shown(fraction: str, digits: int | None) -> str:
    """The fraction of a second as written, or with exactly `digits` digits (0 for none)."""
    if digits is None:
        return fraction
    return (fraction + "0" * 9)[: int(digits)] if digits > 0 else ""


def to_utc(source: str, fraction_digits: int | None = None) -> str:
    """An ISO-8601 or RFC3339 timestamp as ISO-8601 in UTC, `2026-10-03T07:30:00Z`; the fraction
    of a second is kept as written, or written with `fraction_digits` digits (`3` for
    milliseconds: `2026-10-03T07:30:00.000Z`; `0` for none)."""
    if source is None:
        return None  # type: ignore[return-value]
    from datetime import timedelta

    local, fraction, offset = _timestamp(source)
    fraction = _fraction_shown(fraction, fraction_digits)
    utc = local - timedelta(minutes=offset)
    return utc.strftime("%Y-%m-%dT%H:%M:%S") + (f".{fraction}" if fraction else "") + "Z"


def rfc3339_normalize(source: str, fraction_digits: int | None = None) -> str:
    """An ISO-8601 or RFC3339 timestamp written as RFC3339, the JSON date-time: `T` between date
    and time, seconds always, the offset as `Z` or `+HH:MM` (UTC when it has none). The instant and
    its offset are kept; `to_utc` also moves it to UTC. The fraction of a second is kept as
    written, or written with `fraction_digits` digits (`3` for milliseconds, `0` for none)."""
    if source is None:
        return None  # type: ignore[return-value]
    local, fraction, offset = _timestamp(source)
    fraction = _fraction_shown(fraction, fraction_digits)
    zone = (
        "Z"
        if offset == 0
        else f"{'-' if offset < 0 else '+'}{_py.abs(offset) // 60:02d}:{_py.abs(offset) % 60:02d}"
    )
    return local.strftime("%Y-%m-%dT%H:%M:%S") + (f".{fraction}" if fraction else "") + zone


_DATE_TOKENS = re.compile(r"YYYY|MM|DD|HH24|MI|SS", re.IGNORECASE)


def format_date(s: str, fmt: str) -> str | None:
    """A date, or an ISO-8601 date and time, written with the format `fmt` (YYYY, MM, DD, HH24, MI,
    SS, any case, with separators between them; the same tokens as `parse_date`):
    `format_date("2026-10-03", "DD/MM/YYYY")` is `"03/10/2026"`. The date and time are taken as
    written, without moving them to another time zone; no time is midnight. Any other letter in
    `fmt` is an error."""
    if s is None or not fmt:
        return None
    if re.fullmatch(r"(?:YYYY|MM|DD|HH24|MI|SS|[^A-Za-z0-9])+", fmt, re.IGNORECASE) is None:
        raise ValueError(f"not a date format: {fmt!r}")
    local, _fraction, _offset = _timestamp(s)
    parts = {
        "YYYY": f"{local.year:04d}",
        "MM": f"{local.month:02d}",
        "DD": f"{local.day:02d}",
        "HH24": f"{local.hour:02d}",
        "MI": f"{local.minute:02d}",
        "SS": f"{local.second:02d}",
    }
    return _DATE_TOKENS.sub(lambda m: parts[m.group(0).upper()], fmt)


_PARSE_TOKENS = re.compile(r"YYYY|HH24|HH12|MON|MM|DD|MI|SS|AM", re.IGNORECASE)
_MONTH_NAMES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def parse_timestamp(s: str, fmt: str) -> str | None:
    """A date and time written as `fmt` (YYYY, MM, MON for the English month abbreviation, DD,
    HH24, HH12 with AM, MI, SS, any case, with separators between them) as ISO-8601 without a time
    zone: `parse_timestamp("Mar 25, 2026, 4:08:12 PM", "MON DD, YYYY, HH12:MI:SS AM")` is
    `"2026-03-25T16:08:12"`. The format needs a year, a month and a day; a time without hours is
    midnight. Any other letter in `fmt` is an error, and so is a text that does not fit it."""
    if s is None or not fmt:
        return None
    if (
        re.fullmatch(r"(?:YYYY|HH24|HH12|MON|MM|DD|MI|SS|AM|[^A-Za-z0-9])+", fmt, re.IGNORECASE)
        is None
    ):
        raise ValueError(f"not a date format: {fmt!r}")
    names = [m.group(0).upper() for m in _PARSE_TOKENS.finditer(fmt)]
    if "YYYY" not in names or "DD" not in names or not ({"MM", "MON"} & set(names)):
        raise ValueError(f"a date format needs a year, a month and a day: {fmt!r}")
    pattern = ""
    position = 0
    for m in _PARSE_TOKENS.finditer(fmt):
        literal = fmt[position : m.start()]
        pattern += "".join(r"\s+" if c.isspace() else re.escape(c) for c in literal)
        token = m.group(0).upper()
        pattern += {"YYYY": r"(\d{4})", "MON": r"([A-Za-z]{3})", "AM": r"([AaPp][Mm])"}.get(
            token, r"(\d{1,2})"
        )
        position = m.end()
    pattern += "".join(r"\s+" if c.isspace() else re.escape(c) for c in fmt[position:])
    found = re.fullmatch(r"\s*" + pattern + r"\s*", s)
    if found is None:
        raise ValueError(f"{s!r} does not fit the format {fmt!r}")
    values = dict(zip(names, found.groups(), strict=True))
    from datetime import datetime

    month = (
        int(values["MM"])
        if "MM" in values
        else _MONTH_NAMES.index(values["MON"].upper()) + 1
        if values["MON"].upper() in _MONTH_NAMES
        else 0
    )
    hour = int(values.get("HH24", values.get("HH12", 0)))
    if "HH12" in values:
        hour = hour % 12 + (12 if values.get("AM", "AM").upper() == "PM" else 0)
    return datetime(
        int(values["YYYY"]),
        month,
        int(values["DD"]),
        hour,
        int(values.get("MI", 0)),
        int(values.get("SS", 0)),
    ).strftime("%Y-%m-%dT%H:%M:%S")


def days_between(start: str, end: str) -> int | None:
    """The whole calendar days from the date of `start` to the date of `end` (ISO-8601 dates or
    timestamps, the time is ignored): `days_between("2026-03-20", "2026-03-25")` is `5`, and it is
    negative when `end` is earlier. Null if either is missing."""
    if start is None or end is None:
        return None
    return (_timestamp(end)[0].date() - _timestamp(start)[0].date()).days


def add_days(date_text: str, days: int) -> str | None:
    """The date `days` after the date of `date_text` (an ISO-8601 date or timestamp, the time is
    ignored), as `YYYY-MM-DD`; `days` may be negative. Null if either is missing."""
    if date_text is None or days is None:
        return None
    from datetime import timedelta

    return (_timestamp(date_text)[0].date() + timedelta(days=int(days))).isoformat()
