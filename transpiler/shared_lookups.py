"""Project-wide lookups: a table that several mappings read as `@label`, kept once in the project
as `lookups/<label>.lookup.yaml` (the file name is the label) instead of in each mapping.

    type: str                 # optional, as for a lookup of a mapping
    description: ...          # optional
    entries: {IT: EUR, ...}

A mapping sees them as `FunctionalFile.shared`, set when it is loaded; they are never written
back into the mapping's own file. The build embeds the table in each mapping that uses it, as it
does a local lookup. Changing a table sends the validated rules that read it back to review, with
a note saying what changed (`mark_changed`)."""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

import yaml

from transpiler.ids import assign_ids
from transpiler.model import (
    _IDENT,
    FieldRule,
    FnYamlError,
    FunctionalFile,
    LookupRule,
    LoopRule,
    ObjectRule,
    Rule,
    load_functional_file,
    load_rule,
)
from transpiler.serialize import write_functional

LOOKUPS_DIR = Path("lookups")
SUFFIX = ".lookup.yaml"
FUNCTIONAL = Path("mappings/functional")
_SHOWN_CHANGES = 6


def lookup_file(project: Path, label: str) -> Path:
    return project / LOOKUPS_DIR / f"{label}{SUFFIX}"


def project_of(path: Path) -> Path | None:
    """The project a mapping file belongs to, by the layout (`<project>/mappings/functional/`)."""
    folder = path.resolve().parent
    if folder.name == "functional" and folder.parent.name == "mappings":
        return folder.parent.parent
    return None


def _to_rule(label: str, raw: Any, where: str) -> LookupRule:
    if not isinstance(raw, dict):
        raise FnYamlError(f"{where}: top level must be a mapping")
    rule = load_rule(where, {**raw, "kind": "lookup", "label": label})
    assert isinstance(rule, LookupRule)
    rule.id = None
    return rule


def read_shared(project: Path, label: str) -> LookupRule:
    path = lookup_file(project, label)
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise FnYamlError(f"{path}: not valid YAML: {exc}") from exc
    return _to_rule(label, raw, str(path))


def load_shared(project: Path) -> dict[str, LookupRule]:
    """Every project-wide lookup, by label."""
    folder = project / LOOKUPS_DIR
    if not folder.is_dir():
        return {}
    found: dict[str, LookupRule] = {}
    for path in sorted(folder.glob(f"*{SUFFIX}")):
        label = path.name.removesuffix(SUFFIX)
        if not _IDENT.match(label):
            raise FnYamlError(f"{path}: {label!r} is not a valid lookup label")
        found[label] = read_shared(project, label)
    return found


def attach(file: FunctionalFile, path: Path | None) -> None:
    """Gives `file` the project-wide lookups of its project."""
    project = project_of(path) if path else None
    if project is not None:
        file.shared = load_shared(project)


def _local(rules: list[Rule]):
    for rule in rules:
        if isinstance(rule, LookupRule):
            yield rule
        elif isinstance(rule, ObjectRule | LoopRule):
            yield from _local(rule.rules)


def clashes(file: FunctionalFile) -> list[str]:
    """Labels a mapping declares itself that are also project-wide."""
    return sorted({r.label for r in _local(file.rules)} & set(file.shared))


def write_shared(project: Path, rule: LookupRule) -> None:
    raw: dict[str, Any] = {}
    if rule.type:
        raw["type"] = rule.type
    if rule.description:
        raw["description"] = rule.description
    raw["entries"] = dict(rule.entries)
    text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False)
    _to_rule(rule.label, yaml.safe_load(text), rule.label)  # what is written loads again
    path = lookup_file(project, rule.label)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# -- who uses a table -------------------------------------------------------------------------


def _reads(label: str, text: str | None) -> bool:
    return bool(text) and re.search(rf"@{re.escape(label)}(?![\w])", text or "") is not None


def _field_reads(label: str, rule: FieldRule) -> bool:
    t = rule.transform
    return any(_reads(label, s) for s in (t.expression, t.code_override, rule.source_path))


