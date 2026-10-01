"""Completion for the Target, Source and Expression cells of the desktop tool.

`complete(...)` answers "what can be typed at this cursor position?" from the file's rules and
the project's JSON Schemas; the tool shows the answer in a drop-down. The semantics (what
`$`, `@`, a bare name mean in each column, which loop is `@`) are the ones `check` uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from compiler.function_registry import FunctionInfo, builtin_functions
from transpiler.check import UNKNOWN, Node, _Schemas
from transpiler.model import (
    RESERVED_ALIASES,
    FieldRule,
    FunctionalFile,
    LookupRule,
    LoopRule,
    ObjectRule,
    Rule,
)
from transpiler.paths import expand_paths
from transpiler.selector import split_selector

Schema = dict[str, Any]

_KEYWORDS = ("and", "or", "not", "in", "True", "False", "None")


@dataclass
class Item:
    label: str  # shown
    insert: str  # replaces the text typed since `from_`
    kind: str  # field | function | label | lookup | alias | keyword | value
    detail: str = ""
    doc: str = ""  # longer explanation (a function's docstring)
    origin: str = ""  # where a function comes from: "built-in" or its project file

    def to_json(self) -> dict[str, str]:
        return {
            "label": self.label,
            "insert": self.insert,
            "kind": self.kind,
            "detail": self.detail,
            "doc": self.doc,
            "origin": self.origin,
        }


@dataclass
class Completion:
    from_: int  # offset in the cell text where the replaced part starts
    items: list[Item]

    def to_json(self) -> dict[str, Any]:
        return {"from": self.from_, "items": [i.to_json() for i in self.items]}


@dataclass
class _Context:
    """What the cell's rule can see: the input and output nodes and the loops around it."""

    items: list[Node]
    labels: list[str | None]
    out: Node  # the output node of the container the rule is in
    taken: set[str]  # sibling names already used in that container
    notes: list[str] = field(default_factory=list)  # what each element of `items` is
    loops: list[bool] = field(default_factory=list)  # ... and whether it is a loop's (has an index)


