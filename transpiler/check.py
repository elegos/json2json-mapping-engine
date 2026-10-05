"""Check a Rule Tree rule by rule (M6.1b), for the desktop tool.

Every rule is checked on its own, so one bad rule does not hide the others:

- **form** — the loader's checks on the rule alone, expression syntax and anchors
  (unknown label, `@` outside a loop), duplicate names inside a container;
- **validity against the data** — when a JSON Schema exists: a Target must exist in the
  output schema with a compatible type (and `required` must not contradict it), a
  container must be an object / array as declared and cover the schema's required
  fields; a Source and every `$.` / `@.` reference in an expression must exist in the
  input schema.

A schema construct this module does not understand (`patternProperties`, a `$ref` it
cannot follow, …) is treated as "unknown": nothing is reported against it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from compiler.function_registry import FunctionInfo
from compiler.schema_files import Kind, resolve_schema_path
from transpiler.anchors import (
    AnchorScope,
    LoopRef,
    _split_strings,
    resolve_anchors,
    uses_value,
)
from transpiler.expr import parse_block
from transpiler.exprtypes import ExprTyper
from transpiler.model import (
    RESERVED_ALIASES,
    FieldRule,
    FnYamlError,
    FunctionalFile,
    LookupRule,
    LoopRule,
    ObjectRule,
    Rule,
    SchemasSection,
    is_alias_path,
    is_unfinished,
    load_rule,
)
from transpiler.paths import expand_paths
from transpiler.selector import (
    find_selections,
    normalize_condition,
    replace_selections,
    split_selector,
)
from transpiler.serialize import rule_to_raw

Schema = dict[str, Any]


@dataclass
class Issue:
    rule: str  # `rules[0].rules[1]`; "" for the file as a whole
    column: str | None  # grid column id
    severity: str  # "error" | "warning"
    message: str
    code: str = ""  # a kind the build acts on ("unfinished"), else empty

    def to_json(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "file": None,
            "rule": self.rule or None,
            "column": self.column,
            "message": self.message,
        }


class _Unknown:
    """Stands for a schema part that cannot be followed: nothing is reported against it."""


UNKNOWN = _Unknown()
Node = Schema | _Unknown | None  # None = does not exist

_IDENT = re.compile(r"^[A-Za-z_]\w*$")
_SEGMENT = re.compile(r"\.?([A-Za-z_]\w*)|(\[(?:\*|\d+)\])")
_TYPES = {
    "str": {"string"},
    "int": {"integer"},
    "number": {"number", "integer"},
    "bool": {"boolean"},
    "date": {"string"},
    "datetime": {"string"},
}


class _Schemas:
    def __init__(self, root: Schema | None):
        self.root = root

    def deref(self, node: Schema) -> Schema:
        seen = 0
        while "$ref" in node and seen < 20:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/") or self.root is None:
                return {}
            target: Any = self.root
            for part in ref[2:].split("/"):
                target = (
                    target.get(part.replace("~1", "/").replace("~0", "~"))
                    if isinstance(target, dict)
                    else None
                )
            if not isinstance(target, dict):
                return {}
            node, seen = target, seen + 1
        return node

    def variants(self, node: Schema) -> list[Schema]:
        node = self.deref(node)
        alts = node.get("oneOf") or node.get("anyOf")
        if isinstance(alts, list) and alts:
            return [v for a in alts if isinstance(a, dict) for v in self.variants(a)]
        return [node]

    def types(self, node: Schema) -> set[str]:
        found: set[str] = set()
        for v in self.variants(node):
            t = v.get("type")
            found |= {t} if isinstance(t, str) else set(t) if isinstance(t, list) else set()
        return found - {"null"}

    def nullable(self, node: Schema) -> bool:
        """Whether the schema lets the value be null."""
        for v in self.variants(node):
            t = v.get("type")
            if t == "null" or (isinstance(t, list) and "null" in t):
                return True
        return False

    def prop(self, node: Node, name: str) -> Node:
        if not isinstance(node, dict):
            return node
        unknown = False
        for v in self.variants(node):
            props = v.get("properties")
            if isinstance(props, dict) and isinstance(props.get(name), dict):
                return props[name]
            extra = v.get("additionalProperties")
            if isinstance(extra, dict):
                return extra
            if not isinstance(props, dict) or extra is True or "patternProperties" in v:
                unknown = True
        return UNKNOWN if unknown else None

    def values(self, node: Schema) -> list[Schema] | None:
        """The schemas of an object's values (its properties, or `additionalProperties`);
        None where they cannot be listed."""
        found: list[Schema] = []
        for v in self.variants(node):
            props = v.get("properties")
            extra = v.get("additionalProperties")
            if "patternProperties" in v or extra is True:
                return None
            if isinstance(props, dict):
                found += [self.deref(p) for p in props.values() if isinstance(p, dict)]
            if isinstance(extra, dict):
                found.append(self.deref(extra))
        return found

    def items(self, node: Node) -> Node:
        if not isinstance(node, dict):
            return node
        for v in self.variants(node):
            if isinstance(v.get("items"), dict):
                return v["items"]
        return None if "array" in self.types(node) else UNKNOWN

    def resolve(self, base: Node, text: str) -> tuple[Node, str | None]:
        """Follow `a.b[*].c` from `base`. Returns the node reached, or (None, what is missing)."""
        node = base
        for m in _SEGMENT.finditer(text):
            if node is UNKNOWN or node is None:
                break
            if m.group(2):
                node = self.items(node)
                if node is None:
                    return None, "[*] (not an array)"
            else:
                node = self.prop(node, m.group(1))
                if node is None:
                    return None, m.group(1)
        return node, None

    def required(self, node: Node) -> list[str]:
        if not isinstance(node, dict):
            return []
        out: list[str] = []
        for v in self.variants(node):
            req = v.get("required")
            out += [r for r in req if isinstance(r, str)] if isinstance(req, list) else []
        return out


# the schema walker, for the tools that read a schema the way the check does
SchemaView = _Schemas


class _TableName(str):
    """Prints as its own name: the anchor resolver `repr`s a lookup into the expression."""

    def __repr__(self) -> str:
        return str(self)


_JSON_TYPE = {
    "str": "string",
    "date": "string",
    "datetime": "string",
    "int": "integer",
    "number": "number",
    "bool": "boolean",
}


def _constant_node(value: Any) -> Schema | _Unknown:
    """A schema for a constant Source; a null tells nothing."""
    kind = (
        "boolean" if isinstance(value, bool)
        else "integer" if isinstance(value, int)
        else "number" if isinstance(value, float)
        else "string" if isinstance(value, str)
        else None
    )  # fmt: skip
    return {"type": kind} if kind else UNKNOWN


def _lookup_node(rule: LookupRule) -> Schema:
    """A schema for a lookup's entries: an object whose values have the declared type, or,
    when none is declared, the type they all share (nothing stated if they differ)."""
    declared = _JSON_TYPE.get(rule.type or "")
    if declared is None:
        kinds = {
            "boolean" if isinstance(v, bool)
            else "integer" if isinstance(v, int)
            else "number" if isinstance(v, float)
            else "string" if isinstance(v, str)
            else "?"
            for v in rule.entries.values()
        }  # fmt: skip
        declared = kinds.pop() if len(kinds) == 1 and "?" not in kinds else None
    values: Schema = {"type": declared} if declared else {}
    return {"type": "object", "additionalProperties": values}


_REF = re.compile(r"^(\$|@(?:\d+|[A-Za-z_]\w*)?)((?:\.[A-Za-z_]\w*|\[(?:\*|\d+)\])+)$")


def _lookup_calls(text: str) -> list[tuple[str, bool]]:
    """For each `lookup(...)` call of `text`: its second argument as written, and whether
    the call is the whole expression. Strings and nested brackets are skipped over."""
    calls: list[tuple[str, bool]] = []
    for m in re.finditer(r"\blookup\s*\(", text):
        depth, quote, args, start = 1, "", [], m.end()
        i = start
        while i < len(text) and depth:
            c = text[i]
            if quote:
                quote = "" if c == quote and text[i - 1] != "\\" else quote
            elif c in "\"'":
                quote = c
            elif c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
                if depth == 0:
                    args.append(text[start:i])
            elif c == "," and depth == 1:
                args.append(text[start:i])
                start = i + 1
            i += 1
        if depth == 0 and len(args) >= 2:
            whole = m.start() == len(text) - len(text.lstrip()) and text[i:].strip() == ""
            calls.append((args[1].strip(), whole))
    return calls


_REF = re.compile(
    r"(\$|@(?:\d+|[A-Za-z_]\w*)?)((?:\.[A-Za-z_]\w*|\[(?:\*|\d+)\])+)(\()?",
)


class _Checker:
    def __init__(
        self,
        file: FunctionalFile,
        input_schema: Schema | None,
        output_schema: Schema | None,
        functions: Mapping[str, FunctionInfo] | None = None,
    ):
        self.file = file
        self.functions = functions
        self.inp = _Schemas(input_schema)
        self.out = _Schemas(output_schema)
        self.has_in = input_schema is not None
        self.has_out = output_schema is not None
        self.issues: list[Issue] = []
        found = [r for r in self._all(file.rules) if isinstance(r, LookupRule)]
        everything = [*file.shared.values(), *found]
        self.lookups = {r.label: dict(r.entries) for r in everything}
        self.lookup_nodes = {r.label: _lookup_node(r) for r in everything}

    def _all(self, rules: list[Rule]):
        for r in rules:
            yield r
            if isinstance(r, ObjectRule | LoopRule):
                yield from self._all(r.rules)

    def add(
        self, rule: str, column: str | None, message: str, severity: str = "error", code: str = ""
    ) -> None:
        self.issues.append(Issue(rule, column, severity, message, code))

    # -- form ------------------------------------------------------------------

    def form(self, path: str, rule: Rule) -> None:
        raw = rule_to_raw(rule)
        raw.pop("rules", None)
        try:
            load_rule(path, raw)
        except FnYamlError as exc:
            self.add(path, _column_of(str(exc)), str(exc).split(": ", 1)[-1])
        if isinstance(rule, LookupRule) and rule.label in self.file.shared:
            self.add(
                path,
                "label",
                f"@{rule.label} is also a project-wide lookup: remove this one, or rename it",
            )

    def block(
        self, path: str, text: str, scope: AnchorScope, column: str, dev: bool = False
    ) -> None:
        try:
            resolved = text if dev else resolve_anchors(text, scope, "expression").text
            parse_block(resolved, "x", "expression")
        except FnYamlError as exc:
            self.add(path, column, str(exc).split(": ", 1)[-1])

    # -- data ------------------------------------------------------------------

    def selections(
        self,
        path: str,
        text: str,
        column: str,
        scope: AnchorScope,
        root: Node,
        items: list[Node],
        labels: list[str | None],
    ) -> str:
        """Checks the condition of each selection in `text` (`$.items[marker = 'T'].qty`) as a
        filter is checked: the list must exist and the condition reads the candidate as `@`.
        Answers `text` with each selection as the first element (`$.items[0].qty`), which the
        other checks can follow."""
        for sel in find_selections(text):
            condition = normalize_condition(sel.condition)
            if find_selections(condition):
                self.add(path, column, "a condition cannot hold another selection")
                continue
            m = re.match(r"(\$|@(?:\d+|[A-Za-z_]\w*)?)(.*)$", sel.path)
            base = self._anchor(m.group(1), root, items, labels) if m else UNKNOWN
            item: Node = UNKNOWN
            if self.has_in and m and base is not UNKNOWN and base is not None:
                reached, missing = self.inp.resolve(base, f"{m.group(2)}[*]")
                if reached is None:
                    self.add(path, column, f"'{missing}' is not in the input schema ({sel.path})")
                else:
                    item = reached
            inner = AnchorScope(
                loops=(*scope.loops, LoopRef(None, "src", "index")), lookups=scope.lookups
            )
            self.block(path, condition, inner, column)
            self.refs(path, condition, column, root, [*items, item], [*labels, None])
            self.typecheck(path, condition, None, "", root, [*items, item], [*labels, None])
        return replace_selections(text, lambda s: f"{s.path}[0]")

    def refs(
        self,
        path: str,
        text: str,
        column: str,
        root: Node,
        items: list[Node],
        labels: list[str | None],
    ) -> None:
        """Every `$.a.b` / `@.x` reference of `text` must exist in the input schema."""
        if not self.has_in:
            return
        for is_string, chunk in _split_strings(text):
            if is_string:
                continue
            for m in _REF.finditer(chunk):
                anchor, chain, call = m.group(1), m.group(2), m.group(3)
                if call:  # `$.a.strip(` — the last segment is a method, not a field
                    chain = chain[: chain.rfind(".")] if "." in chain else chain
                base = self._anchor(anchor, root, items, labels)
                if base is UNKNOWN or base is None or not chain:
                    continue
                node, missing = self.inp.resolve(base, chain)
                if node is None:
                    self.add(
                        path, column, f"'{missing}' is not in the input schema ({anchor}{chain})"
                    )

    def types(
        self,
        path: str,
        rule: FieldRule,
        text: str,
        root: Node,
        items: list[Node],
        labels: list[str | None],
        value: Node = None,
    ) -> None:
        """What the expression yields against what the field is (`transpiler.exprtypes`)."""
        wanted = _TYPES.get(rule.type)
        self.typecheck(
            path,
            text,
            frozenset(wanted) if wanted else None,
            f"the field is '{rule.type}'",
            root,
            items,
            labels,
            value,
        )

    def typecheck(
        self,
        path: str,
        text: str,
        want: frozenset[str] | None,
        what: str,
        root: Node,
        items: list[Node],
        labels: list[str | None],
        value: Node = None,
    ) -> None:
        loops = tuple(LoopRef(lbl, f"_L{i}", f"_I{i}") for i, lbl in enumerate(labels, 1))
        # a lookup is typed by its declared type: it stands for a name whose schema says so
        tables = {label: _TableName(f"_LK_{label}") for label in self.lookups}
        try:
            resolved = resolve_anchors(text, AnchorScope(loops, tables), "expression").text  # type: ignore[arg-type]
        except FnYamlError:
            return  # reported by `block`
        env: dict[str, Any] = {"root": root, "value": value}
        env.update({f"_LK_{label}": node for label, node in self.lookup_nodes.items()})
        env.update({f"_L{i}": node for i, node in enumerate(items, 1)})
        typer = ExprTyper(
            self.inp, env, lambda message: self.add(path, "expression", message), self.functions
        )
        typer.check(resolved, want, what)

    def devcheck(self, path: str, text: str, root: Node, items: list[Node]) -> None:
        """The calls of a code override (developer dialect: `root`, `src`, `src1`...): arguments
        and their types, against the registry."""
        env: dict[str, Any] = {"root": root}
        env.update({("src" if o == 0 else f"src{o}"): n for o, n in enumerate(reversed(items))})
        indexes = ["index" if o == 0 else f"index{o}" for o in range(len(items))]
        ExprTyper(
            self.inp, env, lambda message: self.add(path, "status", message), self.functions
        ).check_block(text, indexes)

    def _anchor(self, anchor: str, root: Node, items: list[Node], labels: list[str | None]) -> Node:
        if anchor == "$":
            return root
        name = anchor[1:]
        if not items:
            return None
        if name == "":
            return items[-1]
        if name.isdigit():
            n = int(name)
            return items[-n] if 1 <= n <= len(items) else UNKNOWN
        for i in range(len(labels) - 1, -1, -1):
            if labels[i] == name:
                return items[i]
        return UNKNOWN  # a lookup label, or an error the form check reports

    # -- walk ------------------------------------------------------------------

    def walk(
        self,
        rules: list[Rule],
        prefix: str,
        scope: AnchorScope,
        out: Node,
        in_root: Node,
        items: list[Node],
        labels: list[str | None],
    ) -> None:
        names: set[str] = set()
        covered: set[str] = set()
        for i, rule in enumerate(rules):
            path = f"{prefix}[{i}]"
            self.form(path, rule)
            if isinstance(rule, LookupRule):
                continue
            name = rule.field if isinstance(rule, FieldRule) else _basename(rule.output)
            covered.add(name)
            if is_unfinished(rule):
                self.unfinished(path, rule, name, out)
            if name in names:
                self.add(path, "target", f"'{name}' is already a rule of this container")
            names.add(name)
            if isinstance(rule, FieldRule):
                self.field(path, rule, scope, out, in_root, items, labels)
            else:
                self.container(path, rule, scope, out, in_root, items, labels)
        if self.has_out and isinstance(out, dict):
            missing = [r for r in self.out.required(out) if r not in covered]
            if missing:
                where = prefix.rsplit(".rules", 1)[0] if ".rules" in prefix else ""
                self.add(where, "target", f"the output schema requires {', '.join(missing)}")

    def unfinished(self, path: str, rule: Rule, name: str, out: Node) -> None:
        """A rule with nothing defined: ignored by the build, so a warning, unless the output
        schema requires what it would produce (an error: the build stops)."""
        what = "a Source" if isinstance(rule, FieldRule | LoopRule) else "a rule with a Source"
        if self.has_out and isinstance(out, dict) and name in self.out.required(out):
            self.add(
                path,
                "source",
                f"required by the output schema, but it still needs {what}",
                code="unfinished",
            )
        else:
            self.add(path, "source", f"ignored until {what} is defined", "warning")

    def field(self, path, rule: FieldRule, scope, out, in_root, items, labels) -> None:
        t = rule.transform
        text = t.code_override if t.status == "manual" else t.expression
        has_source = rule.has_constant or bool(rule.source_path)
        value: Node = UNKNOWN  # what `value` stands for: the Source
        if rule.has_constant:
            value = _constant_node(rule.source_constant)
        elif rule.source_path:
            src = self.selections(path, rule.source_path, "source", scope, in_root, items, labels)
            if self.has_in:
                base = in_root if src.startswith("$") else (items[-1] if items else in_root)
                node, missing = self.inp.resolve(base, re.sub(r"^[$@]", "", src))
                if node is None:
                    self.add(path, "source", f"'{missing}' is not in the input schema")
                else:
                    value = node
        if text and t.status != "manual":
            text = self.selections(path, text, "expression", scope, in_root, items, labels)
        if text:
            self.block(
                path,
                text,
                scope,
                "status" if t.status == "manual" else "expression",
                t.status == "manual",
            )
            if t.status == "manual":
                self.devcheck(path, text, in_root, items)
            if t.status != "manual":
                self.refs(path, text, "expression", in_root, items, labels)
                if uses_value(text) and not has_source:
                    self.add(path, "expression", "`value` is used but the rule has no Source")
        if t.status != "manual" and (text or has_source):
            # no expression: the field takes its Source value as it is
            self.types(path, rule, text or "value", in_root, items, labels, value)
        if not self.has_out or not isinstance(out, dict):
            return
        node = self.out.prop(out, rule.field)
        if node is None:
            self.add(path, "target", f"'{rule.field}' is not in the output schema")
            return
        if isinstance(node, dict):
            declared = self.out.types(node)
            if declared and not (declared & _TYPES.get(rule.type, set())):
                self.add(
                    path,
                    "type",
                    f"declared '{rule.type}' but the output schema says {'/'.join(sorted(declared))}",
                )
        if not rule.required and rule.field in self.out.required(out):
            self.add(path, "req", "required by the output schema")

    def container(
        self, path, rule: ObjectRule | LoopRule, scope, out, in_root, items, labels
    ) -> None:
        name = _basename(rule.output)
        node: Node = UNKNOWN
        if self.has_out and isinstance(out, dict):
            node = self.out.prop(out, name)
            if node is None:
                self.add(path, "target", f"'{name}' is not in the output schema")
                node = UNKNOWN
        is_loop = isinstance(rule, LoopRule)
        if isinstance(node, dict):
            types = self.out.types(node)
            want = "array" if is_loop else "object"
            if types and want not in types:
                self.add(
                    path, "type", f"the output schema says {'/'.join(sorted(types))}, not {want}"
                )
                node = UNKNOWN
            elif is_loop:
                node = self.out.items(node)
            elif types and not self.out.nullable(node) and (rule.guard or rule.source):
                # the build refuses a non-nullable output for a value that may be omitted
                self.add(
                    path,
                    "type",
                    f"'{name}' is left out when its "
                    f"{'guard is false' if rule.guard else 'source selects no element'}, "
                    'so the output schema must allow null (type ["object", "null"])',
                )
        selector = (
            split_selector(rule.source) if isinstance(rule, ObjectRule) and rule.source else None
        )
        if isinstance(rule, ObjectRule) and selector is None:
            if rule.guard:
                guard = self.selections(
                    path, rule.guard, "expression", scope, in_root, items, labels
                )
                self.block(path, guard, scope, "expression")
                self.refs(path, guard, "expression", in_root, items, labels)
                # a condition is true or false as in Python: no type is expected of it
                self.typecheck(path, guard, None, "", in_root, items, labels)
            self.walk(rule.rules, f"{path}.rules", scope, node, in_root, items, labels)
            return
        # a loop, or an object that selects one element of a list: both read an element `@`
        if selector is not None:
            source, condition, label = f"{selector[0]}[*]", selector[1], None
        else:
            assert isinstance(rule, LoopRule)
            source, condition, label = rule.source, rule.filter, rule.label
        item: Node = UNKNOWN
        if not source.strip() and not is_unfinished(rule):
            self.add(path, "source", "a loop needs a source")
        if self.has_in and source:
            base = in_root if source.startswith("$") else (items[-1] if items else in_root)
            reached, missing = self.inp.resolve(base, re.sub(r"^[$@]", "", source))
            if reached is None:
                self.add(path, "source", f"'{missing}' is not in the input schema")
            else:
                item = reached
        inner = AnchorScope(
            loops=(*scope.loops, LoopRef(label, "src", "index")), lookups=scope.lookups
        )
        if selector is None and condition and find_selections(condition):
            self.add(
                path,
                "expression",
                "a filter cannot hold a selection (a path with a condition in it): "
                "read it in the fields of the loop",
            )
            condition = None
        if condition:
            column = "expression" if selector is None else "source"
            self.block(path, condition, inner, column)
            self.refs(path, condition, column, in_root, [*items, item], [*labels, label])
            self.typecheck(path, condition, None, "", in_root, [*items, item], [*labels, label])
        self.walk(
            rule.rules, f"{path}.rules", inner, node, in_root, [*items, item], [*labels, label]
        )

    def paths(self, original: FunctionalFile) -> None:
        """The `paths:` section: names and syntax always, existence when there is an input schema."""
        section = original.paths
        named = [("root", section.root)] if section.root else []
        named += [(f"alias '{n}'", p) for n, p in section.aliases.items()]
        loops = {r.label for r in self._all(original.rules) if isinstance(r, LoopRule) and r.label}
        for name in section.aliases:
            problem = None
            if not _IDENT.match(name):
                problem = "is not a valid name"
            elif name in RESERVED_ALIASES:
                problem = f"is reserved (@{name})"
            elif name in self.lookups:
                problem = "is also the name of a lookup table"
            elif name in loops:
                problem = "is also the label of a loop"
            if problem:
                self.add("", "paths", f"paths: alias '{name}' {problem}")
        for what, text in named:
            assert text is not None
            if not is_alias_path(text, selection=what != "root"):
                self.add(
                    "",
                    "paths",
                    f"paths: the {what} must be a path from the root like $.a.b[0] — got {text!r}",
                )
                continue
            if what != "root":
                # a condition in an alias is checked as where it is used
                root = self.inp.root if self.inp.root is not None else UNKNOWN
                text = self.selections(
                    "", text, "paths", AnchorScope(lookups=self.lookups), root, [], []
                )
            if self.has_in and self.inp.root is not None:
                node, missing = self.inp.resolve(self.inp.root, text.removeprefix("$"))
                if node is None:
                    self.add(
                        "",
                        "paths",
                        f"paths: the {what} {text} — '{missing}' is not in the input schema",
                    )

    def run(self) -> list[Issue]:
        root_in: Node = self.inp.root if self.inp.root is not None else UNKNOWN
        root_out: Node = self.out.root if self.out.root is not None else UNKNOWN
        scope = AnchorScope(lookups=self.lookups)
        self.walk(self.file.rules, "rules", scope, root_out, root_in, [], [])
        return self.issues


def _basename(output: str) -> str:
    return re.sub(r"^[$@]\.?", "", output).removesuffix("[*]")


def _column_of(message: str) -> str | None:
    named = message.split(": ", 1)[-1]
    for pattern, column in (
        (r"'(field|output|label)'", "target"),
        (r"'type'", "type"),
        (r"'required'", "req"),
        (r"source", "source"),
        (r"transform|expression|guard|filter|sort|parallel", "expression"),
    ):
        if re.search(pattern, named):
            return column
    return None


def check_functional(
    file: FunctionalFile,
    input_schema: Schema | None = None,
    output_schema: Schema | None = None,
    functions: Mapping[str, FunctionInfo] | None = None,
) -> list[Issue]:
    """`functions`: the registry to type calls with (built-ins and the project's own); the
    built-ins by default."""
    checker = _Checker(expand_paths(file), input_schema, output_schema, functions)
    checker.paths(file)
    return checker.run()


def schemas_for(
    project: Path, stem: str, refs: SchemasSection | None = None
) -> tuple[Schema | None, Schema | None]:
    """The input / output schemas of `mappings/.../<stem>.fn.yaml`: the file's `schemas:`
    section (`refs`) where it points elsewhere, else by convention
    (`schemas/<stem>_input.schema.json`, `..._output...`); None where a file is missing or
    unreadable."""

    def load(kind: Kind) -> Schema | None:
        override = (refs.input if kind == "input" else refs.output) if refs else None
        path = resolve_schema_path(project, stem, kind, override)
        try:
            data = json.loads(path.read_text())
        except OSError, ValueError:
            return None
        return data if isinstance(data, dict) else None

    return load("input"), load("output")
