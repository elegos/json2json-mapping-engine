"""`.fn.yaml` writer — the inverse of `model.load_functional_file`.

The desktop tool (M6) edits the Rule Tree as JSON and never touches YAML; this
module turns the tree back into a `.fn.yaml`. Defaults are omitted, so a file
that was loaded and written unchanged keeps its meaning (YAML comments and
key order of hand-edited files are not preserved).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from transpiler.atomic import write_atomic
from transpiler.model import (
    FieldRule,
    FunctionalFile,
    LookupRule,
    LoopRule,
    ObjectRule,
    Rule,
    apply_decay,
    parse_functional,
)


def _put(out: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        out[key] = value


def _short(path: str, implied: str) -> str:
    """A container's Target without the prefix its context implies (`$.` at the top level,
    `@.` inside a container); the loader spells it out again. Sources are always written in
    full: the explicit form teaches that `$.` means the document root."""
    return path.removeprefix(implied)


def _field_to_raw(rule: FieldRule) -> dict[str, Any]:
    raw: dict[str, Any] = {"kind": "field"}
    _put(raw, "id", rule.id)
    raw["field"] = rule.field
    raw["type"] = rule.type
    if not rule.required:
        raw["required"] = False
    _put(raw, "format", rule.format)
    choices: dict[str, Any] = {}
    _put(choices, "format", rule.choices.format)
    _put(choices, "multipleOf", rule.choices.multiple_of)
    if rule.choices.conflicts:
        choices["conflicts"] = dict(rule.choices.conflicts)
    if choices:
        raw["choices"] = choices
    _put(raw, "allowed", rule.allowed)
    _put(raw, "example", rule.example)
    _put(raw, "description", rule.description)
    if rule.has_constant:
        raw["source"] = {"constant": rule.source_constant}
    elif rule.source_path is not None:
        raw["source"] = {"path": rule.source_path}
    transform: dict[str, Any] = {}
    _put(transform, "expression", rule.transform.expression)
    if rule.transform.status != "auto":
        transform["status"] = rule.transform.status
    _put(transform, "code_override", rule.transform.code_override)
    _put(transform, "last_auto_version", rule.transform.last_auto_version)
    if transform:
        raw["transform"] = transform
    validation: dict[str, Any] = {}
    if rule.validation.validated:
        validation["validated"] = True
    if rule.validation.needs_review and not rule.validation.validated:  # never both
        validation["needs_review"] = True
    _put(validation, "notes", rule.validation.notes)
    if validation:
        raw["validation"] = validation
    if rule.version:
        raw["version"] = dict(rule.version)
    return raw


def _rule_to_raw(rule: Rule, in_loop: bool = False, nested: bool = False) -> dict[str, Any]:
    if isinstance(rule, FieldRule):
        return _field_to_raw(rule)
    raw: dict[str, Any] = {"kind": rule.kind}
    _put(raw, "id", rule.id)
    if isinstance(rule, LookupRule):
        raw["label"] = rule.label
        _put(raw, "type", rule.type)
        raw["entries"] = dict(rule.entries)
        _put(raw, "description", rule.description)
        return raw
    if isinstance(rule, LoopRule):
        _put(raw, "label", rule.label)
        raw["source"] = rule.source
        _put(raw, "filter", rule.filter)
        if rule.sort_key is not None:
            sort: dict[str, Any] = {"key": rule.sort_key}
            if rule.sort_reverse:
                sort["reverse"] = True
            raw["sort"] = sort
        raw["output"] = _short(rule.output, "@." if nested else "$.")
        if rule.index_start:
            raw["index_start"] = rule.index_start
        _put(raw, "parallel", rule.parallel)
    else:
        assert isinstance(rule, ObjectRule)
        raw["output"] = _short(rule.output, "@." if nested else "$.")
        _put(raw, "source", rule.source)
        _put(raw, "guard", rule.guard)
    _put(raw, "description", rule.description)
    below_loop = in_loop or isinstance(rule, LoopRule)
    raw["rules"] = [_rule_to_raw(r, below_loop, True) for r in rule.rules]
    return raw


def rule_to_raw(rule: Rule) -> dict[str, Any]:
    return _rule_to_raw(rule)


def functional_to_raw(file: FunctionalFile) -> dict[str, Any]:
    raw: dict[str, Any] = {"name": file.name, "id": file.id}
    schemas: dict[str, Any] = {}
    _put(schemas, "input", file.schemas.input)
    _put(schemas, "output", file.schemas.output)
    if schemas:
        raw["schemas"] = schemas
    paths: dict[str, Any] = {}
    _put(paths, "root", file.paths.root)
    if file.paths.aliases:
        paths["aliases"] = dict(file.paths.aliases)
    if paths:
        raw["paths"] = paths
    raw["rules"] = [_rule_to_raw(r) for r in file.rules]
    return raw


def functional_to_yaml(file: FunctionalFile) -> str:
    return yaml.safe_dump(
        functional_to_raw(file), sort_keys=False, allow_unicode=True, default_flow_style=False
    )


def _field_rules(rules: list[Rule]) -> dict[str, FieldRule]:
    found: dict[str, FieldRule] = {}
    for rule in rules:
        if isinstance(rule, FieldRule) and rule.id:
            found[rule.id] = rule
        elif isinstance(rule, (ObjectRule, LoopRule)):
            found.update(_field_rules(rule.rules))
    return found


def _decay_rules(rules: list[Rule], old: dict[str, FieldRule], decayed: list[str]) -> list[Rule]:
    result: list[Rule] = []
    for rule in rules:
        if isinstance(rule, FieldRule) and rule.id in old:
            new = apply_decay(old[rule.id], rule)
            if new is not rule:
                decayed.append(rule.id)  # type: ignore[arg-type]
            result.append(new)
        elif isinstance(rule, (ObjectRule, LoopRule)):
            result.append(replace(rule, rules=_decay_rules(rule.rules, old, decayed)))
        else:
            result.append(rule)
    return result


def apply_decay_tree(old: FunctionalFile, new: FunctionalFile) -> tuple[FunctionalFile, list[str]]:
    """Validation decay over a whole file: each field rule of `new` is compared with
    the rule of the same id in `old` (rules without an id, or new ones, never
    decay). Returns the file and the ids that decayed."""
    decayed: list[str] = []
    rules = _decay_rules(new.rules, _field_rules(old.rules), decayed)
    return replace(new, rules=rules), decayed


def write_functional(path: Path, file: FunctionalFile) -> None:
    """Write `file` to `path`, after checking that what is written loads again."""
    text = functional_to_yaml(file)
    parse_functional(yaml.safe_load(text), default_id=file.id, path=path)
    write_atomic(path, text)
