"""Stages `build`, `fuse`, `emit` (docs/ARCHITECTURE.md, §Transpiler pipeline).

`build_stage`: id assignment, anchors, expression blocks, `choices` steps ->
the `.map.py` before fusion. `fuse_stage`: the compiler's own
`compiler.loop_fusion` (no reimplementation). `emit_stage`: header and final
touches. Each takes the previous stage's text, so a stage can be re-run from
its on-disk artifact (`transpiler.stages`).

**Shape of the generated code.** One rule function per *output element*:

- a top-level `field` rule -> `def <id>(root) -> T` + `out.<Field> = <id>(root)`;
- an `object` rule -> a `@dataclass` of its members + one function building it
  (a false `guard` is a bare `return`, which omits the object);
- a `loop` rule -> a `@dataclass` of one element + one function building it;
  a top-level loop is a single `for` in the mapping body.

Objects and loops nest. A nested object is a call to the child's function
(`Sub=sub_fn(root, src)`); a nested loop is a list built by a `for` inside the
parent's function (`lines = []` / `for ...: lines.append(child_fn(...))`) and
passed as a field (`Lines=lines`). Children are emitted before their parent
(`def` order is call order).

A failing member is reported under the *outermost* composite rule (one
`out.<Field>.append(...)` per top-level element), since the compiler cannot
isolate members inside a composite. Members there cannot use bare `return` /
`return Null` (a composite has no "omit one member" form): express that with
`coalesce`/`if_else`, or a nested `object` with a `guard`.

**Parameters** (§Generated function parameter naming): every function takes
`root`, then the element of each enclosing loop, outermost first, ending with
its own (`src2, src1, src` — `src` is always the nearest loop's element), then
the positions (`index2, index1, index`) that its subtree actually references.
"""

from __future__ import annotations

import ast
import contextlib
import json
import re
import textwrap
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from compiler.loop_fusion import fuse_loops
from compiler.schema_generator import SchemaTypes
from transpiler.anchors import AnchorScope, LoopRef, resolve_anchors, uses_value
from transpiler.check import _Schemas
from transpiler.expr import COMMENT_MARK, Block, comment_stmt, parse_block
from transpiler.exprtypes import ExprTyper
from transpiler.ids import assign_ids, ident_of, walk
from transpiler.model import (
    CONFLICT_KEY,
    CONFLICT_RESOLUTIONS,
    FieldRule,
    FnYamlError,
    FunctionalFile,
    LookupRule,
    LoopRule,
    ObjectRule,
    Rule,
    is_group,
    load_functional_file,
    prune_unfinished,
)
from transpiler.orderby import OrderKey, parse_order_by
from transpiler.paths import expand_paths
from transpiler.selector import (
    Selection,
    find_selections,
    lower_selectors,
    replace_selections,
    selection_parts,
    selection_text,
)


@dataclass(frozen=True)
class TranspileOptions:
    loop_fusion: bool = True
    parallel_conflict: str = "exception"
    # round | truncate — project defaults, overridden by a rule's `choices`
    format_choice: str = "round"
    multiple_of_choice: str = "round"


def _pascal(name: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Anon"


_OUT_PATH = re.compile(r"^[$@]\.(?P<name>[A-Za-z_]\w*)(?:\[\*?\])?$")
_ATTR_CHAIN = re.compile(r'^[A-Za-z_]\w*((\.[A-Za-z_]\w*|\["[A-Za-z_]\w*"\])(\[\d+\])*)*$')
_INDEX_NAME = re.compile(r"^index(\d*)$")


def _output_field(path: str, where: str) -> str:
    m = _OUT_PATH.match(path.strip())
    if not m:
        raise FnYamlError(
            f"{where}: output path {path!r} must be one field of the enclosing element "
            "('$.Orders[*]' at top level, '@.Lines[*]' / '@.Discount' inside a loop or object) — "
            "nest rules instead of writing a deeper path"
        )
    return m.group("name")


def _annotation(base: str, nullable: bool, null_sentinel: bool) -> str:
    return " | ".join([base, *(["None"] if nullable else []), *(["Null"] if null_sentinel else [])])


def _decimals(fmt: str) -> int:
    return len(fmt.split(".", 1)[1]) if "." in fmt else 0


class _CollapseDoubleNot(ast.NodeTransformer):
    """`if not not X:` -> `if X:` (test position only, where it's truthiness).
    Fusion turns the `if not (F): continue` filter idiom into `if not (not F)`."""

    def visit_If(self, node: ast.If) -> ast.If:
        self.generic_visit(node)
        t = node.test
        while (
            isinstance(t, ast.UnaryOp)
            and isinstance(t.op, ast.Not)
            and isinstance(t.operand, ast.UnaryOp)
            and isinstance(t.operand.op, ast.Not)
        ):
            t = t.operand.operand
        node.test = t
        return node


def _render(module: ast.Module) -> str:
    text = ast.unparse(module)
    quote = "(?:'''|\"\"\"|'|\")"
    return re.sub(
        rf"^(\s*){quote}{re.escape(COMMENT_MARK)}(.*?){quote}$", r"\1# \2", text, flags=re.M
    )


class _PostProcess(ast.NodeTransformer):
    """Apply the post-processing steps to every returned value, each explained by
    a comment line above the `return`: the `.map.py` is what the developer reads."""

    def __init__(self, steps: list[tuple[str, str, Callable[[ast.expr], ast.expr]]]):
        self.steps = steps  # (kind, comment, wrap)

    def visit_Return(self, node: ast.Return) -> list[ast.stmt]:
        v = node.value
        if v is None or (isinstance(v, ast.Name) and v.id == "Null"):
            return [node]
        for _kind, _text, wrap in self.steps:
            v = wrap(v)
        notes = [comment_stmt(text) for _kind, text, _wrap in self.steps]
        return [*notes, ast.copy_location(ast.Return(value=v), node)]


def _call(func: str, *args: ast.expr) -> ast.expr:
    return ast.Call(func=ast.Name(id=func, ctx=ast.Load()), args=list(args), keywords=[])


def _decimals_of(number: Any) -> int:
    exp = Decimal(str(number)).normalize().as_tuple().exponent
    return max(0, -exp) if isinstance(exp, int) else 0


def _index_offsets(nodes: Sequence[ast.AST]) -> set[int]:
    """Which of `index`, `index1`, ... the code reads (0 = nearest loop)."""
    found: set[int] = set()
    for node in nodes:
        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                m = _INDEX_NAME.match(n.id)
                if m:
                    found.add(int(m.group(1) or 0))
    return found


@dataclass
class _Picks:
    """The selections of one block of text: `(list path, condition)` -> (variable, the line
    that assigns it). `emit` False builds the lines of a proposal, which make no function."""

    emit: bool = True
    lines: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)

    def prefix(self, text: str) -> str:
        """`text` under the assignments of its selections."""
        if not self.lines:
            return text
        body = textwrap.dedent(text).strip("\n")
        return "\n".join([*(line for _, line in self.lines.values()), body])


