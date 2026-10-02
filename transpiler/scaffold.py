"""Rules from an output schema: one empty rule for every property the mapping does not cover.

Loading an output schema, the tool offers to lay out the mapping from it: a field rule per scalar
property, an object rule per object, a loop rule per array of objects, nested as the schema is,
with Source and Expression empty (`is_unfinished`: ignored by the build until the user defines
them, an error if the schema requires them). A mapping that already has rules keeps them: only
what is missing is added, at the end of its container, and nothing is changed or deleted."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from transpiler.check import SchemaView
from transpiler.edit import _scope_prefix, basename
from transpiler.model import (
    _IDENT,
    FieldRule,
    FunctionalFile,
    LoopRule,
    ObjectRule,
    Rule,
)

Schema = dict[str, Any]

_SCALAR = {"string": "str", "integer": "int", "number": "number", "boolean": "bool"}
_FORMATS = {"date": "date", "date-time": "datetime"}


@dataclass
class Scaffold:
    file: FunctionalFile
    added: int = 0
    # what the schema describes but a rule cannot be made for, with the reason
    skipped: list[str] = field(default_factory=list)


def _properties(view: SchemaView, node: Schema) -> dict[str, Schema]:
    found: dict[str, Schema] = {}
    for variant in view.variants(node):
        props = variant.get("properties")
        if isinstance(props, dict):
            for name, sub in props.items():
                if isinstance(sub, dict):
                    found.setdefault(str(name), view.deref(sub))
    return found


def _field_type(view: SchemaView, node: Schema) -> str | None:
    types = view.types(node)
    scalar = [t for t in ("string", "integer", "number", "boolean") if t in types]
    if not scalar:
        return None
    if scalar[0] == "string":
        return _FORMATS.get(str(node.get("format")), "str")
    return _SCALAR[scalar[0]]


def _existing(children: list[Rule], name: str) -> Rule | None:
    for child in children:
        if isinstance(child, FieldRule) and child.field == name:
            return child
        if isinstance(child, ObjectRule | LoopRule) and basename(child.output) == name:
            return child
    return None


def _fill(
    view: SchemaView, node: Schema, children: list[Rule], top_level: bool, where: str, out: Scaffold
) -> None:
    required = view.required(node)
    prefix = _scope_prefix(top_level)
    for name, sub in _properties(view, node).items():
        label = f"{where}{name}"
        have = _existing(children, name)
        types = view.types(sub)
        if "array" in types:
            items = view.items(sub)
            item = view.deref(items) if isinstance(items, dict) else {}
            if "object" not in view.types(item) or not _properties(view, item):
                if have is None:
                    out.skipped.append(f"{label}: an array that is not of objects")
                continue
            if have is None:
                have = LoopRule(id=None, source="", output=f"{prefix}{name}[*]")
                children.append(have)
                out.added += 1
            if isinstance(have, LoopRule):
                _fill(view, item, have.rules, False, f"{label}[*].", out)
        elif "object" in types:
            if not _properties(view, sub):
                if have is None:
                    out.skipped.append(f"{label}: an object with no properties listed")
                continue
            if have is None:
                have = ObjectRule(id=None, output=f"{prefix}{name}")
                children.append(have)
                out.added += 1
            if isinstance(have, ObjectRule):
                _fill(view, sub, have.rules, False, f"{label}.", out)
        elif have is None:
            kind = _field_type(view, sub)
            if kind is None:
                out.skipped.append(f"{label}: no type a field can have")
            elif not _IDENT.match(name):
                out.skipped.append(f"{label}: not a valid field name")
            else:
                description = sub.get("description")
                children.append(
                    FieldRule(
                        id=None,
                        field=name,
                        type=kind,
                        required=name in required,
                        description=description if isinstance(description, str) else None,
                    )
                )
                out.added += 1


def scaffold_rules(file: FunctionalFile, output_schema: Schema) -> Scaffold:
    """`file` with an empty rule added for each property of `output_schema` it does not cover."""
    result = Scaffold(copy.deepcopy(file))
    view = SchemaView(output_schema)
    _fill(view, output_schema, result.file.rules, True, "", result)
    return result
