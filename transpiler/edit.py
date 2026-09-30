"""Editing operations on the Rule Tree for the desktop tool (M6).

The grid calls these on every cell edit (through the persistent `mapper serve`
worker, so they are fast). Two conventions are enforced here, once, so that the
grid, the CLI and later importers agree:

- **Target paths.** A Target may be written `OrderId`, `$.OrderId`, `A.B`,
  `Lines.A.B`. The last segment is the rule's own name; the segments before it
  are containers. A missing container is created as an `object` rule; an existing
  one (`object`, or a `loop`, whose elements then receive the rule) is reused. The
  rule moves under the container the path names.
- **Scope prefixes.** Container outputs and sources are stored with `$.` at the top
  level and `@.` inside a loop / object (`$.Lines[*]`, `@.Tax`); a field's name is
  stored bare.

A relative path (no `$`) is relative to the rule's current parent; `$.` starts at the
document root.
"""

from __future__ import annotations

import copy
import re

from transpiler.model import (
    FieldRule,
    FnYamlError,
    FunctionalFile,
    LoopRule,
    ObjectRule,
    Rule,
)

_SEGMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\[\*\])?$")

Container = ObjectRule | LoopRule


def _scope_prefix(top_level: bool) -> str:
    return "$." if top_level else "@."


def basename(output: str) -> str:
    """`$.Lines[*]` -> `Lines`, `@.Tax` -> `Tax`."""
    return re.sub(r"^[$@]\.?", "", output).removesuffix("[*]")


def _locate(file: FunctionalFile, path: str) -> tuple[list[Rule], int]:
    """The list holding the rule at `rules[0].rules[1]` and its index there."""
    indexes = [int(i) for i in re.findall(r"\[(\d+)\]", path)]
    if not indexes:
        raise FnYamlError(f"bad rule path {path!r}")
    rules = file.rules
    for i in indexes[:-1]:
        if i >= len(rules) or not isinstance(rules[i], ObjectRule | LoopRule):
            raise FnYamlError(f"no rule at {path!r}")
        rules = rules[i].rules  # type: ignore[union-attr]
    if indexes[-1] >= len(rules):
        raise FnYamlError(f"no rule at {path!r}")
    return rules, indexes[-1]


def _split_target(text: str) -> tuple[bool, list[str]]:
    """(absolute, segments) of a Target as typed."""
    raw = text.strip()
    absolute = raw.startswith("$")
    raw = re.sub(r"^\$\.?|^@\.?", "", raw)
    segments = raw.split(".") if raw else []
    if not segments:
        raise FnYamlError("Target is empty")
    for seg in segments:
        if not _SEGMENT.match(seg):
            raise FnYamlError(f"invalid Target segment {seg!r} in {text!r}")
    return absolute, segments


def _find_container(children: list[Rule], name: str, skip: Rule) -> Container | None:
    for child in children:
        if (
            child is not skip
            and isinstance(child, ObjectRule | LoopRule)
            and basename(child.output) == name
        ):
            return child
    return None


def _name_taken(children: list[Rule], name: str, skip: Rule) -> bool:
    for child in children:
        if child is skip:
            continue
        if isinstance(child, FieldRule) and child.field == name:
            return True
        if isinstance(child, ObjectRule | LoopRule) and basename(child.output) == name:
            return True
    return False


def retarget(file: FunctionalFile, path: str, text: str) -> FunctionalFile:
    """Set the Target of the rule at `path` to `text` (see the module docstring)."""
    file = copy.deepcopy(file)
    holder, index = _locate(file, path)
    rule = holder[index]
    if not isinstance(rule, FieldRule | ObjectRule | LoopRule):
        raise FnYamlError("only field, object and loop rules have a Target")
    absolute, segments = _split_target(text)
    *containers, last = segments
    last_name, last_array = _SEGMENT.match(last).groups()  # type: ignore[union-attr]
    if isinstance(rule, FieldRule) and last_array:
        raise FnYamlError(f"a field is not an array: {last!r}")
    if isinstance(rule, ObjectRule) and last_array:
        raise FnYamlError(f"an object is not an array: {last!r}")

    root_level = holder is file.rules
    children: list[Rule] = file.rules if absolute else holder
    top_level = absolute or root_level
    for seg in containers:
        name, is_array = _SEGMENT.match(seg).groups()  # type: ignore[union-attr]
        found = _find_container(children, name, rule)
        if found is None:
            if is_array:
                raise FnYamlError(f"declare the loop {seg!r} first: it needs a source")
            found = ObjectRule(id=None, output=f"{_scope_prefix(top_level)}{name}")
            children.append(found)
        children = found.rules
        top_level = False

    if _name_taken(children, last_name, rule):
        raise FnYamlError(f"{last_name!r} is already a rule of that container")
    if isinstance(rule, FieldRule):
        rule.field = last_name
    else:
        rule.output = f"{_scope_prefix(top_level)}{last_name}" + (
            "[*]" if isinstance(rule, LoopRule) else ""
        )
    if children is not holder:
        holder.pop(index)
        children.append(rule)
    return file


def normalize_source(text: str, top_level: bool) -> str:
    """A container's `source` gets its scope prefix: `items[*]` -> `$.items[*]` at the
    top level, `@.items[*]` inside a container. Already-anchored text is kept."""
    raw = text.strip()
    if not raw or raw[0] in "$@":
        return raw
    return f"{_scope_prefix(top_level)}{raw}"


def set_source(file: FunctionalFile, path: str, text: str) -> FunctionalFile:
    """Set the Source column of the rule at `path`. A loop's `source` and a top-level
    field's `source.path` are normalised; a nested field's path is documentation and
    is kept as typed."""
    file = copy.deepcopy(file)
    holder, index = _locate(file, path)
    rule = holder[index]
    top_level = holder is file.rules
    if isinstance(rule, LoopRule):
        rule.source = normalize_source(text, top_level)
    elif isinstance(rule, FieldRule):
        value = text.strip()
        rule.source_path = (normalize_source(value, True) if top_level else value) or None
    else:
        raise FnYamlError("only field and loop rules have a Source")
    return file
