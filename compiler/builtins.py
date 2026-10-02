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
import re
from collections.abc import Mapping
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from compiler.function_registry import special


def _quantize(x: float, digits: int, mode: str) -> float:
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-digits), rounding=mode))


def _column(items: list[Any], field: str) -> list[Any]:
    return [i[field] if field else i for i in items]


def round(x: float, digits: int = 0) -> float:  # noqa: A001
    """`x` rounded to `digits` decimals (half away from zero); to a whole number without `digits`."""
    return _quantize(x, digits, ROUND_HALF_UP)


def trunc(x: float, digits: int) -> float:
    """`x` cut to `digits` decimals, without rounding."""
    return _quantize(x, digits, ROUND_DOWN)


def split_first(s: str, sep: str) -> str:
    """The text before the first `sep` (all of `s` when there is none)."""
    return s.split(sep, 1)[0]


def split_nth(s: str, sep: str, n: int) -> str | None:
    """The `n`-th part (counted from 1) of `s` split at `sep`; null when there is no such part."""
    parts = s.split(sep)
    return parts[n - 1] if 0 < n <= len(parts) else None


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
    return table.get(key, default)


@special
def concat(*parts: Any) -> str:
    """The parts joined as text; a null part counts as empty."""
    return "".join("" if p is None else str(p) for p in parts)


@special
def count(items: list[Any]) -> int:
    """The number of elements of a list."""
    return _py.len(items)


@special
def max(items: list[Any], field: str = "") -> Any:  # noqa: A001
    """The greatest `field` of the elements of a list (the elements themselves without a field)."""
    return _py.max(_column(items, field))


@special
def min(items: list[Any], field: str = "") -> Any:  # noqa: A001
    """The smallest `field` of the elements of a list."""
    return _py.min(_column(items, field))


@special
def sum(items: list[Any], field: str = "") -> Any:  # noqa: A001
    """The sum of the `field` of the elements of a list."""
    return _py.sum(_column(items, field))


@special
def avg(items: list[Any], field: str = "") -> Any:
    """The average of the `field` of the elements of a list."""
    values = _column(items, field)
    return _py.sum(values) / _py.len(values)


# -- text ---------------------------------------------------------------------------
# A null text gives a null result, as in SQL.


def replace(source: str, search: str, replacement: str = "") -> str:
    """`source` with every `search` replaced by `replacement` (removed when there is none)."""
    if source is None:
        return None  # type: ignore[return-value]
    if not search:
        return source
    return source.replace(search, replacement or "")


def regexp_replace(source: str, pattern: str, replacement: str = "") -> str:
    """`source` with every match of `pattern` replaced by `replacement` (`\\1` is the first group); the
    matches are removed when there is no replacement. The pattern is in the dialect of the backend
    that runs the mapping (Python's `re`, Oracle's `REGEXP_*`): keeping to what the target accepts is
    the project's responsibility, and the one place where backends are not interchangeable."""
    if source is None:
        return None  # type: ignore[return-value]
    return re.sub(pattern, replacement or "", source)


def regexp_group(source: str, pattern: str, nth: int) -> str | None:
    """The `nth` group of the first match of `pattern` in `source` (0 is the whole match);
    null when there is no match or no such group. The pattern is in the dialect of the backend that
    runs the mapping, as for `regexp_replace`."""
    if source is None:
        return None
    match = re.search(pattern, source)
    if match is None or nth > match.re.groups:
        return None
    return match.group(nth)


def remove_prefix(source: str, prefix: str) -> str:
    """`source` without `prefix` at its start; unchanged when it does not start with it."""
    if source is None:
        return None  # type: ignore[return-value]
    return source[len(prefix) :] if prefix and source.startswith(prefix) else source


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


def _decimal(x: Any) -> Decimal:
    try:
        return Decimal(str(x).strip())
    except InvalidOperation:
        raise ValueError(f"not a number: {x!r}") from None


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
        return x
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


def to_utc(source: str) -> str:
    """An ISO-8601 or RFC3339 timestamp as ISO-8601 in UTC, `2026-10-03T07:30:00Z`; the fraction
    of a second is kept as written."""
    if source is None:
        return None  # type: ignore[return-value]
    from datetime import timedelta

    local, fraction, offset = _timestamp(source)
    utc = local - timedelta(minutes=offset)
    return utc.strftime("%Y-%m-%dT%H:%M:%S") + (f".{fraction}" if fraction else "") + "Z"


def rfc3339_normalize(source: str) -> str:
    """An ISO-8601 or RFC3339 timestamp written as RFC3339, the JSON date-time: `T` between date
    and time, seconds always, the offset as `Z` or `+HH:MM` (UTC when it has none). The instant and
    its offset are kept; `to_utc` also moves it to UTC."""
    if source is None:
        return None  # type: ignore[return-value]
    local, fraction, offset = _timestamp(source)
    zone = (
        "Z"
        if offset == 0
        else f"{'-' if offset < 0 else '+'}{abs(offset) // 60:02d}:{abs(offset) % 60:02d}"
    )
    return local.strftime("%Y-%m-%dT%H:%M:%S") + (f".{fraction}" if fraction else "") + zone
