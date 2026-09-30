"""Stage `load` — YAML Loader (docs/ARCHITECTURE.md, §Transpiler pipeline,
§Functional file schema).

Reads a `.fn.yaml` into a typed Rule Tree. Strict about structure (unknown
keys, wrong kinds, missing required keys are errors, reported with the path to
the offending rule) but knows nothing about expression syntax — that is
the `build` stage.

Metadata the transpiler never reads (`allowed`, `example`, `description`,
`version`, `source.path`) is still loaded and kept, so the desktop tool (M6)
and the decay helper (`apply_decay`) work off the same model.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, Literal

import yaml

FIELD_TYPES = ("str", "int", "number", "bool", "date", "datetime")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class FnYamlError(Exception):
    """Invalid `.fn.yaml`. The message starts with the path to the offending rule."""


@dataclass
class Validation:
    validated: bool = False
    needs_review: bool = False
    notes: str | None = None


@dataclass
class Transform:
    expression: str | None = None
    status: Literal["auto", "manual"] = "auto"
    code_override: str | None = None
    last_auto_version: str | None = None


CONFLICT_KEY = "format+multipleOf"
CONFLICT_RESOLUTIONS = ("both", "multipleOf_only", "format_only")
_ROUNDING = ("round", "truncate")


@dataclass
class Choices:
    """Per-rule decisions on the post-processing steps the transpiler appends
    after the declared transform. `None` = not decided here (project default in
    `mapper.toml` `[compiler.default_choices]`, or, for `conflicts`, unresolved)."""

    format: Literal["round", "truncate"] | None = None
    multiple_of: Literal["round", "truncate"] | None = None
    conflicts: dict[str, str] = dc_field(default_factory=dict)


@dataclass
class FieldRule:
    id: str | None
    field: str
    type: str
    required: bool = True
    format: str | None = None
    choices: Choices = dc_field(default_factory=Choices)
    allowed: dict[str, Any] | None = None
    example: Any = None
    description: str | None = None
    source_path: str | None = None
    # a constant Source (`source: {constant: 27}`): the value is not read from the input
    source_constant: Any = None
    has_constant: bool = False
    transform: Transform = dc_field(default_factory=Transform)
    validation: Validation = dc_field(default_factory=Validation)
    version: dict[str, Any] = dc_field(default_factory=dict)
    kind: Literal["field"] = "field"


@dataclass
class ObjectRule:
    id: str | None
    output: str
    guard: str | None = None
    description: str | None = None
    rules: list[Rule] = dc_field(default_factory=list)
    kind: Literal["object"] = "object"


@dataclass
class LoopRule:
    id: str | None
    source: str
    output: str
    label: str | None = None
    filter: str | None = None
    sort_key: str | None = None
    sort_reverse: bool = False
    index_start: int = 0  # start-offset for `@index`
    parallel: int | None = None  # `@parallel(degree=N)` on the loop's element function
    description: str | None = None
    rules: list[Rule] = dc_field(default_factory=list)
    kind: Literal["loop"] = "loop"


@dataclass
class LookupRule:
    id: str | None
    label: str
    entries: dict[str, Any]
    description: str | None = None
    # primitive type every value must have; None = not declared (values are not checked)
    type: str | None = None
    kind: Literal["lookup"] = "lookup"


Rule = FieldRule | ObjectRule | LoopRule | LookupRule


@dataclass
class FunctionalFile:
    name: str
    id: str
    rules: list[Rule]
    path: Path | None = None


# -- loading -----------------------------------------------------------------


def value_has_type(value: Any, type_: str) -> bool:
    """Whether a YAML / JSON scalar is a valid value of the field type `type_` (a date
    or datetime travels as a string)."""
    if type_ == "bool":
        return isinstance(value, bool)
    if type_ == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_ == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, str)


def _err(where: str, msg: str) -> FnYamlError:
    return FnYamlError(f"{where}: {msg}")


def _check_keys(where: str, raw: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise _err(where, f"unknown key(s): {', '.join(unknown)}")


def _get_str(where: str, raw: dict[str, Any], key: str, required: bool = False) -> str | None:
    value = raw.get(key)
    if value is None:
        if required:
            raise _err(where, f"missing required key '{key}'")
        return None
    if not isinstance(value, str):
        raise _err(where, f"'{key}' must be a string")
    return value


def _get_dict(where: str, raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _err(where, f"'{key}' must be a mapping")
    return value


def _load_rule_id(where: str, raw: dict[str, Any]) -> str | None:
    rid = raw.get("id")
    if rid is None:
        return None
    if not isinstance(rid, str) or not _IDENT.match(rid):
        raise _err(where, f"invalid id {rid!r} (letters, digits, '_'; must not start with a digit)")
    return rid


_COMMON = {"id", "kind", "description"}
_FIELD_KEYS = _COMMON | {
    "field",
    "type",
    "format",
    "choices",
    "required",
    "allowed",
    "example",
    "source",
    "transform",
    "validation",
    "version",
}
_OBJECT_KEYS = _COMMON | {"output", "guard", "rules"}
_LOOP_KEYS = _COMMON | {
    "label",
    "source",
    "filter",
    "sort",
    "output",
    "index_start",
    "parallel",
    "rules",
}
_LOOKUP_KEYS = _COMMON | {"label", "entries", "type"}


def _load_choices(where: str, raw: dict[str, Any]) -> Choices:
    c_raw = _get_dict(where, raw, "choices")
    _check_keys(f"{where}.choices", c_raw, {"format", "multipleOf", "conflicts"})
    for key in ("format", "multipleOf"):
        if c_raw.get(key) not in (None, *_ROUNDING):
            raise _err(
                f"{where}.choices", f"'{key}' must be 'round' or 'truncate' — got {c_raw[key]!r}"
            )
    conflicts = c_raw.get("conflicts") or {}
    if not isinstance(conflicts, dict):
        raise _err(f"{where}.choices", "'conflicts' must be a mapping")
    _check_keys(f"{where}.choices.conflicts", conflicts, {CONFLICT_KEY})
    for key, res in conflicts.items():
        if res not in CONFLICT_RESOLUTIONS:
            raise _err(
                f"{where}.choices.conflicts",
                f"'{key}' must be one of {', '.join(CONFLICT_RESOLUTIONS)} — got {res!r}",
            )
    return Choices(c_raw.get("format"), c_raw.get("multipleOf"), dict(conflicts))


def _load_field(where: str, raw: dict[str, Any]) -> FieldRule:
    _check_keys(where, raw, _FIELD_KEYS)
    name = _get_str(where, raw, "field", required=True)
    type_ = _get_str(where, raw, "type", required=True)
    assert name is not None and type_ is not None
    if not _IDENT.match(name):
        raise _err(where, f"'field' {name!r} is not a valid output field name")
    if type_ not in FIELD_TYPES:
        raise _err(where, f"'type' must be one of {', '.join(FIELD_TYPES)} — got {type_!r}")
    fmt = raw.get("format")
    if fmt is not None and not isinstance(fmt, str):
        raise _err(where, "'format' must be a string")
    choices = _load_choices(where, raw)
    required = raw.get("required", True)
    if not isinstance(required, bool):
        raise _err(where, "'required' must be true or false")

    t_raw = _get_dict(where, raw, "transform")
    _check_keys(
        f"{where}.transform", t_raw, {"expression", "status", "code_override", "last_auto_version"}
    )
    status = t_raw.get("status", "auto")
    if status not in ("auto", "manual"):
        raise _err(where, f"transform.status must be 'auto' or 'manual' — got {status!r}")
    transform = Transform(
        expression=_get_str(f"{where}.transform", t_raw, "expression"),
        status=status,
        code_override=_get_str(f"{where}.transform", t_raw, "code_override"),
        last_auto_version=_get_str(f"{where}.transform", t_raw, "last_auto_version"),
    )
    if status == "manual" and not transform.code_override:
        raise _err(where, "transform.status is 'manual' but code_override is empty")

    v_raw = _get_dict(where, raw, "validation")
    _check_keys(f"{where}.validation", v_raw, {"validated", "needs_review", "notes"})
    validation = Validation(
        validated=bool(v_raw.get("validated", False)),
        needs_review=bool(v_raw.get("needs_review", False)),
        notes=v_raw.get("notes"),
    )
    s_raw = _get_dict(where, raw, "source")
    _check_keys(f"{where}.source", s_raw, {"path", "constant"})
    if "path" in s_raw and "constant" in s_raw:
        raise _err(where, "'source' has both a path and a constant — pick one")
    has_source = "path" in s_raw or "constant" in s_raw
    if status == "auto" and not transform.expression and not has_source:
        raise _err(where, "the rule has neither a source nor an expression")
    if "constant" in s_raw and isinstance(s_raw["constant"], dict | list):
        raise _err(where, "'source.constant' must be a scalar")
    allowed = raw.get("allowed")
    if allowed is not None and not isinstance(allowed, dict):
        raise _err(where, "'allowed' must be a mapping")

    return FieldRule(
        id=_load_rule_id(where, raw),
        field=name,
        type=type_,
        required=required,
        format=fmt,
        choices=choices,
        allowed=allowed,
        example=raw.get("example"),
        description=_get_str(where, raw, "description"),
        source_path=s_raw.get("path"),
        source_constant=s_raw.get("constant"),
        has_constant="constant" in s_raw,
        transform=transform,
        validation=validation,
        version=_get_dict(where, raw, "version"),
    )


def _load_children(where: str, raw: dict[str, Any]) -> list[Rule]:
    children = raw.get("rules")
    if children is None:
        return []
    if not isinstance(children, list):
        raise _err(where, "'rules' must be a list")
    return [_load_rule(f"{where}.rules[{i}]", r) for i, r in enumerate(children)]


def _load_parallel(where: str, raw: dict[str, Any]) -> int | None:
    """`parallel: N` or `parallel: {degree: N}` — the two spellings of
    `@parallel(N)` / `@parallel(degree=N)`."""
    value = raw.get("parallel")
    if isinstance(value, dict):
        _check_keys(f"{where}.parallel", value, {"degree"})
        value = value.get("degree")
    if value is None:
        if "parallel" in raw:
            raise _err(where, "'parallel' needs a degree (`parallel: 4`)")
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise _err(where, "'parallel' degree must be an integer >= 1")
    return value


def _load_rule(where: str, raw: Any) -> Rule:
    if not isinstance(raw, dict):
        raise _err(where, "a rule must be a mapping")
    kind = raw.get("kind")
    if kind == "field":
        return _load_field(where, raw)
    if kind == "object":
        _check_keys(where, raw, _OBJECT_KEYS)
        return ObjectRule(
            id=_load_rule_id(where, raw),
            output=_get_str(where, raw, "output", required=True) or "",
            guard=_get_str(where, raw, "guard"),
            description=_get_str(where, raw, "description"),
            rules=_load_children(where, raw),
        )
    if kind == "loop":
        _check_keys(where, raw, _LOOP_KEYS)
        sort = raw.get("sort")
        sort_key, sort_reverse = None, False
        if sort is not None:
            if not isinstance(sort, dict) or "key" not in sort:
                raise _err(where, "'sort' must be a mapping with a 'key'")
            _check_keys(f"{where}.sort", sort, {"key", "reverse"})
            sort_key = _get_str(f"{where}.sort", sort, "key", required=True)
            sort_reverse = bool(sort.get("reverse", False))
        index_start = raw.get("index_start", 0)
        if not isinstance(index_start, int) or isinstance(index_start, bool):
            raise _err(where, "'index_start' must be an integer")
        label = _get_str(where, raw, "label")
        if label is not None and not _IDENT.match(label):
            raise _err(where, f"invalid label {label!r}")
        return LoopRule(
            id=_load_rule_id(where, raw),
            source=_get_str(where, raw, "source", required=True) or "",
            output=_get_str(where, raw, "output", required=True) or "",
            label=label,
            filter=_get_str(where, raw, "filter"),
            sort_key=sort_key,
            sort_reverse=sort_reverse,
            index_start=index_start,
            parallel=_load_parallel(where, raw),
            description=_get_str(where, raw, "description"),
            rules=_load_children(where, raw),
        )
    if kind == "lookup":
        _check_keys(where, raw, _LOOKUP_KEYS)
        label = _get_str(where, raw, "label", required=True) or ""
        if not _IDENT.match(label):
            raise _err(where, f"invalid label {label!r}")
        entries = raw.get("entries")
        if not isinstance(entries, dict) or not entries:
            raise _err(where, "'entries' must be a non-empty mapping")
        type_ = _get_str(where, raw, "type")
        if type_ is not None and type_ not in FIELD_TYPES:
            raise _err(where, f"'type' must be one of {', '.join(FIELD_TYPES)} — got {type_!r}")
        for key, value in entries.items():
            if type_ is not None and not value_has_type(value, type_):
                raise _err(where, f"entries: the value of {str(key)!r} is not a {type_}: {value!r}")
        return LookupRule(
            id=_load_rule_id(where, raw),
            label=label,
            entries={str(k): v for k, v in entries.items()},
            description=_get_str(where, raw, "description"),
            type=type_,
        )
    raise _err(where, f"'kind' must be one of field, object, loop, lookup — got {kind!r}")


def load_rule(where: str, raw: Any) -> Rule:
    """One rule (children included) from its raw mapping — for checking a rule on its own."""
    return _load_rule(where, raw)


def load_functional_file(path: Path) -> FunctionalFile:
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise FnYamlError(f"{path}: not valid YAML: {exc}") from exc
    return parse_functional(raw, default_id=path.name.removesuffix(".fn.yaml"), path=path)


def parse_functional(raw: Any, default_id: str, path: Path | None = None) -> FunctionalFile:
    where = str(path) if path else "<fn.yaml>"
    if not isinstance(raw, dict):
        raise _err(where, "top level must be a mapping")
    _check_keys(where, raw, {"name", "id", "rules"})
    file_id = raw.get("id", default_id)
    if not isinstance(file_id, str) or not _IDENT.match(file_id):
        raise _err(where, f"invalid file id {file_id!r}")
    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise _err(where, "'rules' must be a non-empty list")
    rules = [_load_rule(f"rules[{i}]", r) for i, r in enumerate(rules_raw)]
    return FunctionalFile(name=str(raw.get("name", file_id)), id=file_id, rules=rules, path=path)


# -- validation decay (§Rule validation) --------------------------------------


def apply_decay(old: FieldRule, new: FieldRule) -> FieldRule:
    """Validation decay: `validated` resets to false and `needs_review` to true
    whenever the *functional* side changed — `source.path` / `source.constant` or
    `transform.expression`. A `code_override` change alone never decays (the
    developer owns that code)."""
    functional_change = (
        old.source_path != new.source_path
        or old.source_constant != new.source_constant
        or old.has_constant != new.has_constant
        or old.transform.expression != new.transform.expression
    )
    if not functional_change:
        return new
    return replace(new, validation=replace(new.validation, validated=False, needs_review=True))


# -- (de)serialization of the loaded tree (stage artifact `load`) -------------


def functional_to_dict(file: FunctionalFile) -> dict[str, Any]:
    """The Rule Tree as plain data; every rule carries its `kind` tag."""
    data = asdict(file)
    data["path"] = str(file.path) if file.path else None
    return data


def functional_from_dict(data: dict[str, Any]) -> FunctionalFile:
    return FunctionalFile(
        name=data["name"],
        id=data["id"],
        rules=[_rule_from_dict(r) for r in data["rules"]],
        path=Path(data["path"]) if data.get("path") else None,
    )


def _rule_from_dict(data: dict[str, Any]) -> Rule:
    data = dict(data)
    kind = data.pop("kind")
    if kind == "field":
        data["choices"] = Choices(**data["choices"])
        data["transform"] = Transform(**data["transform"])
        data["validation"] = Validation(**data["validation"])
        return FieldRule(**data)
    if kind == "lookup":
        return LookupRule(**data)
    if kind not in ("object", "loop"):
        raise FnYamlError(f"unknown rule kind {kind!r}")
    data["rules"] = [_rule_from_dict(r) for r in data["rules"]]
    return ObjectRule(**data) if kind == "object" else LoopRule(**data)
