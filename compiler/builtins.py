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
from collections.abc import Mapping
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any

from compiler.function_registry import special


def _quantize(x: float, digits: int, mode: str) -> float:
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-digits), rounding=mode))


def _column(items: list[Any], field: str) -> list[Any]:
    return [i[field] if field else i for i in items]


def round(x: float, digits: int) -> float:  # noqa: A001
    """`x` rounded to `digits` decimals (half away from zero)."""
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