def _describe(schemas: _Schemas, node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    types = sorted(schemas.types(node))
    if "array" in types:
        inner = schemas.items(node)
        if isinstance(inner, dict):
            kinds = sorted(schemas.types(inner))
            return f"array of {'/'.join(kinds)}" if kinds else "array"
    return "/".join(types)


def _properties(schemas: _Schemas, node: Node) -> dict[str, Any]:
    found: dict[str, Any] = {}
    if not isinstance(node, dict):
        return found
    for variant in schemas.variants(node):
        props = variant.get("properties")
        if isinstance(props, dict):
            for name, sub in props.items():
                found.setdefault(name, sub)
    return found


def _basename(output: str) -> str:
    return re.sub(r"^[$@]\.?", "", output).removesuffix("[*]")


def _context(
    file: FunctionalFile, path: str, inp: _Schemas, out: _Schemas, dollar: Node
) -> _Context | None:
    """Walk to the rule at `path` (on the file with paths expanded), collecting what it sees."""
    steps = [int(n) for n in re.findall(r"rules\[(\d+)\]", path)]
    if not steps:
        return None
    rules: list[Rule] = file.rules
    out_node: Node = out.root if out.root is not None else UNKNOWN
    items: list[Node] = []
    labels: list[str | None] = []
    notes: list[str] = []
    loops: list[bool] = []
    for depth, step in enumerate(steps):
        if step >= len(rules):
            return None
        rule = rules[step]
        if depth == len(steps) - 1:
            siblings = {
                (r.field if isinstance(r, FieldRule) else _basename(r.output))
                for i, r in enumerate(rules)
                if i != step and not isinstance(r, LookupRule)
            }
            return _Context(items, labels, out_node, siblings, notes, loops)
        if not isinstance(rule, ObjectRule | LoopRule):
            return None
        out_node = out.prop(out_node, _basename(rule.output))
        if isinstance(rule, LoopRule) and isinstance(out_node, dict):
            out_node = out.items(out_node)
        selector = (
            split_selector(rule.source) if isinstance(rule, ObjectRule) and rule.source else None
        )
        if selector is not None or isinstance(rule, LoopRule):
            source = f"{selector[0]}[*]" if selector else getattr(rule, "source", None) or ""
            base = dollar if source.startswith("$") else (items[-1] if items else dollar)
            node, _missing = (
                inp.resolve(base, re.sub(r"^[$@]", "", source)) if source else (UNKNOWN, None)
            )
            items = [*items, node if node is not None else UNKNOWN]
            labels = [*labels, rule.label if isinstance(rule, LoopRule) else None]
            loops = [*loops, isinstance(rule, LoopRule)]
            notes = [
                *notes,
                f"element of the loop over {source}"
                if isinstance(rule, LoopRule)
                else f"element selected by the object's Source ({source})",
            ]
        rules = rule.rules
    return None


_RUN = re.compile(r"[\w@$.\[\]*]*$")
_ANCHOR = re.compile(r"\$|@[A-Za-z_]\w*|@\d+|@")


def _inside_string(before: str) -> bool:
    quote = ""
    i = 0
    while i < len(before):
        ch = before[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        i += 1
    return bool(quote)


def _rank(items: list[Item], partial: str) -> list[Item]:
    low = partial.lower()
    starts = [i for i in items if i.label.lower().startswith(low)]
    if starts or not low:
        return starts or items
    return [i for i in items if low in i.label.lower()]


def complete(
    file: FunctionalFile,
    path: str,
    column: str,
    text: str,
    cursor: int,
    input_schema: Schema | None,
    output_schema: Schema | None,
    functions: dict[str, FunctionInfo] | None = None,
) -> Completion:
    """Suggestions for `text` (the cell's content) at offset `cursor` of the rule at `path`.
    `column` is `target`, `source`, `expression` or `code` (a rule's `code_override`:
    the developer dialect, with `root`, `src`, `src1`... instead of anchors)."""
    inp, out = _Schemas(input_schema), _Schemas(output_schema)
    expanded = expand_paths(file)
    section = file.paths
    real_root: Node = inp.root if inp.root is not None else UNKNOWN
    dollar: Node = real_root
    if section.root and inp.root is not None:
        reached, _m = inp.resolve(inp.root, section.root.removeprefix("$"))
        dollar = reached if reached is not None else UNKNOWN
    ctx = _context(expanded, path, inp, out, dollar)
    if ctx is None:
        return Completion(cursor, [])
    before = text[:cursor]
    if _inside_string(before):
        return Completion(cursor, [])
    if column == "target":
        return _target(before, cursor, ctx, out)

    if column == "code":
        return _code(before, cursor, ctx, inp, real_root, functions)

    # a condition `$.list[...]` in a Source: the element is the one being tested
    items, labels = ctx.items, ctx.labels
    open_at = _unclosed_bracket(before) if column == "source" else None
    if open_at is not None:
        listed = before[:open_at]
        base = dollar if listed.startswith("$") else (items[-1] if items else dollar)
        node, _m = inp.resolve(base, re.sub(r"^[$@]", "", listed) + "[*]")
        items = [*items, node if node is not None else UNKNOWN]
        labels = [*labels, None]

    # inside a condition only what follows its `[` is the expression being typed
    floor = open_at + 1 if open_at is not None else 0
    run = _RUN.search(before, floor)
    token = run.group(0) if run else ""
    start = cursor - len(token)
    anchor_match = _ANCHOR.match(token)

    def anchor_node(anchor: str) -> tuple[Node, bool]:
        """(node the anchor stands for, whether it is a known anchor)"""
        if anchor == "$":
            return dollar, True
        name = anchor[1:]
        if name == "":
            return (items[-1] if items else None), bool(items)
        if name.isdigit():
            n = int(name)
            return (items[-n] if 1 <= n <= len(items) else None), 1 <= n <= len(items)
        if name == "root":
            return real_root, True
        if name in section.aliases:
            reached, _m = inp.resolve(real_root, section.aliases[name].removeprefix("$"))
            return (reached if reached is not None else UNKNOWN), True
        for i in range(len(labels) - 1, -1, -1):
            if labels[i] == name:
                return items[i], True
        return None, False

    if anchor_match and anchor_match.group(0) == token and token.startswith("@"):
        return Completion(start, _rank(_labels(file, labels), token[1:]))
    if anchor_match:
        anchor = anchor_match.group(0)
        rest = token[len(anchor) :]
        node, known = anchor_node(anchor)
        if known and rest.startswith((".", "[")):
            cut = max(rest.rfind("."), rest.rfind("]"))
            chain, partial = rest[: cut + 1], rest[cut + 1 :]
            if chain.endswith("]"):
                return Completion(cursor, [])  # `a[*]` needs a `.` before a name
            chain = chain.removesuffix(".")
            if chain:
                reached, _missing = inp.resolve(node, chain)
                node = reached if reached is not None else UNKNOWN
            return Completion(cursor - len(partial), _fields(inp, node, partial))
        return Completion(cursor, [])
    if "." in token or "[" in token:
        return Completion(cursor, [])

    # a bare name: where a Source or a condition reads the current element, its fields come
    # first; everywhere, the built-ins and `value`
    partial = token
    found: list[Item] = []
    if column == "source":
        current = items[-1] if items else dollar
        found += _fields(inp, current, "", insert_plain=True)
    if column == "expression":
        found.append(Item("value", "value", "value", "the Source's value"))
        registry = functions if functions is not None else builtin_functions()
        found += [
            Item(f.name, f.name + "(", "function", f.signature(), f.doc, f.origin)
            for f in sorted(registry.values(), key=lambda f: f.name)
        ]
        found += [Item(k, k, "keyword") for k in _KEYWORDS]
    return Completion(start, _rank(found, partial))


def _unclosed_bracket(before: str) -> int | None:
    depth, last, quote = 0, None, ""
    i = 0
    while i < len(before):
        ch = before[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "[":
            depth += 1
            if depth == 1:
                last = i
        elif ch == "]":
            depth -= 1
        i += 1
    return last if depth > 0 else None


def _fields(inp: _Schemas, node: Node, partial: str, insert_plain: bool = False) -> list[Item]:
    items: list[Item] = []
    for name, sub in _properties(inp, node).items():
        detail = _describe(inp, sub)
        insert = name + ("[*]" if detail.startswith("array") and not insert_plain else "")
        items.append(Item(name, insert, "field", detail))
    return _rank(items, partial)


def _labels(file: FunctionalFile, loop_labels: list[str | None]) -> list[Item]:
    found = [Item(".", ".", "label", "the current element")]
    found += [Item(label, label, "label", "loop element") for label in loop_labels if label]
    from transpiler.model import _names_of  # noqa: PLC0415

    lookups, _loops = _names_of(file.rules)
    found += [Item(n, n, "lookup", "lookup table") for n in sorted(lookups)]
    found += [Item(n, n, "alias", file.paths.aliases[n]) for n in file.paths.aliases]
    found += [Item("root", "root", "label", "the document root")]
    found += [Item("index", "index", "label", "position in the loop")]
    return [i for i in found if i.label not in RESERVED_ALIASES or i.label in ("root", "index")]


def _target(before: str, cursor: int, ctx: _Context, out: _Schemas) -> Completion:
    """Names of the output schema's properties, inside the container the rule is in."""
    text = re.sub(r"^[$@]\.?", "", before)
    parts = text.split(".")
    partial = parts[-1]
    node: Node = ctx.out
    for name in parts[:-1]:
        name = name.removesuffix("[*]")
        reached = out.prop(node, name)
        if isinstance(reached, dict) and "array" in out.types(reached):
            reached = out.items(reached)
        node = reached if reached is not None else UNKNOWN
    items: list[Item] = []
    for name, sub in _properties(out, node).items():
        if len(parts) == 1 and name in ctx.taken:
            continue
        detail = _describe(out, sub)
        items.append(Item(name, name, "field", detail))
    return Completion(cursor - len(partial), _rank(items, partial))


_CODE_RUN = re.compile(r"[\w.\[\]*]*$")


def _code(
    before: str,
    cursor: int,
    ctx: _Context,
    inp: _Schemas,
    root: Node,
    functions: dict[str, FunctionInfo] | None,
) -> Completion:
    """The developer dialect of a `code_override`: `root` is the document, `src` the element of
    the innermost loop (`src1` the one around it), `index` / `index1` their positions."""
    token = _CODE_RUN.search(before).group(0)  # type: ignore[union-attr]
    start = cursor - len(token)
    names: dict[str, Node] = {"root": root}
    for offset, node in enumerate(reversed(ctx.items)):
        names["src" if offset == 0 else f"src{offset}"] = node
    if "." in token:
        head, _, tail = token.partition(".")
        base = names.get(head)
        if base is None:
            return Completion(cursor, [])
        cut = tail.rfind(".")
        chain, partial = (tail[:cut], tail[cut + 1 :]) if cut >= 0 else ("", tail)
        if "[" in partial:  # `items[0]` needs a `.` before a name
            return Completion(cursor, [])
        if chain:
            reached, _missing = inp.resolve(base, "." + re.sub(r"\[[^\]]*\]", "[*]", chain))
            base = reached if reached is not None else UNKNOWN
        return Completion(cursor - len(partial), _fields(inp, base, partial, insert_plain=True))
    if "[" in token:
        return Completion(cursor, [])
    # the variables assigned on the lines above
    earlier = before.rpartition("\n")[0]
    local = sorted(
        set(re.findall(r"^\s*([A-Za-z_]\w*)\s*=(?!=)", earlier, flags=re.M)) - set(names)
    )
    # `names` runs from the innermost element out, after `root`
    notes = list(reversed(ctx.notes))
    found = [
        Item(n, n, "label", "the document root" if n == "root" else notes[i - 1])
        for i, n in enumerate(names)
    ]
    found += [Item(n, n, "value", "local variable") for n in local]
    for offset, is_loop in enumerate(reversed(ctx.loops)):
        if is_loop:  # an object that selects an element has no position
            n = "index" if offset == 0 else f"index{offset}"
            found.append(Item(n, n, "label", "position in the loop"))
    registry = functions if functions is not None else builtin_functions()
    found += [
        Item(f.name, f.name + "(", "function", f.signature(), f.doc, f.origin)
        for f in sorted(registry.values(), key=lambda f: f.name)
    ]
    found += [Item("Null", "Null", "keyword", "no value")]
    found += [Item(k, k, "keyword") for k in _KEYWORDS]
    return Completion(start, _rank(found, token))