def _walk(rules: list[Rule]):
    for rule in rules:
        yield rule
        if isinstance(rule, ObjectRule | LoopRule):
            yield from _walk(rule.rules)


def mapping_files(project: Path) -> list[Path]:
    folder = project / FUNCTIONAL
    return sorted(folder.glob("*.fn.yaml")) if folder.is_dir() else []


def uses(file: FunctionalFile, label: str) -> bool:
    for rule in _walk(file.rules):
        if isinstance(rule, FieldRule) and _field_reads(label, rule):
            return True
        if isinstance(rule, ObjectRule | LoopRule) and any(
            _reads(label, s)
            for s in (
                getattr(rule, "source", None),
                getattr(rule, "guard", None),
                getattr(rule, "filter", None),
                getattr(rule, "order_by", None),
            )
        ):
            return True
    return False


def users(project: Path, label: str) -> list[str]:
    """The mappings (names) whose rules read `@label`."""
    found: list[str] = []
    for path in mapping_files(project):
        try:
            file = load_functional_file(path)
        except FnYamlError:
            continue  # a mapping that does not load reports itself
        if uses(file, label):
            found.append(path.name.removesuffix(".fn.yaml"))
    return found


# -- what changed -----------------------------------------------------------------------------


def _show(value: Any) -> str:
    return repr(value) if isinstance(value, str) else str(value)


def describe_change(old: LookupRule, new: LookupRule) -> list[str]:
    """What differs between two versions of a table, in a few short phrases."""
    changes: list[str] = []
    for key, value in new.entries.items():
        if key not in old.entries:
            changes.append(f"added {key} = {_show(value)}")
        elif old.entries[key] != value:
            changes.append(f"{key}: {_show(old.entries[key])} -> {_show(value)}")
    changes += [f"removed {key}" for key in old.entries if key not in new.entries]
    if old.type != new.type:
        changes.append(f"type {old.type or 'not declared'} -> {new.type or 'not declared'}")
    if len(changes) > _SHOWN_CHANGES:
        rest = len(changes) - _SHOWN_CHANGES
        changes = [*changes[:_SHOWN_CHANGES], f"and {rest} more"]
    return changes


def mark_changed(project: Path, old: LookupRule, new: LookupRule) -> dict[str, list[str]]:
    """After a table changed: in every mapping, the rules that read it and were validated (or
    were already waiting for review) go to review, with a note saying what changed since the
    last validation. Gives the mappings touched -> the rules."""
    changes = describe_change(old, new)
    if not changes:
        return {}
    note = f"@{new.label} changed ({datetime.date.today().isoformat()}): " + "; ".join(changes)
    touched: dict[str, list[str]] = {}
    for path in mapping_files(project):
        try:
            file = load_functional_file(path)
        except FnYamlError:
            continue
        assign_ids(file)
        marked: list[str] = []
        for rule in _walk(file.rules):
            if not isinstance(rule, FieldRule) or not _field_reads(new.label, rule):
                continue
            v = rule.validation
            if not (v.validated or v.needs_review):
                continue  # never validated: there is no earlier state to compare with
            v.validated, v.needs_review = False, True
            if note not in (v.notes or ""):
                v.notes = f"{v.notes}\n{note}" if v.notes else note
            marked.append(rule.id or rule.field)
        if marked:
            write_functional(path, file)
            touched[path.name.removesuffix(".fn.yaml")] = marked
    return touched


# -- the operations of the tool --------------------------------------------------------------


def describe(project: Path) -> list[dict[str, Any]]:
    """Every project-wide table, with the mappings that read it."""
    return [
        {
            "label": label,
            "type": rule.type,
            "description": rule.description,
            "entries": rule.entries,
            "used_by": users(project, label),
        }
        for label, rule in load_shared(project).items()
    ]


