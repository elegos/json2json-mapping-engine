"""Stages 4-5 and orchestration (docs/ARCHITECTURE.md, §Transpiler pipeline).

`transpile()` runs: id assignment -> Stage 2 anchors -> Stage 3 expression
blocks -> build the `.map.py` AST -> Stage 4 Loop Fusion (the compiler's own
`compiler.loop_fusion`, no reimplementation) -> Stage 5 `ast.unparse`.

**What the compiler can express bounds what this can emit.** Output today is:
top-level scalar fields, top-level objects (fields only, optional guard), and
single-level loops over a source array (fields only). Nested loops/objects
inside a loop or object are rejected with a clear error naming the rule.

**Shape of the generated code** (one rule function per *output element*):

- a top-level `field` rule -> `def <ident>(root) -> T` + `out.<Field> = <ident>(root)`;
- an `object` rule -> a `@dataclass` of its fields + one function building it
  (a false `guard` is a bare `return`, which omits the object);
- a `loop` rule -> a `@dataclass` of its fields + one function per item, called
  from a single `for` loop.

Fields of a loop/object share one function, so a failing field is reported
under the loop/object rule's id, not the field's — the compiler has no way to
isolate them inside a composite. Fields there also cannot use bare `return`
/ `return Null` (a composite has no "omit one field" form): express that with
`coalesce`/`if_else`.

Parameter convention (§Generated function parameter naming): `root`; loops add
`src` (the item) and `index`, the latter only if some field references it.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from compiler.loop_fusion import fuse_loops
from compiler.schema_generator import SchemaTypes
from transpiler.anchors import AnchorScope, resolve_anchors
from transpiler.expr import Block, parse_block
from transpiler.ids import assign_ids, ident_of
from transpiler.model import (
    FieldRule,
    FnYamlError,
    FunctionalFile,
    LookupRule,
    LoopRule,
    ObjectRule,
    Rule,
    load_functional_file,
)


@dataclass(frozen=True)
class TranspileOptions:
    loop_fusion: bool = True
    parallel_conflict: str = "exception"
    decimal_mode: str = "round"  # round | truncate — per-field format_mode overrides


def _pascal(name: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Anon"


_PATH = re.compile(r"^(?P<anchor>[$@])(?P<rest>(?:\.[A-Za-z_]\w*)*)(?:\[\*?\])?$")


def _source_expr(path: str, where: str) -> str:
    m = _PATH.match(path.strip())
    if not m:
        raise FnYamlError(f"{where}: unsupported source path {path!r}")
    if m.group("anchor") == "@":
        raise FnYamlError(
            f"{where}: relative source path {path!r} means a nested loop, which the "
            "compiler does not support yet"
        )
    return "root" + m.group("rest")


def _output_field(path: str, where: str) -> str:
    m = _PATH.match(path.strip())
    segs = m.group("rest").split(".")[1:] if m else []
    if len(segs) != 1:
        raise FnYamlError(
            f"{where}: output path {path!r} must be a single field of the output root "
            "(e.g. '$.Orders[*]') — deeper output paths need nested-output support in the compiler"
        )
    return segs[0]


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


class _Wrap(ast.NodeTransformer):
    """Wrap every returned value in `round(x, n)` / `trunc(x, n)` (`format`)."""

    def __init__(self, func: str, digits: int):
        self.func, self.digits = func, digits

    def visit_Return(self, node: ast.Return) -> ast.Return:
        v = node.value
        if v is None or (isinstance(v, ast.Name) and v.id == "Null"):
            return node
        call = ast.Call(
            func=ast.Name(id=self.func, ctx=ast.Load()),
            args=[v, ast.Constant(value=self.digits)],
            keywords=[],
        )
        return ast.copy_location(ast.Return(value=call), node)


def _type_name_at(schema: SchemaTypes | None, source_expr: str) -> str | None:
    """Element type of `root.a.b` (an array) per the input schema, else None."""
    if schema is None:
        return None
    cls = schema.classes.get(schema.root_type)
    type_expr = schema.root_type
    for seg in source_expr.split(".")[1:]:
        if cls is None:
            return None
        fld = next((f for f in cls.fields if f.name == seg), None)
        if fld is None:
            return None
        type_expr = fld.type_expr
        parts = [p.strip() for p in type_expr.split("|") if p.strip() not in ("None", "Null")]
        if len(parts) != 1:
            return None
        type_expr = parts[0]
        cls = schema.classes.get(type_expr)
    if type_expr.startswith("list[") and type_expr.endswith("]"):
        return type_expr[5:-1]
    return None


class _Builder:
    def __init__(self, file: FunctionalFile, options: TranspileOptions, schema: SchemaTypes | None):
        self.file = file
        self.opt = options
        self.schema = schema
        self.lookups: dict[str, dict] = {}
        self.classes: list[ast.stmt] = []
        self.functions: list[ast.stmt] = []
        self.flow: list[ast.stmt] = []
        self._class_names: set[str] = set()

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

    def _field_block(self, rule: FieldRule, fq: str, scope: AnchorScope) -> Block:
        where = f"rule '{fq}'"
        t = rule.transform
        if t.status == "manual":
            assert t.code_override is not None
            text = t.code_override
        else:
            assert t.expression is not None
            text = resolve_anchors(t.expression, scope, where).text
        block = parse_block(text, ident_of(fq), where)
        if rule.type == "number" and rule.format:
            mode = rule.format_mode or self.opt.decimal_mode
            wrap = _Wrap("round" if mode == "round" else "trunc", _decimals(rule.format))
            block = Block([wrap.visit(s) for s in block.stmts], block.returns_null, block.can_omit)
            for s in block.stmts:
                ast.fix_missing_locations(s)
        return block

    def _ret_annotation(self, rule: FieldRule, block: Block) -> str:
        return _annotation(rule.type, not rule.required, block.returns_null)

    def _param_types(self, source_expr: str | None) -> tuple[str, str]:
        root = self.schema.root_type if self.schema else "Any"
        src = (_type_name_at(self.schema, source_expr) if source_expr else None) or "Any"
        return root, src

    # -- rules -------------------------------------------------------------

    def build(self) -> None:
        from transpiler.ids import walk

        for _fq, rule in walk(self.file.rules):
            if isinstance(rule, LookupRule):
                self.lookups[rule.label] = dict(rule.entries)
        labels = [
            r.label for _fq, r in walk(self.file.rules) if isinstance(r, LoopRule) and r.label
        ]
        clash = sorted(set(labels) & set(self.lookups))
        if clash:
            raise FnYamlError(f"label(s) used by both a loop and a lookup: {', '.join(clash)}")

        for rule in self.file.rules:
            assert rule.id is not None
            if isinstance(rule, LookupRule):
                continue
            if isinstance(rule, FieldRule):
                self._top_field(rule)
            elif isinstance(rule, ObjectRule):
                self._object(rule)
            else:
                self._loop(rule)

    def _top_field(self, rule: FieldRule) -> None:
        assert rule.id is not None
        fq, ident = rule.id, ident_of(rule.id)
        block = self._field_block(rule, fq, AnchorScope(lookups=self.lookups))
        root_t, _ = self._param_types(None)
        ret = self._ret_annotation(rule, block)
        fn = ast.parse(f"def {ident}(root: {root_t}) -> {ret}:\n    pass").body[0]
        assert isinstance(fn, ast.FunctionDef)
        fn.body = block.stmts
        self.functions.append(fn)
        self.flow += self._stmts(f"out.{rule.field} = {ident}(root)")

    def _composite_fields(
        self, parent: ObjectRule | LoopRule, parent_fq: str, scope: AnchorScope
    ) -> tuple[list[ast.stmt], list[tuple[str, str, str]]]:
        pre: list[ast.stmt] = []
        fields: list[tuple[str, str, str]] = []  # (name, annotation, value source)
        kw: list[ast.keyword] = []
        seen: set[str] = set()
        for child in parent.rules:
            assert child.id is not None
            fq = f"{parent_fq}.{child.id}"
            if isinstance(child, LookupRule):
                continue
            if not isinstance(child, FieldRule):
                raise FnYamlError(
                    f"rule '{fq}': a {child.kind} rule nested in a {parent.kind} needs "
                    "nested-output support in the compiler, which does not exist yet"
                )
            if child.field in seen:
                raise FnYamlError(f"rule '{fq}': duplicate field '{child.field}'")
            seen.add(child.field)
            block = self._field_block(child, fq, scope)
            if not block.is_simple:
                raise FnYamlError(
                    f"rule '{fq}': inside a {parent.kind} a field must be assignments followed by "
                    "one value (no if/return/Null) — use if_else()/coalesce() instead"
                )
            pre += block.pre
            kw.append(ast.keyword(arg=child.field, value=block.value))
            fields.append((child.field, self._ret_annotation(child, block), ""))
        if not fields:
            raise FnYamlError(f"rule '{parent_fq}': a {parent.kind} rule needs at least one field")
        self._kw = kw
        return pre, fields

    def _make_class(self, base: str, fields: list[tuple[str, str, str]]) -> str:
        name = self._unique_class(base)
        body = "\n".join(f"    {n}: {a}" for n, a, _ in fields)
        self.classes += self._stmts(f"@dataclass\nclass {name}:\n{body}")
        return name

    def _object(self, rule: ObjectRule) -> None:
        assert rule.id is not None
        fq, ident = rule.id, ident_of(rule.id)
        out_field = _output_field(rule.output, f"rule '{fq}'")
        scope = AnchorScope(lookups=self.lookups)
        pre, fields = self._composite_fields(rule, fq, scope)
        kw = self._kw
        cls = self._make_class(_pascal(out_field), fields)
        root_t, _ = self._param_types(None)
        fn = ast.parse(f"def {ident}(root: {root_t}) -> {cls}:\n    pass").body[0]
        assert isinstance(fn, ast.FunctionDef)
        build: list[ast.stmt] = [
            *pre,
            ast.Return(value=ast.Call(func=ast.Name(cls, ast.Load()), args=[], keywords=kw)),
        ]
        body: list[ast.stmt] = build
        if rule.guard:
            g = parse_block(
                resolve_anchors(rule.guard, scope, f"rule '{fq}' guard").text,
                f"{ident}_guard",
                f"rule '{fq}' guard",
            )
            if not g.is_simple:
                raise FnYamlError(f"rule '{fq}': guard must be a single boolean expression")
            # `if <guard>: build else: return` — not `if not <guard>: return`: a NULL
            # guard (missing field) must omit the object, and in SQL `NOT NULL` is
            # NULL, so the negated form would fall through and build it.
            test = ast.If(test=g.value, body=build, orelse=[ast.Return(value=None)])
            body = [*g.pre, test]
        fn.body = body
        ast.fix_missing_locations(fn)
        self.functions.append(fn)
        self.flow += self._stmts(f"out.{out_field} = {ident}(root)")

    def _loop(self, rule: LoopRule) -> None:
        assert rule.id is not None
        fq, ident = rule.id, ident_of(rule.id)
        where = f"rule '{fq}'"
        src_expr = _source_expr(rule.source, where)
        out_field = _output_field(rule.output, where)
        scope = AnchorScope(loop_label=rule.label, in_loop=True, lookups=self.lookups)
        pre, fields = self._composite_fields(rule, fq, scope)
        kw = self._kw

        uses_index = any(
            isinstance(n, ast.Name) and n.id == "index"
            for node in [*pre, *[k.value for k in kw]]
            for n in ast.walk(node)
        )
        cls = self._make_class(_pascal(out_field) + "Item", fields)
        root_t, src_t = self._param_types(src_expr)
        params = f"root: {root_t}, src: {src_t}" + (", index: int" if uses_index else "")
        fn = ast.parse(f"def {ident}({params}) -> {cls}:\n    pass").body[0]
        assert isinstance(fn, ast.FunctionDef)
        fn.body = [
            *pre,
            ast.Return(value=ast.Call(func=ast.Name(cls, ast.Load()), args=[], keywords=kw)),
        ]
        ast.fix_missing_locations(fn)
        self.functions.append(fn)

        iterable = src_expr
        if rule.sort_key:
            m = re.match(rf"^@(?:{re.escape(rule.label or '')})?\.(\w+)$", rule.sort_key.strip())
            if not m:
                raise FnYamlError(f"{where}: sort key must be a field of the item ('@.field')")
            rev = ", reverse=True" if rule.sort_reverse else ""
            iterable = f'sorted({iterable}, key="{m.group(1)}"{rev})'
        filter_text = None
        if rule.filter:
            f = resolve_anchors(rule.filter, scope, f"{where} filter")
            if f.uses_index:
                raise FnYamlError(f"{where}: filter cannot reference @index")
            filter_text = f.text
        if uses_index:
            # The index numbers the elements that pass the filter, so the filter must
            # come *before* enumerate(): in real Python a `continue` in the body would
            # leave gaps. The compiler lowers this form (per-branch counter when fused).
            if filter_text:
                iterable = f"[src for src in {iterable} if {filter_text}]"
            start = f", start={rule.index_start}" if rule.index_start else ""
            iterable = f"enumerate({iterable}{start})"
        target = "index, src" if uses_index else "src"
        call_args = "root, src" + (", index" if uses_index else "")
        loop_src = f"for {target} in {iterable}:\n    out.{out_field}.append({ident}({call_args}))"
        loop = self._stmts(loop_src)[0]
        assert isinstance(loop, ast.For)
        if filter_text and not uses_index:
            guard = self._stmts(f"if not ({filter_text}):\n    continue")[0]
            loop.body.insert(0, guard)
        ast.fix_missing_locations(loop)
        self.flow.append(loop)


def transpile_file_model(
    file: FunctionalFile,
    options: TranspileOptions | None = None,
    input_schema: SchemaTypes | None = None,
    source_name: str = "<fn.yaml>",
) -> str:
    options = options or TranspileOptions()
    assign_ids(file)
    b = _Builder(file, options, input_schema)
    b.build()

    header = ast.parse(f"from __mapping__ import *\n\n__id__ = {file.id!r}").body
    body: list[ast.stmt] = [*header, *b.classes, *b.functions, *b.flow]
    if options.loop_fusion:
        fixed = header + b.classes + b.functions
        rule_defs = {s.name: s for s in b.functions if isinstance(s, ast.FunctionDef)}
        body = [
            *fixed,
            *fuse_loops(
                b.flow, rule_defs, options.parallel_conflict, True, lower_filtered_iters=False
            ),
        ]
    module = ast.Module(body=body, type_ignores=[])
    module = _CollapseDoubleNot().visit(module)
    ast.fix_missing_locations(module)
    comment = (
        f"# Generated by `mapper transpile` from {source_name} — do not edit.\n"
        f"# compiler options: loop_fusion={'on' if options.loop_fusion else 'off'}\n\n"
    )
    return comment + ast.unparse(module) + "\n"


def transpile_file(
    path: Path,
    options: TranspileOptions | None = None,
    input_schema: SchemaTypes | None = None,
) -> str:
    return transpile_file_model(load_functional_file(path), options, input_schema, path.name)


__all__ = ["Rule", "TranspileOptions", "transpile_file", "transpile_file_model"]