@dataclass(frozen=True)
class _Frame:
    """The loops enclosing a rule, outermost first, with each element's schema
    type name (None = untyped / no schema)."""

    labels: tuple[str | None, ...] = ()
    types: tuple[str | None, ...] = ()
    # each loop's source as an absolute path (`$.orders[*].lines[*]`), for a field's Source
    sources: tuple[str, ...] = ()

    @property
    def depth(self) -> int:
        return len(self.labels)

    @staticmethod
    def item_name(offset: int) -> str:
        return "src" if offset == 0 else f"src{offset}"

    @staticmethod
    def index_name(offset: int) -> str:
        return "index" if offset == 0 else f"index{offset}"

    def item_names(self) -> list[str]:
        return [self.item_name(o) for o in range(self.depth - 1, -1, -1)]

    def loop_refs(self) -> tuple[LoopRef, ...]:
        return tuple(
            LoopRef(label, self.item_name(self.depth - 1 - i), self.index_name(self.depth - 1 - i))
            for i, label in enumerate(self.labels)
        )

    def child(self, label: str | None, type_name: str | None, source: str = "") -> _Frame:
        raw = source.strip().replace("[]", "[*]")
        if raw.startswith("@.") and self.sources:
            raw = self.sources[-1] + raw[1:]
        return _Frame((*self.labels, label), (*self.types, type_name), (*self.sources, raw))


@dataclass
class _Composite:
    ident: str
    cls: str
    needs: set[int]  # index offsets (in the composite's own frame) its function takes


def _order_kind(text: str) -> str | None:
    """How the values of an order key compare: `number` or `str`, from what the expression
    produces (the result of a function, an operator, a literal); None when that is not known."""
    try:
        node = ast.parse(text.strip(), mode="eval").body
    except SyntaxError:
        return None
    if isinstance(node, ast.BinOp) and (
        not isinstance(node.op, ast.Add)
        or any(
            isinstance(n, ast.Constant) and isinstance(n.value, int | float)
            for n in (node.left, node.right)
        )
    ):
        return "number"  # arithmetic: a sum of a text and a number is not one
    found = ExprTyper(None, {}, lambda message: None).infer(node)
    if found and found <= {"number", "integer"}:
        return "number"
    if found and found <= {"string"}:
        return "str"
    return None


