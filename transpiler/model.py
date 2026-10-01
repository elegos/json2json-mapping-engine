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
    # fingerprints of the functions the rule used when it was validated (name -> hash)
    functions: dict[str, str] = dc_field(default_factory=dict)


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
    # `<list>[<condition>]`: the object is built from the first element that satisfies it
    # (transpiler/selector.py); the rules inside read that element as `@`
    source: str | None = None
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
    # internal (never written): the lowered form of an object with a selecting Source,
    # whose result is the first element instead of a list
    first: bool = False
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
class PathsSection:
    """The file's `paths:` section: what `$` stands for and the named path aliases.
    Every path in it is written from the real document root."""

    # `$` means this path instead of the document root (e.g. `$.transmissions.list[0]`)
    root: str | None = None
    # `@name` stands for this path (e.g. `metadata: $.transmissions.metadata`)
    aliases: dict[str, str] = dc_field(default_factory=dict)


@dataclass
class FunctionalFile:
    name: str
    id: str
    rules: list[Rule]
    path: Path | None = None
    paths: PathsSection = dc_field(default_factory=PathsSection)


# `@root` always reaches the real document root; `@index` is the loop position
RESERVED_ALIASES = ("root", "index")
_ALIAS_PATH = re.compile(r"^\$(\.[A-Za-z_]\w*(\[\d+\])*)+$")


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
_OBJECT_KEYS = _COMMON | {"output", "guard", "source", "rules"}
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
    _check_keys(f"{where}.validation", v_raw, {"validated", "needs_review", "notes", "functions"})
    fns = v_raw.get("functions", {})
    if not isinstance(fns, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in fns.items()
    ):
        raise _err(where, "validation.functions must map function names to hash strings")
    validation = Validation(
        validated=bool(v_raw.get("validated", False)),
        needs_review=bool(v_raw.get("needs_review", False)),
        notes=v_raw.get("notes"),
        functions=dict(fns),
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
        source = _get_str(where, raw, "source")
        if source is not None:
            from transpiler.selector import split_selector

            if split_selector(source) is None:
                raise _err(
                    where,
                    "the source of an object selects one element: $.list[condition] "
                    f"— got {source!r}",
                )
            if raw.get("guard"):
                raise _err(where, "an object has a guard or a source, not both")
        return ObjectRule(
            id=_load_rule_id(where, raw),
            output=_get_str(where, raw, "output", required=True) or "",
            guard=_get_str(where, raw, "guard"),
            description=_get_str(where, raw, "description"),
            rules=_load_children(where, raw),
            source=source,
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
    _check_keys(where, raw, {"name", "id", "rules", "paths"})
    file_id = raw.get("id", default_id)
    if not isinstance(file_id, str) or not _IDENT.match(file_id):
        raise _err(where, f"invalid file id {file_id!r}")
    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise _err(where, "'rules' must be a non-empty list")
    rules = [_load_rule(f"rules[{i}]", r) for i, r in enumerate(rules_raw)]
    qualify_paths(rules)
    paths = _load_paths(where, raw.get("paths"), rules)
    return FunctionalFile(
        name=str(raw.get("name", file_id)), id=file_id, rules=rules, path=path, paths=paths
    )


def _names_of(rules: list[Rule]) -> tuple[set[str], set[str]]:
    """(lookup labels, loop labels) of a rule tree."""
    lookups: set[str] = set()
    loops: set[str] = set()
    for rule in rules:
        if isinstance(rule, LookupRule):
            lookups.add(rule.label)
        elif isinstance(rule, ObjectRule | LoopRule):
            if isinstance(rule, LoopRule) and rule.label:
                loops.add(rule.label)
            inner = _names_of(rule.rules)
            lookups |= inner[0]
            loops |= inner[1]
    return lookups, loops


def _load_paths(where: str, raw: Any, rules: list[Rule]) -> PathsSection:
    if raw is None:
        return PathsSection()
    if not isinstance(raw, dict):
        raise _err(where, "'paths' must be a mapping")
    _check_keys(f"{where}.paths", raw, {"root", "aliases"})
    root = raw.get("root")
    if root is not None and (not isinstance(root, str) or not _ALIAS_PATH.match(root)):
        raise _err(
            where, f"paths.root must be a path from the document root like $.a.b[0] — got {root!r}"
        )
    aliases_raw = raw.get("aliases") or {}
    if not isinstance(aliases_raw, dict):
        raise _err(where, "paths.aliases must be a mapping of name: path")
    lookups, loops = _names_of(rules)
    for name, target in aliases_raw.items():
        if not isinstance(name, str) or not _IDENT.match(name):
            raise _err(where, f"paths.aliases: {name!r} is not a valid alias name")
        if name in RESERVED_ALIASES:
            raise _err(where, f"paths.aliases: '{name}' is reserved (@{name})")
        if name in lookups:
            raise _err(where, f"paths.aliases: '{name}' is also the name of a lookup table")
        if name in loops:
            raise _err(where, f"paths.aliases: '{name}' is also the label of a loop")
        if not isinstance(target, str) or not _ALIAS_PATH.match(target):
            raise _err(
                where,
                f"paths.aliases.{name} must be a path from the document root like $.a.b — "
                f"got {target!r}",
            )
    return PathsSection(root=root, aliases=dict(aliases_raw))


# -- path style --------------------------------------------------------------


def qualify_source(path: str, in_loop: bool) -> str:
    """A Source without `$` / `@` is relative to the current context: the document root
    outside a loop (`id` = `$.id`), the loop's element inside one (`sku` = `@.sku`).
    `$.name` always means the root, so both spellings are accepted everywhere."""
    text = path.strip()
    if not text or text[0] in "$@":
        return text
    return f"{'@' if in_loop else '$'}.{text}"


def qualify_output(output: str, nested: bool) -> str:
    """A container's `output` without `$` / `@` is relative to its parent: the output
    root at the top level (`Lines[*]` = `$.Lines[*]`), the parent container otherwise."""
    text = output.strip()
    if not text or text[0] in "$@":
        return text
    return f"{'@' if nested else '$'}.{text}"


def qualify_paths(rules: list[Rule], in_loop: bool = False, nested: bool = False) -> None:
    """Spell every Source and container Target in full (`$.` / `@.`), in place, so that
    the rest of the pipeline sees one form. The style the user writes and sees is the
    short one; this is where it is understood."""
    for rule in rules:
        if isinstance(rule, FieldRule):
            if rule.source_path:
                rule.source_path = qualify_source(rule.source_path, in_loop)
        elif isinstance(rule, ObjectRule):
            rule.output = qualify_output(rule.output, nested)
            if rule.source:
                from transpiler.selector import qualify_selector

                rule.source = qualify_selector(rule.source, in_loop)
            # a selecting object reads one element of a list: inside it `@` is that element
            qualify_paths(rule.rules, in_loop or bool(rule.source), True)
        elif isinstance(rule, LoopRule):
            rule.source = qualify_source(rule.source, in_loop)
            rule.output = qualify_output(rule.output, nested)
            qualify_paths(rule.rules, True, True)


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
        paths=PathsSection(**data.get("paths", {})),
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
