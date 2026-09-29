"""`allowed` constraint checks on integration-test output (docs/ARCHITECTURE.md, §allowed).

`allowed` on a `.fn.yaml` field rule holds a subset of JSON Schema validation
keywords. It is never compiled; it is only evaluated here, against the JSON a
mapping actually produced, and violations are reported as warnings (they never
fail a case).

Evaluated keywords (field values are scalars): minimum, maximum,
exclusiveMinimum, exclusiveMaximum, multipleOf, minLength, maxLength, pattern,
format (date, date-time, email, uuid), enum, const, type, and the combinators
allOf / anyOf / oneOf / not (whose sub-schemas use the same keywords). Any other
keyword — array/object ones such as minItems, or unknown ones — is never
ignored silently: `unsupported_keywords` reports it as a warning. `null`
values are skipped (nullability is the type checker's concern).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from transpiler.model import FieldRule, FunctionalFile, LoopRule, ObjectRule, Rule
from transpiler.transpile import _output_field  # pyright: ignore[reportPrivateUsage]

Path = tuple[str, ...]


def collect_constraints(ff: FunctionalFile) -> dict[Path, dict[str, Any]]:
    """Output path (field names from the root; loops/arrays are transparent) ->
    `allowed` mapping, for every field rule that declares one."""
    found: dict[Path, dict[str, Any]] = {}

    def walk(rules: list[Rule], prefix: Path) -> None:
        for r in rules:
            if isinstance(r, FieldRule):
                if r.allowed:
                    found[(*prefix, r.field)] = r.allowed
            elif isinstance(r, (ObjectRule, LoopRule)):
                walk(r.rules, (*prefix, _output_field(r.output, f"rule '{r.id}'")))

    walk(ff.rules, ())
    return found


_COMBINATORS = ("allOf", "anyOf", "oneOf", "not")
_SUPPORTED = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "enum",
        "const",
        "type",
        *_COMBINATORS,
    }
)
_FORMATS = ("date", "date-time", "email", "uuid")
_TYPES: dict[str, Any] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: (
        (isinstance(v, int) and not isinstance(v, bool))
        or (isinstance(v, float) and v.is_integer())
    ),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _multiple_of(value: float, step: Any) -> bool:
    try:
        return Decimal(str(value)) % Decimal(str(step)) == 0
    except (InvalidOperation, ZeroDivisionError):
        return True


def _format_ok(value: str, fmt: str) -> bool:
    try:
        if fmt == "date":
            date.fromisoformat(value)
        elif fmt == "date-time":
            datetime.fromisoformat(value)
        elif fmt == "uuid":
            UUID(value)
        elif fmt == "email":
            return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is not None
    except ValueError:
        return False
    return True


def _violations(value: Any, allowed: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if _is_number(value):
        for key, bad in (
            ("minimum", lambda b: value < b),
            ("maximum", lambda b: value > b),
            ("exclusiveMinimum", lambda b: value <= b),
            ("exclusiveMaximum", lambda b: value >= b),
        ):
            if key in allowed and bad(allowed[key]):
                out.append(f"{key} {allowed[key]}")
        if "multipleOf" in allowed and not _multiple_of(value, allowed["multipleOf"]):
            out.append(f"multipleOf {allowed['multipleOf']}")
    if isinstance(value, str):
        if "minLength" in allowed and len(value) < allowed["minLength"]:
            out.append(f"minLength {allowed['minLength']}")
        if "maxLength" in allowed and len(value) > allowed["maxLength"]:
            out.append(f"maxLength {allowed['maxLength']}")
        if "pattern" in allowed and not re.search(allowed["pattern"], value):
            out.append(f"pattern {allowed['pattern']}")
        fmt = allowed.get("format")
        if fmt in _FORMATS and not _format_ok(value, fmt):
            out.append(f"format {fmt}")
    if "enum" in allowed and value not in allowed["enum"]:
        out.append(f"enum {allowed['enum']}")
    if "const" in allowed and value != allowed["const"]:
        out.append(f"const {allowed['const']!r}")
    if "type" in allowed:
        types = allowed["type"] if isinstance(allowed["type"], list) else [allowed["type"]]
        if not any(t in _TYPES and _TYPES[t](value) for t in types):
            out.append(f"type {allowed['type']}")
    if "allOf" in allowed:
        for sub in allowed["allOf"]:
            out.extend(_violations(value, sub))
    if "anyOf" in allowed and all(_violations(value, sub) for sub in allowed["anyOf"]):
        out.append("anyOf: no alternative matches")
    if "oneOf" in allowed:
        n = sum(1 for sub in allowed["oneOf"] if not _violations(value, sub))
        if n != 1:
            out.append(f"oneOf: {n} alternatives match")
    if "not" in allowed and not _violations(value, allowed["not"]):
        out.append("not: value matches the forbidden schema")
    return out


def _unsupported(allowed: dict[str, Any]) -> set[str]:
    bad = set(allowed) - _SUPPORTED
    for key in _COMBINATORS:
        subs = allowed.get(key)
        for sub in [subs] if isinstance(subs, dict) else subs or []:
            if isinstance(sub, dict):
                bad |= _unsupported(sub)
    return bad


def unsupported_keywords(constraints: dict[Path, dict[str, Any]]) -> list[str]:
    """One warning per (field, keyword) that cannot be evaluated on a scalar field."""
    return [
        f"{'.'.join(path)}: keyword '{kw}' is not supported on a scalar field (not evaluated)"
        for path, allowed in constraints.items()
        for kw in sorted(_unsupported(allowed))
    ]


def check_allowed(output: Any, constraints: dict[Path, dict[str, Any]]) -> list[str]:
    """Warnings like `Orders[0].Lines[1].Qty = -3: minimum 0`."""
    warnings: list[str] = []

    def visit(node: Any, path: Path, where: str) -> None:
        if isinstance(node, list):
            for i, item in enumerate(node):
                visit(item, path, f"{where}[{i}]")
            return
        if node is None:
            return
        if path in constraints:
            for v in _violations(node, constraints[path]):
                warnings.append(f"{where} = {node!r}: {v}")
        if isinstance(node, dict):
            for key, child in node.items():
                visit(child, (*path, key), f"{where}.{key}" if where else key)

    visit(output, (), "")
    return warnings