class _Builder:
    def __init__(
        self,
        file: FunctionalFile,
        options: TranspileOptions,
        schema: SchemaTypes | None,
        output_schema: dict[str, Any] | None = None,
    ):
        self.file = file
        self.opt = options
        self.warnings: list[str] = []
        self.schema = schema
        # the output JSON Schema, to know what it requires (a list is left out when empty unless it does)
        self.out_schema = _Schemas(output_schema) if output_schema is not None else None
        self._out: list[Any] = [output_schema if output_schema is not None else None]
        self._top_lists: set[tuple[int, str]] = set()  # (rules of a level, list) already written
        self._level: list[Any] = file.rules  # the rules written straight into the output root here
        self.lookups: dict[str, dict] = {}
        self.classes: list[ast.stmt] = []
        self.class_fields: dict[str, list[tuple[str, str]]] = {}  # name -> (field, annotation)s
        self.functions: list[ast.stmt] = []
        self.flow: list[ast.stmt] = []
        self._class_names: set[str] = set()
        # the functions picking the first element of a list by a condition, once each
        self._pickers: dict[tuple[str, str, _Frame], tuple[str, set[int]]] = {}
        self._picker_names: set[str] = set()
        self.validation_directive: str | None = None  # `__validation__`, when the file validates
        self.proposals: dict[str, str] = {}  # fq id -> auto code, of every field rule
        self.proposal_errors: dict[str, str] = {}

    # -- helpers -----------------------------------------------------------

    def _unique_class(self, base: str) -> str:
        name, n = base, 2
        while name in self._class_names:
            name = f"{base}{n}"
            n += 1
        self._class_names.add(name)
        return name

    @staticmethod
    def _stmts(src: str) -> list[ast.stmt]:
        return ast.parse(src).body

    def _scope(self, frame: _Frame) -> AnchorScope:
        return AnchorScope(loops=frame.loop_refs(), lookups=self.lookups)

    @contextlib.contextmanager
    def _inside(self, out_field: str, is_list: bool) -> Iterator[None]:
        """The output schema node of what is being built, while its rules are written: the
        container `out_field` of the current one, or the element of the list it is."""
        node: Any = None
        if self.out_schema is not None:
            here = self._out[-1]
            node = self.out_schema.prop(here, out_field) if here is not None else None
            if is_list and node is not None:
                node = self.out_schema.items(node)
        self._out.append(node)
        try:
            yield
        finally:
            self._out.pop()

    def _omits_when_empty(self, rule: LoopRule, out_field: str) -> bool:
        """Whether the list of a loop is left out when no element passed: as the rule says, else
        when the output schema does not require it (with no schema, it is written empty)."""
        if rule.when_empty is not None:
            return rule.when_empty == "omit"
        here = self._out[-1]
        if self.out_schema is None or not isinstance(here, dict):
            return False
        return out_field not in self.out_schema.required(here)

    def _post_steps(
        self, rule: FieldRule, where: str
    ) -> list[tuple[str, str, Callable[[ast.expr], ast.expr]]]:
        """Post-processing steps appended after the declared transform, in order:
        `allowed.multipleOf` snapping, then `format` decimals. Each is decided by
        the rule's `choices`, else the project default."""
        steps: list[tuple[str, str, Callable[[ast.expr], ast.expr]]] = []
        multiple = (rule.allowed or {}).get("multipleOf")
        if multiple is not None:
            if (
                isinstance(multiple, bool)
                or not isinstance(multiple, (int, float))
                or multiple == 0
            ):
                raise FnYamlError(
                    f"{where}: allowed.multipleOf must be a non-zero number — got {multiple!r}"
                )
            if rule.type not in ("number", "int"):
                raise FnYamlError(
                    f"{where}: allowed.multipleOf applies to number/int fields only "
                    f"(this one is {rule.type})"
                )
            if multiple < 0:
                self.warnings.append(
                    f"{where}: allowed.multipleOf {multiple} is negative; a multiple has no "
                    f"sign, using {abs(multiple)}"
                )
                multiple = abs(multiple)
        c = rule.choices
        if c.multiple_of is not None and multiple is None:
            self.warnings.append(f"{where}: choices.multipleOf has no allowed.multipleOf to act on")
        if c.format is not None and not (rule.type == "number" and rule.format):
            self.warnings.append(f"{where}: choices.format has no format to act on")
        if c.conflicts and not (multiple is not None and rule.format):
            self.warnings.append(
                f"{where}: choices.conflicts has no format + allowed.multipleOf pair to act on"
            )
        do_multiple = multiple is not None
        do_format = rule.type == "number" and rule.format is not None
        if do_multiple and do_format:
            assert rule.format is not None
            if _decimals_of(multiple) > _decimals(rule.format):
                resolution = rule.choices.conflicts.get(CONFLICT_KEY)
                if resolution is None:
                    raise FnYamlError(
                        f"{where}: format {rule.format!r} ({_decimals(rule.format)} decimals) "
                        f"conflicts with allowed.multipleOf {multiple} — the format step would "
                        "break the multiple; decide with "
                        f"choices.conflicts.{CONFLICT_KEY}: {' | '.join(CONFLICT_RESOLUTIONS)}"
                    )
                do_multiple = resolution in ("both", "multipleOf_only")
                do_format = resolution in ("both", "format_only")
        if do_multiple:
            mode = rule.choices.multiple_of or self.opt.multiple_of_choice
            fn = "round" if mode == "round" else "trunc"
            step = ast.Constant(value=multiple)

            def snap(v: ast.expr, fn: str = fn, step: ast.Constant = step) -> ast.expr:
                div = ast.BinOp(left=v, op=ast.Div(), right=step)
                return ast.BinOp(
                    left=_call(fn, div, ast.Constant(value=0)), op=ast.Mult(), right=step
                )

            steps.append(
                (
                    "multipleOf",
                    f"{rule.field}: multipleOf {multiple} (choices.multipleOf = {mode})",
                    snap,
                )
            )
        if do_format:
            assert rule.format is not None
            mode = rule.choices.format or self.opt.format_choice
            fn, digits = ("round" if mode == "round" else "trunc"), _decimals(rule.format)
            steps.append(
                (
                    "format",
                    f"{rule.field}: format {rule.format!r} (choices.format = {mode})",
                    lambda v, fn=fn, digits=digits: _call(fn, v, ast.Constant(value=digits)),
                )
            )
        return steps

    def _picker(self, sel: Selection, frame: _Frame, where: str) -> tuple[str, set[int]]:
        """The function that gives the first element of the list `sel.path` for which the
        condition holds (an empty object when none does, so that reading it gives nothing):
        its name and the positions it takes. One per list and condition; the condition reads
        the candidate as `@` and the loops around the rule as `@2`..."""
        condition, order = selection_parts(sel.condition)
        key = (sel.path, selection_text(condition, order), frame)
        if key in self._pickers:
            return self._pickers[key]
        if find_selections(condition):
            raise FnYamlError(f"{where}: a condition cannot hold another selection")
        list_text = resolve_anchors(sel.path, self._scope(frame), f"{where} selection").text
        if not _ATTR_CHAIN.match(list_text):
            raise FnYamlError(f"{where}: unsupported path {sel.path!r} before a condition")
        base = list_text.rsplit(".", 1)[-1]
        ident, n = f"pick_{base}", 2
        while ident in self._picker_names or ident in self._class_names:
            ident, n = f"pick_{base}{n}", n + 1
        self._picker_names.add(ident)
        item, index = f"{ident}_src", f"{ident}_index"
        scope = AnchorScope(
            loops=(*frame.loop_refs(), LoopRef(None, item, index)), lookups=self.lookups
        )
        resolved = resolve_anchors(condition or "True", scope, f"{where} condition")
        if resolved.uses_index:
            raise FnYamlError(f"{where}: a condition cannot reference @index")
        ordered = self._order_iterable(list_text, order, None, scope, f"{where} selection")
        found = f"{ident}_found"
        body = self._stmts(
            f"{found} = []\n"
            f"for {item} in {ordered}:\n"
            f"    if not ({resolved.text}):\n"
            f"        continue\n"
            f"    {found}.append({item})\n"
            f"if {found}:\n"
            f"    return {found}[0]\n"
            f"return {{}}"
        )
        needs = _index_offsets(body)
        fn = ast.parse(f"def {ident}({self._params(frame, needs)}) -> Any:\n    pass").body[0]
        assert isinstance(fn, ast.FunctionDef)
        fn.body = body
        ast.fix_missing_locations(fn)
        self.functions.append(fn)
        self._pickers[key] = (ident, needs)
        return ident, needs

    def _extract(self, text: str, frame: _Frame, where: str, picks: _Picks) -> str:
        """`text` with each selection (`$.items[marker = 'T'].qty`) replaced by a variable
        (`items_pick.qty`) that `picks` assigns: the first element is looked for once, however
        often it is read."""

        def variable(sel: Selection) -> str:
            condition = selection_text(*selection_parts(sel.condition))
            key = (sel.path, condition)
            if key not in picks.lines:
                base = re.sub(r"\W+", "_", sel.path.rsplit(".", 1)[-1]).strip("_") or "root"
                var, n = f"{base}_pick", 2
                while var in {v for v, _ in picks.lines.values()}:
                    var, n = f"{base}_pick{n}", n + 1
                if picks.emit:
                    ident, needs = self._picker(sel, frame, where)
                    names = [
                        a.id for a in self._call_args(frame, None, needs) if isinstance(a, ast.Name)
                    ]
                    picks.lines[key] = (var, f"{var} = {ident}({', '.join(names)})")
                else:
                    # only what it means, for the proposal: no function is made for it
                    picks.lines[key] = (var, f"{var} = pick({sel.path!r}, {condition!r})")
            return picks.lines[key][0]

        return replace_selections(text, variable)

    def _value_text(
        self,
        rule: FieldRule,
        frame: _Frame,
        scope: AnchorScope,
        where: str,
        picks: _Picks,
    ) -> str | None:
        """The Source of a field as Python text: what the name `value` stands for. A path
        that goes through an enclosing loop (`$.items[*].sku`) is rewritten to that loop's
        element (`@.sku`)."""
        if rule.has_constant:
            constant = rule.source_constant
            negative = isinstance(constant, int | float) and constant < 0
            return f"({constant!r})" if negative else repr(constant)
        path = (rule.source_path or "").strip().replace("[]", "[*]")
        if not path:
            return None
        if "[*]" in path:
            for depth in range(frame.depth, 0, -1):
                prefix = frame.sources[depth - 1]
                if path == prefix or path.startswith(prefix + "."):
                    anchor = "@" if depth == frame.depth else f"@{frame.depth - depth + 1}"
                    path = anchor + path[len(prefix) :]
                    break
            if "[*]" in path:
                raise FnYamlError(
                    f"{where}: the source {rule.source_path!r} does not go through an enclosing "
                    "loop: write it relative to the loop (@.name) to use it as `value`"
                )
        path = self._extract(path, frame, where, picks)
        return resolve_anchors(path, scope, f"{where} source").text

    def _auto_text(
        self, rule: FieldRule, scope: AnchorScope, frame: _Frame, where: str, emit: bool = True
    ) -> str:
        """What the transpiler generates from the rule's Source and expression, as developer
        dialect text (anchors resolved), whatever the rule's status. A selection in them
        (`$.items[marker = 'T'].qty`) is a variable assigned on the first lines. With `emit`
        False nothing is added to the module (the text is only a proposal)."""
        t = rule.transform
        picks = _Picks(emit)
        value = self._value_text(rule, frame, scope, where, picks)
        expression = t.expression or "value"  # no expression: the Source's value as it is
        if re.search(r"(?<![\w.])value\s*=(?!=)", expression):
            raise FnYamlError(f"{where}: `value` is reserved (the rule's Source value)")
        if value is None and uses_value(expression):
            raise FnYamlError(f"{where}: the expression uses `value` but the rule has no Source")
        expression = self._extract(expression, frame, where, picks)
        return picks.prefix(resolve_anchors(expression, scope, where, value).text)

    def _propose(
        self, rule: FieldRule, fq: str, scope: AnchorScope, frame: _Frame, where: str
    ) -> None:
        """What the transpiler would generate now for a field rule, whatever its status
        (`self.proposals`), normalised so that only a change in meaning shows."""
        try:
            text = self._auto_text(rule, scope, frame, where, emit=False)
            self.proposals[fq] = ast.unparse(ast.parse(textwrap.dedent(text).strip("\n")))
        except (FnYamlError, SyntaxError) as exc:
            self.proposal_errors[fq] = str(exc)

    def _field_block(self, rule: FieldRule, fq: str, scope: AnchorScope, frame: _Frame) -> Block:
        where = f"rule '{fq}'"
        t = rule.transform
        self._propose(rule, fq, scope, frame, where)
        if t.status == "manual":
            assert t.code_override is not None
            text = t.code_override
        else:
            text = self._auto_text(rule, scope, frame, where)
        block = parse_block(text, ident_of(fq), where)
        steps = self._post_steps(rule, where)
        if steps:
            post = _PostProcess(steps)
            stmts: list[ast.stmt] = []
            for s in block.stmts:
                out = post.visit(s)
                stmts.extend(out if isinstance(out, list) else [out])
            block = Block(stmts, block.returns_null, block.can_omit)
            for s in block.stmts:
                ast.fix_missing_locations(s)
        return block

    def _walk_type(self, start: str | None, segs: list[str]) -> str | None:
        """Type expression reached from class `start` via attribute `segs`."""
        if self.schema is None or start is None:
            return None
        type_expr = start
        for seg in segs:
            parts = [p.strip() for p in type_expr.split("|") if p.strip() not in ("None", "Null")]
            cls = self.schema.classes.get(parts[0]) if len(parts) == 1 else None
            fld = next((f for f in cls.fields if f.name == seg), None) if cls else None
            if fld is None:
                return None
            type_expr = fld.type_expr
        parts = [p.strip() for p in type_expr.split("|") if p.strip() not in ("None", "Null")]
        return parts[0] if len(parts) == 1 else None

    def _element_type(self, source_text: str, frame: _Frame) -> str | None:
        """Element type of the array at `root.a.b` / `src.items` (a resolved path)."""
        names: dict[str, str | None] = {"root": self.schema.root_type if self.schema else None}
        for off in range(frame.depth):
            names[frame.item_name(off)] = frame.types[frame.depth - 1 - off]
        first, *segs = source_text.split(".")
        t = self._walk_type(names.get(first), segs)
        if t and t.startswith("list[") and t.endswith("]"):
            return t[5:-1]
        return None

    def _params(self, frame: _Frame, needs: set[int]) -> str:
        root_t = self.schema.root_type if self.schema else "Any"
        parts = [f"root: {root_t}"]
        for off in range(frame.depth - 1, -1, -1):
            parts.append(f"{frame.item_name(off)}: {frame.types[frame.depth - 1 - off] or 'Any'}")
        parts += [f"{frame.index_name(o)}: int" for o in sorted(needs, reverse=True)]
        return ", ".join(parts)

    def _make_class(self, base: str, fields: list[tuple[str, str]]) -> str:
        name = self._unique_class(base)
        self.class_fields[name] = list(fields)
        body = "\n".join(f"    {n}: {a}" for n, a in fields)
        self.classes += self._stmts(f"@dataclass\nclass {name}:\n{body}")
        return name

    # -- rules -------------------------------------------------------------

    def build(self) -> None:
        for label, shared in self.file.shared.items():
            self.lookups[label] = dict(shared.entries)
        for _fq, rule in walk(self.file.rules):
            if isinstance(rule, LookupRule):
                if rule.label in self.file.shared:
                    raise FnYamlError(
                        f"lookup '{rule.label}' is also a project-wide lookup: remove the one in the mapping"
                    )
                self.lookups[rule.label] = dict(rule.entries)
        labels = [
            r.label for _fq, r in walk(self.file.rules) if isinstance(r, LoopRule) and r.label
        ]
        clash = sorted(set(labels) & set(self.lookups))
        if clash:
            raise FnYamlError(f"label(s) used by both a loop and a lookup: {', '.join(clash)}")

        for rule in self.file.rules:
            assert rule.id is not None
            self._top(rule, rule.id)
        self._checks()

    def _checks(self) -> None:
        """The extra validations: each `expect` becomes a function of the document that must be
        true (`$` is the input for the input side and the output for the output side), and the
        directive that lists them for the compiler (compiler/validation.py)."""
        directive: dict[str, Any] = {}
        for side in ("input", "output"):
            spec = self.file.validations.side(side)
            checks: list[dict[str, str]] = []
            for check in spec.checks:
                ident = f"check_{side}_{check.id}"
                where = f"validation '{check.id}'"
                frame = _Frame()
                picks = _Picks()
                text = self._extract(check.expect, frame, where, picks)
                block = parse_block(
                    picks.prefix(resolve_anchors(text, self._scope(frame), where).text),
                    ident,
                    where,
                )
                fn = ast.parse(f"def {ident}(root: Any) -> bool:\n    pass").body[0]
                assert isinstance(fn, ast.FunctionDef)
                fn.body = block.stmts
                self.functions.append(fn)
                checks.append(
                    {
                        "fn": ident,
                        "code": check.code,
                        "message": check.message,
                        "action": check.action,
                    }
                )
            if spec.schema or checks:
                directive[side] = {"schema": spec.schema, "checks": checks}
        if directive:
            self.validation_directive = json.dumps(directive, separators=(",", ":"))

    def _top(self, rule: Rule, fq: str) -> None:
        """One rule written straight into the output root (`fq` is its qualified id)."""
        if isinstance(rule, LookupRule):
            return
        if isinstance(rule, FieldRule):
            self._top_field(rule, fq)
        elif isinstance(rule, ObjectRule) and is_group(rule):
            self._top_group(rule, fq)
        elif isinstance(rule, ObjectRule):
            self._top_object(rule, fq)
        elif rule.first:
            self._top_first(rule, fq)
        elif self._top_omitting(rule):
            self._top_list(rule, fq)
        else:
            self._top_loop(rule, fq)

    def _top_omitting(self, rule: LoopRule) -> bool:
        """Whether a top-level loop writes a list that is left out when empty."""
        out_field = _output_field(rule.output, f"rule '{rule.id}'")
        return self._omits_when_empty(rule, out_field)

    def _top_list(self, rule: LoopRule, fq: str) -> None:
        """A top-level list that is left out when empty: one function builds it (the loops that
        write it, in the order of the rules) and returns it, or nothing when no element passed."""
        out_field = _output_field(rule.output, f"rule '{fq}'")
        if (id(self._level), out_field) in self._top_lists:
            return  # the loops of this list were all written with the first
        self._top_lists.add((id(self._level), out_field))
        stmts: list[ast.stmt] = []
        into: tuple[str, str] | None = None
        list_var = ""
        for other in self._level:
            if (
                isinstance(other, LoopRule)
                and not other.first
                and _output_field(other.output, "") == out_field
            ):
                assert other.id is not None
                with self._inside(out_field, True):
                    more, list_var, sub = self._nested_loop(
                        other, other.id, _Frame(), f"rule '{other.id}'", into=into
                    )
                stmts += more
                into = into or (list_var, sub.cls)
        assert into is not None
        body = [*stmts, *self._stmts(f"if {list_var}:\n    return {list_var}\nreturn")]
        ident = f"{ident_of(fq)}_all"
        fn = ast.parse(f"def {ident}(root: Any) -> list[{into[1]}] | None:\n    pass").body[0]
        assert isinstance(fn, ast.FunctionDef)
        fn.body = body
        ast.fix_missing_locations(fn)
        self.functions.append(fn)
        self.flow += self._stmts(f"out.{out_field} = {ident}(root)")

    def _top_group(self, rule: ObjectRule, fq: str) -> None:
        """`output: $`: a group of rules that write into the root, all of them or none (its
        `guard`). The mapping has no notion of alternative shapes: whoever writes it guards the
        rules of each shape, and the rules of the other shapes are not run."""
        start = len(self.flow)
        outer, self._level = self._level, rule.rules
        for child in rule.rules:
            assert child.id is not None
            self._top(child, f"{fq}.{child.id}")
        self._level = outer
        body = self.flow[start:] or self._stmts("pass")
        del self.flow[start:]
        if not rule.guard:
            self.flow += body
            return
        where = f"rule '{fq}' guard"
        picks = _Picks()
        text = self._extract(rule.guard, _Frame(), where, picks)
        g = parse_block(
            picks.prefix(resolve_anchors(text, self._scope(_Frame()), where).text),
            f"{ident_of(fq)}_guard",
            where,
        )
        if not g.is_simple or g.pre:
            raise FnYamlError(f"{where}: must be a single boolean expression")
        self.flow.append(ast.If(test=g.value, body=body, orelse=[]))

    def _top_field(self, rule: FieldRule, fq: str) -> None:
        ident = ident_of(fq)
        block = self._field_block(rule, fq, self._scope(_Frame()), _Frame())
        ret = _annotation(rule.type, not rule.required, block.returns_null)
        fn = ast.parse(f"def {ident}({self._params(_Frame(), set())}) -> {ret}:\n    pass").body[0]
        assert isinstance(fn, ast.FunctionDef)
        fn.body = block.stmts
        self.functions.append(fn)
        self.flow += self._stmts(f"out.{rule.field} = {ident}(root)")

    def _top_object(self, rule: ObjectRule, fq: str) -> None:
        out_field = _output_field(rule.output, f"rule '{fq}'")
        with self._inside(out_field, False):
            comp = self._composite(rule, fq, _Frame(), _pascal(out_field), rule.guard)
        self.flow += self._stmts(f"out.{out_field} = {comp.ident}(root)")

    def _top_first(self, rule: LoopRule, fq: str) -> None:
        where = f"rule '{fq}'"
        out_field = _output_field(rule.output, where)
        with self._inside(out_field, False):
            wrapper = self._first_match(rule, fq, _Frame(), where)
        self.flow += self._stmts(f"out.{out_field} = {wrapper.ident}(root)")

    def _first_match(self, rule: LoopRule, fq: str, frame: _Frame, where: str) -> _Composite:
        """A selecting object: a function that loops over the list like a loop rule, keeping the
        elements that satisfy the condition, and returns the first one's object (nothing, so
        the object is omitted, when none does)."""
        stmts, list_var, sub = self._nested_loop(rule, fq, frame, where)
        body: list[ast.stmt] = [
            *stmts,
            *self._stmts(f"if {list_var}:\n    return {list_var}[0]\nreturn"),
        ]
        ident = f"{ident_of(fq)}_first"
        needs = _index_offsets(body)
        fn = ast.parse(
            f"def {ident}({self._params(frame, needs)}) -> {sub.cls} | None:\n    pass"
        ).body[0]
        assert isinstance(fn, ast.FunctionDef)
        fn.body = body
        ast.fix_missing_locations(fn)
        self.functions.append(fn)
        return _Composite(ident, sub.cls, needs)

    def _top_loop(self, rule: LoopRule, fq: str) -> None:
        where = f"rule '{fq}'"
        out_field = _output_field(rule.output, where)
        source = self._source_text(rule, self._scope(_Frame()), where)
        frame = _Frame().child(rule.label, self._element_type(source, _Frame()), rule.source)
        with self._inside(out_field, True):
            comp = self._composite(rule, fq, frame, _pascal(out_field) + "Item", None)
        uses_index = 0 in comp.needs
        scope = self._scope(frame)
        iterable, filter_text = self._iterable(rule, source, "src", scope, uses_index, where)
        target = "index, src" if uses_index else "src"
        args = "root, src" + (", index" if uses_index else "")
        loop = self._stmts(
            f"for {target} in {iterable}:\n    out.{out_field}.append({comp.ident}({args}))"
        )[0]
        assert isinstance(loop, ast.For)
        if filter_text and not uses_index:
            loop.body.insert(0, self._stmts(f"if not ({filter_text}):\n    continue")[0])
        ast.fix_missing_locations(loop)
        self.flow.append(loop)

    def _source_text(self, rule: LoopRule, scope: AnchorScope, where: str) -> str:
        path = re.sub(r"\[\*?\]$", "", rule.source.strip())
        text = resolve_anchors(path, scope, f"{where} source").text
        if not _ATTR_CHAIN.match(text):
            raise FnYamlError(f"{where}: unsupported source path {rule.source!r}")
        return text

    def _ordered(self, iterable: str, rule: LoopRule, scope: AnchorScope, where: str) -> str:
        """`iterable` ordered by the loop's `order_by`."""
        return self._order_iterable(
            iterable, parse_order_by(rule.order_by or ""), rule.label, scope, where
        )

    def _order_iterable(
        self,
        iterable: str,
        keys: list[OrderKey],
        label: str | None,
        scope: AnchorScope,
        where: str,
    ) -> str:
        """`iterable` inside the `sorted(...)` calls of `keys`: one per key, the last key innermost
        (the sort is stable, so the first decides and the next breaks its ties)."""
        field_of = re.escape(label or "")
        for key in reversed(keys):
            options = (", reverse=True" if key.desc else "") + (
                ", nulls='first'" if key.nulls_first else ""
            )
            field = re.match(rf"^@(?:{field_of})?\.(\w+)$", key.expr.strip())
            if field:
                iterable = f"sorted({iterable}, key={field.group(1)!r}{options})"
                continue
            if find_selections(key.expr):
                raise FnYamlError(
                    f"{where}: an order key cannot hold a selection (a path with a condition in it)"
                )
            resolved = resolve_anchors(key.expr, scope, f"{where} order by")
            if resolved.uses_index:
                raise FnYamlError(f"{where}: an order key cannot reference @index")
            kind = _order_kind(resolved.text)
            if kind is None:
                raise FnYamlError(
                    f"{where}: the type of the order key '{key.expr}' is not known: make it a number "
                    "with to_number(...) or a text with to_string(...), or order by a field of the element"
                )
            iterable = f"sorted({iterable}, by={resolved.text}, kind={kind!r}{options})"
        return iterable

    def _iterable(
        self,
        rule: LoopRule,
        source: str,
        item: str,
        scope: AnchorScope,
        uses_index: bool,
        where: str,
    ) -> tuple[str, str | None]:
        """The `for` iterable text, and the filter (None when folded into it).
        `scope` names the loop's own element/index as they appear where the
        `for` is written."""
        iterable = source
        if rule.order_by:
            iterable = self._ordered(iterable, rule, scope, where)
        filter_text = None
        if rule.filter:
            if find_selections(rule.filter):
                raise FnYamlError(
                    f"{where}: a filter cannot hold a selection (a path with a condition in it): "
                    "read it in the fields of the loop"
                )
            f = resolve_anchors(rule.filter, scope, f"{where} filter")
            if f.uses_index:
                raise FnYamlError(f"{where}: filter cannot reference @index")
            filter_text = f.text
        if uses_index:
            # The index numbers the elements that pass the filter, so the filter must
            # come *before* enumerate(): in real Python a `continue` in the body would
            # leave gaps. The compiler lowers this form (per-branch counter when fused).
            if filter_text:
                iterable = f"[{item} for {item} in {iterable} if {filter_text}]"
                filter_text = None
            start = f", start={rule.index_start}" if rule.index_start else ""
            iterable = f"enumerate({iterable}{start})"
        return iterable, filter_text

    # -- composites (object / loop element) --------------------------------

    def _composite(
        self,
        node: ObjectRule | LoopRule,
        fq: str,
        frame: _Frame,
        cls_base: str,
        guard: str | None,
        reuse: str | None = None,
    ) -> _Composite:
        """Emit the dataclass + function for one object/loop element, children
        first. `frame` is the element's own frame (a loop's includes itself)."""
        ident = ident_of(fq)
        scope = self._scope(frame)
        pre: list[ast.stmt] = []
        kwargs: list[ast.keyword] = []
        fields: list[tuple[str, str]] = []
        seen: set[str] = set()
        # output list -> (its variable, its element class): loops may add to one, in order
        lists: dict[str, tuple[str, str]] = {}

        def add(name: str, annotation: str, value: ast.expr, where: str) -> None:
            if name in seen:
                raise FnYamlError(f"{where}: duplicate output field '{name}'")
            seen.add(name)
            kwargs.append(ast.keyword(arg=name, value=value))
            fields.append((name, annotation))

        for child in node.rules:
            assert child.id is not None
            cfq = f"{fq}.{child.id}"
            where = f"rule '{cfq}'"
            if isinstance(child, LookupRule):
                continue
            if isinstance(child, FieldRule):
                block = self._field_block(child, cfq, scope, frame)
                if not block.is_simple:
                    raise FnYamlError(
                        f"{where}: inside a {node.kind} a field must be assignments followed by "
                        "one value (no if/return/Null) — use if_else()/coalesce() instead"
                    )
                pre += block.pre
                add(
                    child.field,
                    _annotation(child.type, not child.required, False),
                    block.value,
                    where,
                )
            elif isinstance(child, ObjectRule):
                out_field = _output_field(child.output, where)
                with self._inside(out_field, False):
                    sub = self._composite(child, cfq, frame, _pascal(out_field), child.guard)
                call = ast.Call(
                    func=ast.Name(id=sub.ident, ctx=ast.Load()),
                    args=self._call_args(frame, None, sub.needs),
                    keywords=[],
                )
                add(out_field, sub.cls + (" | None" if child.guard else ""), call, where)
            elif child.first:
                out_field = _output_field(child.output, where)
                with self._inside(out_field, False):
                    wrapper = self._first_match(child, cfq, frame, where)
                call = ast.Call(
                    func=ast.Name(id=wrapper.ident, ctx=ast.Load()),
                    args=self._call_args(frame, None, wrapper.needs),
                    keywords=[],
                )
                add(out_field, f"{wrapper.cls} | None", call, where)
            else:
                out_field = _output_field(child.output, where)
                omit = self._omits_when_empty(child, out_field)
                with self._inside(out_field, True):
                    stmts, list_var, sub = self._nested_loop(
                        child, cfq, frame, where, into=lists.get(out_field)
                    )
                pre += stmts
                if out_field not in lists:
                    lists[out_field] = (list_var, sub.cls)
                    value: ast.expr = ast.Name(id=list_var, ctx=ast.Load())
                    annotation = f"list[{sub.cls}]"
                    if omit:  # nothing to list: the field is left out
                        value = ast.IfExp(
                            test=ast.Name(id=list_var, ctx=ast.Load()),
                            body=ast.Name(id=list_var, ctx=ast.Load()),
                            orelse=ast.Constant(value=None),
                        )
                        annotation += " | None"
                    add(out_field, annotation, value, where)

        if not fields:
            raise FnYamlError(f"rule '{fq}': a {node.kind} rule needs at least one member")

        # a loop adding to a list another loop started has that loop's element class when the
        # elements have the same fields (the compiler compares the list's class)
        if reuse and self.class_fields.get(reuse) == fields:
            cls = reuse
        else:
            cls = self._make_class(cls_base, fields)
        build: list[ast.stmt] = [
            *pre,
            ast.Return(value=ast.Call(func=ast.Name(cls, ast.Load()), args=[], keywords=kwargs)),
        ]
        body = build
        if guard:
            picks = _Picks()
            guard_text = self._extract(guard, frame, f"rule '{fq}' guard", picks)
            g = parse_block(
                picks.prefix(resolve_anchors(guard_text, scope, f"rule '{fq}' guard").text),
                f"{ident}_guard",
                f"rule '{fq}' guard",
            )
            if not g.is_simple:
                raise FnYamlError(f"rule '{fq}': guard must be a single boolean expression")
            # `if <guard>: build else: return` — not `if not <guard>: return`: a NULL
            # guard (missing field) must omit the object, and in SQL `NOT NULL` is
            # NULL, so the negated form would fall through and build it.
            body = [*g.pre, ast.If(test=g.value, body=build, orelse=[ast.Return(value=None)])]

        needs = _index_offsets(body)
        fn = ast.parse(
            f"def {ident}({self._params(frame, needs)}) -> {cls}{' | None' if guard else ''}:\n    pass"
        ).body[0]
        assert isinstance(fn, ast.FunctionDef)
        fn.body = body
        if isinstance(node, LoopRule) and node.parallel is not None:
            fn.decorator_list = [ast.parse(f"parallel(degree={node.parallel})", mode="eval").body]
        ast.fix_missing_locations(fn)
        self.functions.append(fn)
        return _Composite(ident, cls, needs)

    def _call_args(
        self, frame: _Frame, loop_vars: tuple[str, str] | None, child_needs: set[int]
    ) -> list[ast.expr]:
        """Arguments for calling a child composite from a function in `frame`.
        `loop_vars` = (element, index) names of the child's own loop, when the
        child is a loop element (its frame is one level deeper)."""
        args = ["root", *frame.item_names()]
        if loop_vars:
            args.append(loop_vars[0])
        for off in sorted(child_needs, reverse=True):
            if loop_vars is None:
                args.append(frame.index_name(off))
            elif off == 0:
                args.append(loop_vars[1])
            else:
                args.append(frame.index_name(off - 1))
        return [ast.Name(id=a, ctx=ast.Load()) for a in args]

    def _nested_loop(
        self,
        rule: LoopRule,
        fq: str,
        frame: _Frame,
        where: str,
        into: tuple[str, str] | None = None,
    ) -> tuple[list[ast.stmt], str, _Composite]:
        """`<id>_list = []` + a `for` filling it, inside the parent's function; with `into`, the
        `for` adds to a list an earlier loop of the same container started."""
        cid = ident_of(fq)
        source = self._source_text(rule, self._scope(frame), where)
        child_frame = frame.child(rule.label, self._element_type(source, frame), rule.source)
        out_field = _output_field(rule.output, where)
        sub = self._composite(
            rule,
            fq,
            child_frame,
            _pascal(out_field) + ("" if rule.first else "Item"),
            None,
            reuse=into[1] if into else None,
        )

        item, index = f"{cid}_src", f"{cid}_index"
        uses_index = 0 in sub.needs
        loop_scope = AnchorScope(
            loops=(*frame.loop_refs(), LoopRef(rule.label, item, index)), lookups=self.lookups
        )
        iterable, filter_text = self._iterable(rule, source, item, loop_scope, uses_index, where)
        list_var = into[0] if into else f"{cid}_list"
        call = ast.Call(
            func=ast.Name(id=sub.ident, ctx=ast.Load()),
            args=self._call_args(frame, (item, index), sub.needs),
            keywords=[],
        )
        target = f"{index}, {item}" if uses_index else item
        loop = self._stmts(f"for {target} in {iterable}:\n    {list_var}.append(None)")[0]
        assert isinstance(loop, ast.For)
        loop.body = [
            ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id=list_var, ctx=ast.Load()), attr="append", ctx=ast.Load()
                    ),
                    args=[call],
                    keywords=[],
                )
            )
        ]
        if filter_text and not uses_index:
            loop.body.insert(0, self._stmts(f"if not ({filter_text}):\n    continue")[0])
        stmts: list[ast.stmt] = [loop] if into else [*self._stmts(f"{list_var} = []"), loop]
        return stmts, list_var, sub


