"""Validation of the input and the output of a mapping (docs/IMPLEMENTATION_PLAN.md, §Validation
of the input and the output).

A mapping may declare, on each side (the document before any rule runs, the output after the last):
- the JSON Schema check: the document is validated against the mapping's schema (best effort, the
  host may do it upstream or downstream instead);
- extra checks: a rule function `(root) -> bool` that must hold, with a `code`, a `message` and an
  `action`, `reject` (the mapping gives no output) or `warn` (reported only).

In a `.map.py` this is the reserved directive `__validation__ = '<json>'`, a string so that the
language subset keeps its ban on module-level assignments; the transpiler writes it from the
functional file's `validations:` section. The check functions are ordinary rule functions of the
module that nothing calls: the entry points do, so they are compiled and linked like any other.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

DIRECTIVE = "__validation__"
SIDES = ("input", "output")
ACTIONS = ("reject", "warn")
# codes of the report for a failed JSON Schema check
SCHEMA_CODE = {"input": "SCHEMA_INPUT", "output": "SCHEMA_OUTPUT"}


class ValidationError(Exception):
    """The `__validation__` directive is malformed."""


@dataclass(frozen=True)
class Check:
    fn: str  # the rule function that holds the condition
    code: str
    message: str
    action: Literal["reject", "warn"] = "reject"


@dataclass
class Side:
    schema: bool = False
    checks: list[Check] = field(default_factory=list)


@dataclass
class Validation:
    input: Side = field(default_factory=Side)
    output: Side = field(default_factory=Side)
    # the JSON Schema text of a side whose check is on (canonical, so its hash is stable)
    schemas: dict[str, str] = field(default_factory=dict)

    def side(self, name: str) -> Side:
        return self.input if name == "input" else self.output

    @property
    def active(self) -> bool:
        return any(s.schema or s.checks for s in (self.input, self.output))

    def to_json(self) -> dict[str, Any]:
        return {
            side: {
                "schema": self.side(side).schema,
                "checks": [vars(c) for c in self.side(side).checks],
            }
            for side in SIDES
        }


def canonical_schema(raw: str) -> str:
    """The schema text as embedded: sorted keys, no spaces (the same schema gives the same hash)."""
    return json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def schema_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def parse(text: str) -> Validation:
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise ValidationError(f"{DIRECTIVE} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) - set(SIDES):
        raise ValidationError(f"{DIRECTIVE} must be an object with 'input' and/or 'output'")
    result = Validation()
    codes: set[str] = set()
    for name in SIDES:
        side = result.side(name)
        body = raw.get(name) or {}
        if not isinstance(body, dict) or set(body) - {"schema", "checks"}:
            raise ValidationError(f"{DIRECTIVE}.{name} may only hold 'schema' and 'checks'")
        side.schema = bool(body.get("schema", False))
        for i, item in enumerate(body.get("checks") or []):
            where = f"{DIRECTIVE}.{name}.checks[{i}]"
            if not isinstance(item, dict) or set(item) - {"fn", "code", "message", "action"}:
                raise ValidationError(f"{where}: needs fn, code, message and action")
            action = item.get("action", "reject")
            if action not in ACTIONS:
                raise ValidationError(f"{where}: action must be 'reject' or 'warn'")
            code = item.get("code")
            if not isinstance(code, str) or not code or not isinstance(item.get("fn"), str):
                raise ValidationError(f"{where}: needs a code and the function that checks it")
            if code in codes or code in SCHEMA_CODE.values():
                raise ValidationError(f"{where}: the code {code!r} is used twice")
            codes.add(code)
            side.checks.append(Check(item["fn"], code, str(item.get("message", code)), action))
    return result


def extract(tree: ast.Module) -> Validation | None:
    """The mapping's validation, taking the directive out of `tree` (None when it has none)."""
    for i, stmt in enumerate(tree.body):
        if (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == DIRECTIVE
        ):
            if not (isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)):
                raise ValidationError(f"{DIRECTIVE} must be a string holding JSON")
            validation = parse(stmt.value.value)
            del tree.body[i]
            defined = {s.name: s for s in tree.body if isinstance(s, ast.FunctionDef)}
            for name in SIDES:
                for check in validation.side(name).checks:
                    fn = defined.get(check.fn)
                    if fn is None:
                        raise ValidationError(f"check {check.code!r}: no function {check.fn!r}")
                    if len(fn.args.args) != 1:
                        raise ValidationError(
                            f"check {check.code!r}: {check.fn!r} must take the document only"
                        )
            return validation
    return None