def save(
    project: Path,
    label: str,
    entries: dict[str, Any],
    type_: str | None,
    description: str | None,
    create: bool = False,
) -> dict[str, list[str]]:
    """Creates (`create`) or changes a table. Gives the mappings whose rules went back to review."""
    if not _IDENT.match(label):
        raise FnYamlError(f"{label!r} is not a valid label: letters, digits and _")
    exists = lookup_file(project, label).is_file()
    if create and exists:
        raise FnYamlError(f"there is already a project-wide lookup called @{label}")
    if not create and not exists:
        raise FnYamlError(f"no project-wide lookup called @{label}")
    if create:
        _check_free(project, label)
    new = _to_rule(
        label, {"entries": entries, "type": type_, "description": description or None}, label
    )
    old = None if create else read_shared(project, label)
    write_shared(project, new)
    return {} if old is None else mark_changed(project, old, new)


def _check_free(project: Path, label: str) -> None:
    """A new project-wide label must not be a lookup, a loop label or an alias of a mapping."""
    for path in mapping_files(project):
        try:
            file = load_functional_file(path)
        except FnYamlError:
            continue
        name = path.name.removesuffix(".fn.yaml")
        if label in {r.label for r in _local(file.rules)}:
            raise FnYamlError(f"mapping {name} has its own lookup called @{label}")
        if label in {r.label for r in _walk(file.rules) if isinstance(r, LoopRule) and r.label}:
            raise FnYamlError(f"mapping {name} has a loop labelled {label}")
        if label in file.paths.aliases:
            raise FnYamlError(f"mapping {name} has an alias called {label}")


def delete(project: Path, label: str) -> None:
    """Removes a table, unless a mapping reads it."""
    if not lookup_file(project, label).is_file():
        raise FnYamlError(f"no project-wide lookup called @{label}")
    readers = users(project, label)
    if readers:
        raise FnYamlError(
            f"@{label} is read by {', '.join(readers)}: change those mappings first "
            "(or clear Project wide to give each its own copy)"
        )
    lookup_file(project, label).unlink()


def _take_out(rules: list[Rule], label: str) -> LookupRule | None:
    for i, rule in enumerate(rules):
        if isinstance(rule, LookupRule) and rule.label == label:
            return rules.pop(i)  # type: ignore[return-value]
        if isinstance(rule, ObjectRule | LoopRule):
            found = _take_out(rule.rules, label)
            if found is not None:
                return found
    return None


def share(project: Path, stem: str, label: str) -> list[str]:
    """Moves the lookup `label` of mapping `stem` into the project. Gives the other mappings that
    declare a lookup of the same name (they now clash with it and must drop theirs)."""
    path = project / FUNCTIONAL / f"{stem}.fn.yaml"
    file = load_functional_file(path)
    if label in file.shared or lookup_file(project, label).is_file():
        raise FnYamlError(f"there is already a project-wide lookup called @{label}")
    rule = _take_out(file.rules, label)
    if rule is None:
        raise FnYamlError(f"mapping {stem} has no lookup called @{label}")
    write_shared(project, rule)
    write_functional(path, file)
    others: list[str] = []
    for other in mapping_files(project):
        if other == path:
            continue
        try:
            if label in {r.label for r in _local(load_functional_file(other).rules)}:
                others.append(other.name.removesuffix(".fn.yaml"))
        except FnYamlError:
            continue
    return others


def unshare(project: Path, label: str) -> list[str]:
    """Gives every mapping that reads the project-wide lookup its own copy, then removes it from
    the project. Gives the mappings changed."""
    rule = read_shared(project, label)
    changed: list[str] = []
    for path in mapping_files(project):
        file = load_functional_file(path)
        if not uses(file, label):
            continue
        copy = LookupRule(
            id=None,
            label=label,
            entries=dict(rule.entries),
            description=rule.description,
            type=rule.type,
        )
        file.rules.insert(0, copy)
        assign_ids(file)
        write_functional(path, file)
        changed.append(path.name.removesuffix(".fn.yaml"))
    lookup_file(project, label).unlink()
    return changed