def build_stage(
    file: FunctionalFile,
    options: TranspileOptions,
    input_schema: SchemaTypes | None = None,
    warnings: list[str] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> str:
    """Stage `build`: rule tree -> `.map.py` text, before loop fusion (anchors,
    expressions, `choices` steps and their comments are all applied here).
    `warnings`, when given, receives the non-fatal findings (unused `choices`,
    negative `multipleOf`, ...)."""
    assign_ids(file)
    # a rule with nothing defined yet (no Source, no Expression) builds nothing
    file = replace(file, rules=prune_unfinished(file.rules))
    if not file.rules:
        raise FnYamlError(
            f"mapping '{file.id}' is empty: no rule has a Source or an Expression yet"
        )
    # aliases / root override applied, selecting objects lowered to first-element loops
    b = _Builder(lower_selectors(expand_paths(file)), options, input_schema, output_schema)
    b.build()
    if warnings is not None:
        warnings.extend(b.warnings)
    directive = f"\n__validation__ = {b.validation_directive!r}" if b.validation_directive else ""
    header = ast.parse(f"from __mapping__ import *\n\n__id__ = {file.id!r}{directive}").body
    module = ast.Module(body=[*header, *b.classes, *b.functions, *b.flow], type_ignores=[])
    ast.fix_missing_locations(module)
    return _render(module) + "\n"


def auto_proposals(
    file: FunctionalFile,
    options: TranspileOptions | None = None,
    input_schema: SchemaTypes | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """For every field rule, what the transpiler would generate from its Source and expression
    now (it is what a manual rule's override replaces), keyed by fully-qualified rule id; and,
    for the rules where that fails, the reason."""
    assign_ids(file)
    file = replace(file, rules=prune_unfinished(file.rules))  # ids are set: they stay as they were
    b = _Builder(lower_selectors(expand_paths(file)), options or TranspileOptions(), input_schema)
    b.build()
    return b.proposals, b.proposal_errors


def fuse_stage(text: str, options: TranspileOptions) -> str:
    """Stage `fuse`: loop fusion over the `build` output (identity when
    `options.loop_fusion` is off)."""
    module = _parse_stage(text)
    if options.loop_fusion:
        n = 0
        for stmt in module.body:
            if not _is_fixed(stmt):
                break
            n += 1
        fixed, flow = module.body[:n], module.body[n:]
        rule_defs = {s.name: s for s in fixed if isinstance(s, ast.FunctionDef)}
        module.body = [
            *fixed,
            *fuse_loops(
                flow, rule_defs, options.parallel_conflict, True, lower_filtered_iters=False
            ),
        ]
    ast.fix_missing_locations(module)
    return _render(module) + "\n"


def emit_stage(text: str, options: TranspileOptions, source_name: str = "<fn.yaml>") -> str:
    """Stage `emit`: final touches and the generated-file header."""
    module = _CollapseDoubleNot().visit(_parse_stage(text))
    comment = (
        f"# Generated by `mapper transpile` from {source_name} — do not edit.\n"
        f"# compiler options: loop_fusion={'on' if options.loop_fusion else 'off'}\n\n"
    )
    return comment + _render(module) + "\n"


def _is_fixed(stmt: ast.stmt) -> bool:
    """Header, dataclasses and rule functions — everything before the mapping body."""
    if isinstance(stmt, ast.Assign):
        return any(
            isinstance(t, ast.Name) and t.id in ("__id__", "__validation__") for t in stmt.targets
        )
    return isinstance(stmt, ast.ImportFrom | ast.ClassDef | ast.FunctionDef)


def _parse_stage(text: str) -> ast.Module:
    """Read a stage's `.map.py` back: `# ...` comment lines (the only comments
    a stage file has) become marker statements again, so they survive."""
    text = re.sub(r"^(\s*)# (.*)$", lambda m: f"{m[1]}{COMMENT_MARK + m[2]!r}", text, flags=re.M)
    return ast.parse(text)


def transpile_file_model(
    file: FunctionalFile,
    options: TranspileOptions | None = None,
    input_schema: SchemaTypes | None = None,
    source_name: str = "<fn.yaml>",
    warnings: list[str] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> str:
    options = options or TranspileOptions()
    built = build_stage(file, options, input_schema, warnings, output_schema)
    return emit_stage(fuse_stage(built, options), options, source_name)


def transpile_file(
    path: Path,
    options: TranspileOptions | None = None,
    input_schema: SchemaTypes | None = None,
    warnings: list[str] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> str:
    return transpile_file_model(
        load_functional_file(path), options, input_schema, path.name, warnings, output_schema
    )


__all__ = [
    "Rule",
    "TranspileOptions",
    "auto_proposals",
    "build_stage",
    "emit_stage",
    "fuse_stage",
    "transpile_file",
    "transpile_file_model",
]
