"""PL/SQL Code Generator — bootstrap mode (M2a/M2b).

Emits the twin `map_<id>` / `map_<id>_safe` procedures described in
docs/ARCHITECTURE.md §Generated artifact / §Runtime error semantics.

**Function-calling convention** (locked in after discussion): rule
functions (`def`) are written at the *source* root level in `.map.py`, with
explicit typed parameters — no implicit closure over `root`/`src`/the
enclosing loop variable. A function only ever sees what's passed to it:

    def line_rule(itm: Item) -> Line:
        return Line(LineId=itm.id, LineAmount=itm.price)

    for itm in root.orders.items:
        out.Lines.append(line_rule(itm))

**Standalone, package-assembly-ready functions.** Each `fn_<rule_id>` is
emitted as its own `CREATE OR REPLACE FUNCTION`, a sibling of `map_<id>` /
`map_<id>_safe` — not nested inside them. This is deliberate: package
assembly (M3) will place `map_<id>`/`map_<id>_safe` and every `fn_<rule_id>`
into one package body, exporting `fn_<rule_id>` in the spec too only when
`[target.plsql] export_rule_functions = true` (§Generated artifact,
"Rule-function visibility") — that only works cleanly if rule functions are
already independent subprograms, not closures nested inside a specific
caller.

**"Omit field" without a shared exception.** A standalone function can't
rely on a `WHEN e_field_omitted THEN` handler declared in some specific
caller's scope (that was M2a's mechanism, viable only because rule
functions were nested inside their one caller). Instead, every rule
function takes a trailing `p_omitted OUT BOOLEAN` parameter: bare `return`
sets it `TRUE` and returns `NULL`; every other path sets it `FALSE`
(defaulted at function entry). The call site checks `p_omitted` after the
call instead of catching a dedicated exception — same three-way emission
contract (§Return semantics), a mechanism that works identically whether
the function ends up nested, standalone, or package-private.

**Composite output values** — `Line(LineId=..., LineAmount=...)` (keyword
construction of a `@dataclass`) has no dedicated AST node; it is an
ordinary `Call` whose `func` name happens to be a locally-declared
dataclass. It is built **in memory**, field by field, directly on a
`JSON_OBJECT_T` via a `.put()` sequence — never round-tripped through
`JSON_OBJECT(...)`/text at all. An earlier version did that text round
trip (`JSON_OBJECT_T(JSON_OBJECT(...))`) and hit two real problems: native
PL/SQL rejects `JSON_OBJECT(...) RETURNING CLOB` (PLS-00684 — that clause
is SQL-context-only), and even the default (VARCHAR2) form caps the whole
serialized value at 4000 bytes for no reason, since `JSON_OBJECT_T.put()`
has no such limit. Supported today only as the direct value of a `return`
or of `out.<field> = ...` / `.append(...)` — not as a nested sub-expression
(`_materialize_dataclass` needs a statement sequence, not a single
expression slot).

**Output arrays** — `out.<Field>.append(<expr>)` is recognized as a
statement (an `Expr` wrapping a `Call` to `<out-attribute-chain>.append`),
not a new grammar construct (`Call`/`Attribute`/`Expr`-statement are all
already unrestricted by the Validator). Every list-typed output field gets
one `JSON_ARRAY_T` accumulator declared at the top of each procedure,
appended to wherever the source `.append()` call appears (including inside
a generated `for`-loop), and `.put()` onto `v_out_obj` once at the end.

**Standing principle: CLOB only at the true boundary.** `p_src`/`p_out`/
`p_err` are CLOB because that's the procedure's external contract
(§Generated artifact) — nothing more. `p_src` is parsed into `v_srcroot`
exactly once, at the top; `v_out_obj`/list accumulators are serialized to
CLOB exactly once, at the bottom (`p_out := v_out_obj.TO_CLOB()`;
`p_err := v_err_arr.to_clob()`). Everything in between — every rule
function, every dataclass construction, every `get_*`/`.put()`/`.append()`
call — stays in native `JSON_OBJECT_T`/`JSON_ARRAY_T` object form. No
intermediate text/CLOB round trip, and no dropping into a SQL-context-only
construct (like `JSON_OBJECT(...)`, which caused the PLS-00684 bug above)
where a native PL/SQL object-method call does the same job without the
context switch. The one narrow, unavoidable exception is the error
payload's *message text* itself (`RAISE_APPLICATION_ERROR` and `p_err` are
inherently text/CLOB by their own nature, not by choice).

(Deferred, not yet needed by any fixture: a mapping whose *root* output is
itself an array rather than an object would need `v_out_obj` to be a
`JSON_ARRAY_T` instead of a `JSON_OBJECT_T` — same principle, just a
different top-level accumulator type. Every fixture so far has an
object-shaped root output.)

Scope of this milestone (documented, not silently assumed):
- Single-level `for` loops are supported; nested loops are not yet.
- Loop Fusion (merging multiple loops/field-functions over the same source
  array, the `@parallel` conflict check, the filter-to-per-branch-IF
  rewrite — docs/ARCHITECTURE.md's Loop Fusion Optimizer section) is not
  wired into this backend yet — every `for` compiles to its own loop.
- Package assembly (spec/body, multi-file, the `export_rule_functions`
  toggle's actual effect) is a Build CLI concern (M3) — this module emits
  standalone objects, already shaped for that later step.
- String sizing from JSON Schema `maxLength` is not wired up yet — `str`
  fields/locals default to a generic `VARCHAR2(4000 CHAR)` declaration.
- The RAISE_APPLICATION_ERROR payload is byte-budget-aware (§Runtime error
  semantics + M0.5 spike findings, docs/spike-notes.md).
"""

from __future__ import annotations

import ast
import itertools
from dataclasses import dataclass

from compiler.annotations import AnnotationError, resolve_dsl_type
from compiler.backends.base import CodeGenerator, FieldRule
from compiler.function_linker import FunctionLinker

# PL/SQL requires a VARCHAR2 *variable* declaration to carry a size (unlike
# a function RETURN type or PARAMETER type, which must NOT — see
# `_DSL_TO_PLSQL_UNCONSTRAINED` below).
_EXPECTED_TO_DECL_TYPE = {
    "VARCHAR2": "VARCHAR2(4000 CHAR)",
    "NUMBER": "NUMBER",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
}

# PL/SQL disallows size/scale constraints on a function's RETURN type or on
# a parameter's type (PLS-00263) — both must be declared unconstrained.
_DSL_TO_PLSQL_UNCONSTRAINED = {
    "str": "VARCHAR2",
    "int": "NUMBER",
    "number": "NUMBER",
    "bool": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
}

_GETTER = {
    "VARCHAR2": "get_String",
    "NUMBER": "get_Number",
    "BOOLEAN": "get_Boolean",
    "DATE": "get_Date",
    "TIMESTAMP": "get_Timestamp",
}

_DSL_TO_EXPECTED = {
    "str": "VARCHAR2",
    "int": "NUMBER",
    "number": "NUMBER",
    "bool": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
}

_COMPARE_OPS = {
    ast.Eq: "=",
    ast.NotEq: "<>",
    ast.Lt: "<",
    ast.Gt: ">",
    ast.LtE: "<=",
    ast.GtE: ">=",
}

_BINOPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}

# Per-builtin, per-positional-arg expected PL/SQL scalar kind. `None` means
# "inherit the call's own outer expected type" (e.g. coalesce's branches).
# `concat` is variadic and handled separately (every arg is VARCHAR2).
_BUILTIN_ARG_EXPECTED: dict[str, list[str | None]] = {
    "coalesce": [None, None],
    "round": ["NUMBER", "NUMBER"],
    "if_else": ["BOOLEAN", None, None],
    "split_first": ["VARCHAR2", "VARCHAR2"],
    "split_nth": ["VARCHAR2", "VARCHAR2", "NUMBER"],
    "lookup": ["VARCHAR2", "OBJECT", "VARCHAR2"],
    "parse_date": ["VARCHAR2", "VARCHAR2"],
}

# Conservative target for the *entries* JSON, leaving margin under the
# ~1899-byte ceiling observed for `DBMS_UTILITY.FORMAT_ERROR_STACK` against a
# real Oracle 23ai instance (M0.5 spike) — see the comment at `raising_tail`.
_ERROR_PAYLOAD_BYTE_BUDGET = 1800

class CodeGenError(Exception):
    pass


def _quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


@dataclass(frozen=True)
class _DataclassField:
    name: str
    base_type: str
    nullable: bool


@dataclass(frozen=True)
class _DataclassDef:
    name: str
    fields: list[_DataclassField]


def _collect_dataclasses(tree: ast.Module) -> dict[str, _DataclassDef]:
    registry: dict[str, _DataclassDef] = {}
    for stmt in tree.body:
        if not isinstance(stmt, ast.ClassDef):
            continue
        is_dataclass = any(
            (isinstance(d, ast.Name) and d.id == "dataclass")
            or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
            for d in stmt.decorator_list
        )
        if not is_dataclass:
            continue
        fields: list[_DataclassField] = []
        for body_stmt in stmt.body:
            if isinstance(body_stmt, ast.AnnAssign) and isinstance(body_stmt.target, ast.Name):
                base, nullable = resolve_dsl_type(body_stmt.annotation)
                fields.append(_DataclassField(body_stmt.target.id, base, nullable))
        registry[stmt.name] = _DataclassDef(stmt.name, fields)
    return registry


def _expected_kind(base_type: str) -> str:
    """PL/SQL scalar-getter kind for a DSL base type name, or "OBJECT" for
    anything else (a dataclass, or an unchecked schema-derived type)."""
    return _DSL_TO_EXPECTED.get(base_type, "OBJECT")


def _plsql_unconstrained_type(base_type: str) -> str:
    """Unconstrained PL/SQL type for a RETURN clause or parameter."""
    return _DSL_TO_PLSQL_UNCONSTRAINED.get(base_type, "JSON_OBJECT_T")


@dataclass
class _RuleSignature:
    param_names: list[str]
    param_expected: list[str]  # per-param expected kind, for call-site arg translation
    param_plsql_types: list[str]
    return_base_type: str
    return_expected: str
    return_plsql_type: str
    nullable: bool


def _resolve_signature(fn_def: ast.FunctionDef) -> _RuleSignature:
    if fn_def.returns is None:
        raise CodeGenError(f"function '{fn_def.name}' is missing a return annotation")
    try:
        return_base, nullable = resolve_dsl_type(fn_def.returns)
    except AnnotationError as exc:
        raise CodeGenError(str(exc)) from exc

    param_names: list[str] = []
    param_expected: list[str] = []
    param_plsql_types: list[str] = []
    for a in fn_def.args.args:
        if a.annotation is None:
            raise CodeGenError(f"parameter '{a.arg}' of '{fn_def.name}' has no type annotation")
        try:
            p_base, _p_nullable = resolve_dsl_type(a.annotation)
        except AnnotationError as exc:
            raise CodeGenError(str(exc)) from exc
        param_names.append(a.arg)
        param_expected.append(_expected_kind(p_base))
        param_plsql_types.append(_plsql_unconstrained_type(p_base))

    return _RuleSignature(
        param_names=param_names,
        param_expected=param_expected,
        param_plsql_types=param_plsql_types,
        return_base_type=return_base,
        return_expected=_expected_kind(return_base),
        return_plsql_type=_plsql_unconstrained_type(return_base),
        nullable=nullable,
    )


class _FlowCtx:
    """Name resolution for the *flowing* module/loop scope: `root`, `src`,
    and loop variables are magic here. No local variables (the Validator
    forbids bare local assignment outside a function body)."""

    def __init__(self, loop_vars: list[str]):
        # Innermost last — used only for `src` (nearest enclosing loop).
        self.loop_vars = loop_vars

    def resolve_name(self, name: str) -> str | None:
        if name == "root":
            return "v_srcroot"
        if name == "src":
            if not self.loop_vars:
                raise CodeGenError("`src` used outside a loop")
            return f"v_{self.loop_vars[-1]}"
        if name in self.loop_vars:
            return f"v_{name}"
        return None


class _FnCtx:
    """Name resolution inside a rule-function body: only its own declared
    parameters and locals are visible — no implicit access to `root`/`src`/
    the caller's loop variable (§ module docstring)."""

    def __init__(self, params: list[str], local_prefix: str):
        self.params = set(params)
        self.local_prefix = local_prefix
        self.locals: dict[str, str] = {}
        self.declarations: list[str] = []

    def resolve_name(self, name: str) -> str | None:
        if name in self.params:
            return f"p_{name}"
        return None


class _ExprTranslator:
    def __init__(
        self,
        ctx: _FlowCtx | _FnCtx,
        rule_signatures: dict[str, _RuleSignature],
        dataclasses: dict[str, _DataclassDef],
        function_linker: FunctionLinker,
    ):
        self.ctx = ctx
        self.rule_signatures = rule_signatures
        self.dataclasses = dataclasses
        self.function_linker = function_linker

    def translate(self, node: ast.expr, expected: str | None) -> str:
        method = getattr(self, f"_t_{type(node).__name__}", None)
        if method is None:
            raise CodeGenError(f"unsupported expression: {type(node).__name__}")
        return method(node, expected)

    def _t_Constant(self, node: ast.Constant, expected: str | None) -> str:
        v = node.value
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, str):
            return _quote(v)
        return str(v)

    def _t_Name(self, node: ast.Name, expected: str | None) -> str:
        name = node.id
        if name == "Null":
            return "NULL"
        resolved = self.ctx.resolve_name(name)
        if resolved is not None:
            return resolved
        if isinstance(self.ctx, _FnCtx) and name in self.ctx.locals:
            return f"v_{self.ctx.local_prefix}_{name}"
        raise CodeGenError(f"unresolved name '{name}'")

    def _t_Attribute(self, node: ast.Attribute, expected: str | None) -> str:
        segments: list[str] = []
        cur: ast.expr = node
        while isinstance(cur, ast.Attribute):
            segments.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            raise CodeGenError("unsupported attribute chain base")
        segments.reverse()
        code = self.translate(cur, None)
        if expected == "OBJECT":
            for seg in segments:
                code = f"{code}.get_Object({_quote(seg)})"
            return code
        if expected == "ARRAY":
            for seg in segments[:-1]:
                code = f"{code}.get_Object({_quote(seg)})"
            return f"{code}.get_Array({_quote(segments[-1])})"
        for seg in segments[:-1]:
            code = f"{code}.get_Object({_quote(seg)})"
        getter = _GETTER.get(expected or "", "get_String")
        return f"{code}.{getter}({_quote(segments[-1])})"

    def _t_BinOp(self, node: ast.BinOp, expected: str | None) -> str:
        op_type = type(node.op)
        left = self.translate(node.left, "NUMBER")
        right = self.translate(node.right, "NUMBER")
        if op_type in _BINOPS:
            return f"({left} {_BINOPS[op_type]} {right})"
        if op_type is ast.Div:
            return f"({left} / {right})"
        if op_type is ast.FloorDiv:
            return f"TRUNC({left} / {right})"
        if op_type is ast.Mod:
            return f"MOD({left}, {right})"
        raise CodeGenError(f"unsupported operator: {op_type.__name__}")

    def _t_Compare(self, node: ast.Compare, expected: str | None) -> str:
        if len(node.ops) != 1:
            raise CodeGenError("chained comparisons are not supported")
        op = node.ops[0]
        if type(op) not in _COMPARE_OPS:
            raise CodeGenError(f"unsupported comparison operator: {type(op).__name__}")
        operand_expected = "VARCHAR2"
        for side in (node.left, node.comparators[0]):
            if (
                isinstance(side, ast.Constant)
                and isinstance(side.value, (int, float))
                and not isinstance(side.value, bool)
            ):
                operand_expected = "NUMBER"
        left = self.translate(node.left, operand_expected)
        right = self.translate(node.comparators[0], operand_expected)
        return f"({left} {_COMPARE_OPS[type(op)]} {right})"

    def _t_BoolOp(self, node: ast.BoolOp, expected: str | None) -> str:
        joiner = " AND " if isinstance(node.op, ast.And) else " OR "
        parts = [self.translate(v, "BOOLEAN") for v in node.values]
        return "(" + joiner.join(parts) + ")"

    def _t_UnaryOp(self, node: ast.UnaryOp, expected: str | None) -> str:
        if not isinstance(node.op, ast.Not):
            raise CodeGenError("unsupported unary operator")
        return f"(NOT {self.translate(node.operand, 'BOOLEAN')})"

    def _t_IfExp(self, node: ast.IfExp, expected: str | None) -> str:
        test = self.translate(node.test, "BOOLEAN")
        body = self.translate(node.body, expected)
        orelse = self.translate(node.orelse, expected)
        return f"(CASE WHEN {test} THEN {body} ELSE {orelse} END)"

    def _t_Call(self, node: ast.Call, expected: str | None) -> str:
        if not isinstance(node.func, ast.Name):
            raise CodeGenError("only direct function calls are supported")
        name = node.func.id

        if name in self.dataclasses:
            raise CodeGenError(
                f"'{name}(...)' dataclass construction is only supported as a direct "
                "`return` value or `out.<field> = ...` / `.append(...)` argument "
                "(§module docstring) — it cannot be used as a nested sub-expression"
            )

        if name in self.rule_signatures:
            raise CodeGenError(
                f"'{name}' returns a value AND an omitted-flag — call it via the "
                "statement-level helper, not as a nested expression (M2b limitation)"
            )

        impl = self.function_linker.resolve(name)
        if name == "concat":
            arg_exprs = [self.translate(a, "VARCHAR2") for a in node.args]
        else:
            per_arg_expected = _BUILTIN_ARG_EXPECTED.get(name)
            arg_exprs = [
                self.translate(
                    a,
                    (per_arg_expected[i] if per_arg_expected and per_arg_expected[i] else expected),
                )
                for i, a in enumerate(node.args)
            ]
        return impl.render("plsql", arg_exprs)


def _is_dataclass_construction(node: ast.expr, dataclasses: dict[str, _DataclassDef]) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in dataclasses


def _materialize_dataclass(
    call: ast.Call, translator: _ExprTranslator, tmp_var: str
) -> list[str]:
    """Build a dataclass value **in memory**, field by field, into
    `tmp_var` — no text round-trip through `JSON_OBJECT()`/CLOB/VARCHAR2 at
    all, so no 4000-byte ceiling and no PLS-00684 (native PL/SQL rejects
    `JSON_OBJECT(...) RETURNING CLOB` — SQL-context-only, verified against a
    live Oracle 23ai instance). `JSON_OBJECT_T.put()` has no size limit."""
    assert isinstance(call.func, ast.Name)
    name = call.func.id
    cls = translator.dataclasses[name]
    if call.args:
        raise CodeGenError(f"'{name}(...)' construction requires keyword arguments")
    field_by_name = {f.name: f for f in cls.fields}
    lines = [f"{tmp_var} := JSON_OBJECT_T();"]
    for kw in call.keywords:
        if kw.arg is None:
            raise CodeGenError(f"'**kwargs' is not supported in '{name}(...)' construction")
        field_def = field_by_name.get(kw.arg)
        if field_def is None:
            raise CodeGenError(f"'{name}' has no field '{kw.arg}'")
        expected = _expected_kind(field_def.base_type)
        value_expr = translator.translate(kw.value, expected)
        lines.append(f"{tmp_var}.put({_quote(kw.arg)}, {value_expr});")
    return lines


def infer_type(node: ast.expr, ctx: _FnCtx) -> str:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "BOOLEAN"
        if isinstance(node.value, (int, float)):
            return "NUMBER"
        return "VARCHAR2"
    if isinstance(node, ast.BinOp):
        return "NUMBER"
    if isinstance(node, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
        return "BOOLEAN"
    if isinstance(node, ast.IfExp):
        return infer_type(node.body, ctx)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fname = node.func.id
        if fname == "coalesce":
            return infer_type(node.args[0], ctx)
        if fname == "if_else":
            return infer_type(node.args[1], ctx)
        if fname == "round":
            return "NUMBER"
        if fname == "parse_date":
            return "DATE"
        if fname in ("concat", "split_first", "split_nth", "lookup"):
            return "VARCHAR2"
    if isinstance(node, ast.Name) and node.id in ctx.locals:
        return ctx.locals[node.id]
    return "VARCHAR2"


def _indent(lines: list[str], level: int = 1) -> list[str]:
    pad = "    " * level
    return [pad + ln for ln in lines]


def _translate_fn_body(
    stmts: list[ast.stmt],
    ctx: _FnCtx,
    return_expected: str,
    translator: _ExprTranslator,
) -> list[str]:
    out: list[str] = []
    for stmt in stmts:
        if isinstance(stmt, ast.Assign):
            target = stmt.targets[0]
            if not isinstance(target, ast.Name):
                raise CodeGenError("unsupported local assignment target")
            inferred = infer_type(stmt.value, ctx)
            rhs = translator.translate(stmt.value, inferred)
            mangled = f"v_{ctx.local_prefix}_{target.id}"
            if target.id not in ctx.locals:
                ctx.locals[target.id] = inferred
                decl_type = _EXPECTED_TO_DECL_TYPE.get(inferred, inferred)
                ctx.declarations.append(f"{mangled} {decl_type};")
            out.append(f"{mangled} := {rhs};")
        elif isinstance(stmt, ast.Return):
            if stmt.value is None:
                out.append("p_omitted := TRUE;")
                out.append("RETURN NULL;")
            elif isinstance(stmt.value, ast.Name) and stmt.value.id == "Null":
                out.append("RETURN NULL;")
            elif _is_dataclass_construction(stmt.value, translator.dataclasses):
                assert isinstance(stmt.value, ast.Call)
                tmp_var = f"v_{ctx.local_prefix}__dc"
                if tmp_var not in ctx.locals:
                    ctx.locals[tmp_var] = "OBJECT"
                    ctx.declarations.append(f"{tmp_var} JSON_OBJECT_T;")
                out.extend(_materialize_dataclass(stmt.value, translator, tmp_var))
                out.append(f"RETURN {tmp_var};")
            else:
                out.append(f"RETURN {translator.translate(stmt.value, return_expected)};")
        elif isinstance(stmt, ast.If):
            out.extend(_translate_fn_if(stmt, ctx, return_expected, translator))
        else:
            raise CodeGenError(f"unsupported statement in field-rule body: {type(stmt).__name__}")
    return out


def _translate_fn_if(
    stmt: ast.If, ctx: _FnCtx, return_expected: str, translator: _ExprTranslator
) -> list[str]:
    lines = [f"IF {translator.translate(stmt.test, 'BOOLEAN')} THEN"]
    lines.extend(_indent(_translate_fn_body(stmt.body, ctx, return_expected, translator)))
    orelse = stmt.orelse
    while len(orelse) == 1 and isinstance(orelse[0], ast.If):
        elif_stmt = orelse[0]
        lines.append(f"ELSIF {translator.translate(elif_stmt.test, 'BOOLEAN')} THEN")
        lines.extend(_indent(_translate_fn_body(elif_stmt.body, ctx, return_expected, translator)))
        orelse = elif_stmt.orelse
    if orelse:
        lines.append("ELSE")
        lines.extend(_indent(_translate_fn_body(orelse, ctx, return_expected, translator)))
    lines.append("END IF;")
    return lines


@dataclass
class _ListAccumulator:
    field_name: str
    var_name: str


class PlsqlCodeGenerator(CodeGenerator):
    target = "plsql"

    def __init__(self, function_linker: FunctionLinker, error_code: int = -20000):
        self.function_linker = function_linker
        self.error_code = error_code

    # -- CodeGenerator interface -----------------------------------------

    def size_string_type(self, max_length: int | None) -> str:
        if max_length is not None and max_length <= 4000:
            return f"VARCHAR2({max_length} CHAR)"
        return "CLOB"

    def emit_field_guard(self, rule: FieldRule, out_field: str) -> str:
        raise NotImplementedError("use compile_module — kept for interface completeness")

    def emit_loop(self, loop_var: str, source_expr: str, body: str) -> str:
        raise NotImplementedError("use compile_module — kept for interface completeness")

    def emit_procedure_pair(
        self, mapping_id: str, declarations: str, body: str, error_code: int
    ) -> str:
        raise NotImplementedError("use compile_module — kept for interface completeness")

    # -- module compilation -----------------------------------------------

    def compile_module(self, tree: ast.Module, mapping_id: str, scope_resolution=None) -> str:
        self._loop_counter = itertools.count()
        dataclasses = _collect_dataclasses(tree)
        rule_defs: dict[str, ast.FunctionDef] = {}
        flow_stmts: list[ast.stmt] = []

        for stmt in tree.body:
            if isinstance(stmt, ast.ImportFrom):
                continue
            if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
                continue  # __id__ directive, already handled by the caller
            if isinstance(stmt, ast.ClassDef):
                continue  # already collected into `dataclasses`
            if isinstance(stmt, ast.FunctionDef):
                rule_defs[stmt.name] = stmt
                continue
            flow_stmts.append(stmt)

        rule_signatures = {name: _resolve_signature(fn_def) for name, fn_def in rule_defs.items()}

        function_texts = [
            self._compile_rule_function(name, fn_def, rule_signatures, dataclasses)
            for name, fn_def in rule_defs.items()
        ]

        list_accumulators: dict[str, _ListAccumulator] = {}
        body_lines = self._emit_flow(
            flow_stmts,
            loop_vars=[],
            rule_signatures=rule_signatures,
            dataclasses=dataclasses,
            list_accumulators=list_accumulators,
        )

        return self._render(mapping_id, function_texts, body_lines, list_accumulators)

    def _compile_rule_function(
        self,
        name: str,
        fn_def: ast.FunctionDef,
        rule_signatures: dict[str, _RuleSignature],
        dataclasses: dict[str, _DataclassDef],
    ) -> str:
        sig = rule_signatures[name]
        ctx = _FnCtx(params=sig.param_names, local_prefix=name)
        translator = _ExprTranslator(ctx, rule_signatures, dataclasses, self.function_linker)
        body_lines = ["p_omitted := FALSE;"]
        body_lines.extend(_translate_fn_body(fn_def.body, ctx, sig.return_expected, translator))

        params = [
            f"p_{pname} IN {ptype}"
            for pname, ptype in zip(sig.param_names, sig.param_plsql_types, strict=True)
        ]
        params.append("p_omitted OUT BOOLEAN")
        decls = "\n    ".join(ctx.declarations)

        header = f"FUNCTION fn_{name}(" + ", ".join(params) + f") RETURN {sig.return_plsql_type} IS\n"
        if decls:
            header += f"    {decls}\n"
        return (
            f"CREATE OR REPLACE {header}"
            "BEGIN\n" + "\n".join(_indent(body_lines)) + f"\nEND fn_{name};\n/"
        )

    def _emit_flow(
        self,
        stmts: list[ast.stmt],
        loop_vars: list[str],
        rule_signatures: dict[str, _RuleSignature],
        dataclasses: dict[str, _DataclassDef],
        list_accumulators: dict[str, _ListAccumulator],
    ) -> list[str]:
        ctx = _FlowCtx(loop_vars)
        translator = _ExprTranslator(ctx, rule_signatures, dataclasses, self.function_linker)
        lines: list[str] = []

        for stmt in stmts:
            if isinstance(stmt, ast.Assign):
                target = stmt.targets[0]
                if not (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "out"
                ):
                    raise CodeGenError("only `out.<field> = ...` assignments are supported")
                field_name = target.attr
                lines.extend(
                    self._emit_out_write(
                        field_name, stmt.value, ctx, translator, rule_signatures,
                        sink=lambda expr, f=field_name: f"v_out_obj.put({_quote(f)}, {expr});",
                    )
                )
            elif (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Call)
                and self._is_out_append(stmt.value)
            ):
                call = stmt.value
                assert isinstance(call.func, ast.Attribute)
                out_attr = call.func.value
                assert isinstance(out_attr, ast.Attribute)
                field_name = out_attr.attr
                if field_name not in list_accumulators:
                    list_accumulators[field_name] = _ListAccumulator(
                        field_name, f"v_arr_{field_name}"
                    )
                if len(call.args) != 1:
                    raise CodeGenError("`.append(...)` takes exactly one argument")
                var_name = list_accumulators[field_name].var_name
                lines.extend(
                    self._emit_out_write(
                        field_name, call.args[0], ctx, translator, rule_signatures,
                        sink=lambda expr, v=var_name: f"{v}.append({expr});",
                    )
                )
            elif isinstance(stmt, ast.For):
                lines.extend(
                    self._emit_for(stmt, loop_vars, rule_signatures, dataclasses, list_accumulators)
                )
            elif isinstance(stmt, ast.If):
                lines.extend(
                    self._emit_flow_if(
                        stmt, loop_vars, rule_signatures, dataclasses, list_accumulators, translator
                    )
                )
            else:
                raise CodeGenError(f"unsupported statement in mapping body: {type(stmt).__name__}")
        return lines

    def _emit_flow_if(
        self,
        stmt: ast.If,
        loop_vars: list[str],
        rule_signatures: dict[str, _RuleSignature],
        dataclasses: dict[str, _DataclassDef],
        list_accumulators: dict[str, _ListAccumulator],
        translator: _ExprTranslator,
    ) -> list[str]:
        """Handles a plain `IF`/`ELIF`/`ELSE` at flow level — the shape the
        Loop Fusion Optimizer normalizes bootstrap `if cond: continue`
        filters into (§compiler/loop_fusion.py), and a legitimate direct
        conditional guard around a group of `out.*` writes in its own right."""

        def recurse(body: list[ast.stmt]) -> list[str]:
            return self._emit_flow(body, loop_vars, rule_signatures, dataclasses, list_accumulators)

        lines = [f"IF {translator.translate(stmt.test, 'BOOLEAN')} THEN"]
        lines.extend(_indent(recurse(stmt.body)))
        orelse = stmt.orelse
        while len(orelse) == 1 and isinstance(orelse[0], ast.If):
            elif_stmt = orelse[0]
            lines.append(f"ELSIF {translator.translate(elif_stmt.test, 'BOOLEAN')} THEN")
            lines.extend(_indent(recurse(elif_stmt.body)))
            orelse = elif_stmt.orelse
        if orelse:
            lines.append("ELSE")
            lines.extend(_indent(recurse(orelse)))
        lines.append("END IF;")
        return lines

    def _emit_out_write(
        self,
        field_name: str,
        value: ast.expr,
        ctx: _FlowCtx,
        translator: _ExprTranslator,
        rule_signatures: dict[str, _RuleSignature],
        sink,
    ) -> list[str]:
        """Emit the guarded statement(s) producing one output value (via
        `sink`, either a `.put()` or an `.append()`), handling both the
        direct-expression shorthand and a call to a rule function (which
        needs the omitted-flag check)."""
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in rule_signatures
        ):
            rule_id = value.func.id
            sig = rule_signatures[rule_id]
            if len(value.args) != len(sig.param_names):
                raise CodeGenError(
                    f"'{rule_id}' takes {len(sig.param_names)} argument(s), got {len(value.args)}"
                )
            arg_exprs = [
                translator.translate(a, sig.param_expected[i]) for i, a in enumerate(value.args)
            ]
            result_var = f"v_result_{rule_id}"
            omitted_var = f"v_omitted_{rule_id}"
            call_expr = f"fn_{rule_id}(" + ", ".join([*arg_exprs, omitted_var]) + ")"
            return self._guarded(
                rule_id,
                declare=[f"{result_var} {_decl_type(sig.return_expected)};", f"{omitted_var} BOOLEAN;"],
                body=[
                    f"{result_var} := {call_expr};",
                    f"IF NOT {omitted_var} THEN",
                    f"    {sink(result_var)}",
                    "END IF;",
                ],
            )
        if _is_dataclass_construction(value, translator.dataclasses):
            assert isinstance(value, ast.Call)
            tmp_var = f"v_dc_{field_name}"
            setup_lines = _materialize_dataclass(value, translator, tmp_var)
            return self._guarded(
                field_name,
                declare=[f"{tmp_var} JSON_OBJECT_T;"],
                body=[*setup_lines, sink(tmp_var)],
            )
        fn_ctx_for_infer = _FnCtx(params=[], local_prefix="_")
        inferred = infer_type(value, fn_ctx_for_infer)
        expr = translator.translate(value, inferred)
        return self._guarded(field_name, declare=[], body=[sink(expr)])

    def _guarded(self, rule_id: str, declare: list[str], body: list[str]) -> list[str]:
        lines = ["DECLARE"] if declare else []
        lines.extend(_indent(declare))
        lines.append("BEGIN")
        lines.extend(_indent(body))
        lines.append("EXCEPTION")
        lines.append("    WHEN OTHERS THEN")
        lines.append(f"        IF NOT v_errors.EXISTS({_quote(rule_id)}) THEN")
        lines.append(f"            v_errors({_quote(rule_id)}) := SQLERRM;")
        lines.append("        END IF;")
        lines.append("END;")
        return lines

    def _emit_for(
        self,
        stmt: ast.For,
        loop_vars: list[str],
        rule_signatures: dict[str, _RuleSignature],
        dataclasses: dict[str, _DataclassDef],
        list_accumulators: dict[str, _ListAccumulator],
    ) -> list[str]:
        if not isinstance(stmt.target, ast.Name):
            raise CodeGenError("for-loop target must be a simple name")
        loop_var = stmt.target.id

        outer_ctx = _FlowCtx(loop_vars)
        outer_translator = _ExprTranslator(outer_ctx, rule_signatures, dataclasses, self.function_linker)
        source_expr = outer_translator.translate(stmt.iter, "ARRAY")

        idx = next(self._loop_counter)
        arr_var = f"v_forarr_{idx}"
        idx_var = f"v_i_{idx}"

        inner_lines = self._emit_flow(
            stmt.body, [*loop_vars, loop_var], rule_signatures, dataclasses, list_accumulators
        )

        lines = [
            "DECLARE",
            f"    {arr_var} JSON_ARRAY_T := {source_expr};",
            "BEGIN",
            f"    FOR {idx_var} IN 0 .. {arr_var}.get_size - 1 LOOP",
            "        DECLARE",
            f"            v_{loop_var} JSON_OBJECT_T := TREAT({arr_var}.get({idx_var}) AS JSON_OBJECT_T);",
            "        BEGIN",
        ]
        lines.extend(_indent(inner_lines, 3))
        lines.extend(["        END;", "    END LOOP;", "END;"])
        return lines

    @staticmethod
    def _is_out_append(call: ast.Call) -> bool:
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "append":
            return False
        base = call.func.value
        return (
            isinstance(base, ast.Attribute)
            and isinstance(base.value, ast.Name)
            and base.value.id == "out"
        )

    # -- rendering ----------------------------------------------------------

    def _render(
        self,
        mapping_id: str,
        function_texts: list[str],
        body_lines: list[str],
        list_accumulators: dict[str, _ListAccumulator],
    ) -> str:
        accumulator_decl_lines = [
            f"{acc.var_name} JSON_ARRAY_T := JSON_ARRAY_T();" for acc in list_accumulators.values()
        ]
        accumulator_put_lines = [
            f"v_out_obj.put({_quote(acc.field_name)}, {acc.var_name});"
            for acc in list_accumulators.values()
        ]

        shared_decls = "\n".join(
            [
                "v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);",
                "v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();",
                "TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);",
                "v_errors   t_error_map;",
                *accumulator_decl_lines,
            ]
        )

        body = "\n".join(body_lines)

        # Byte-budget-aware truncation (§Runtime error semantics: "20 entries,
        # or the byte budget ... whichever is hit first"). The M0.5 Oracle
        # spike found that neither `SQLERRM` (hard-capped at 512 bytes by
        # Oracle) nor `DBMS_UTILITY.FORMAT_ERROR_STACK` (observed ~1899 bytes
        # for a message > ~1970 bytes) truncate *cleanly* at a JSON boundary —
        # they just cut the character stream, corrupting the JSON. So this
        # generated code enforces the budget itself, before raising, by
        # measuring the candidate payload with LENGTHB and stopping before
        # the next entry would push it past `_ERROR_PAYLOAD_BYTE_BUDGET`.
        # Callers must read the message via `DBMS_UTILITY.FORMAT_ERROR_STACK`,
        # not bare `SQLERRM`, or they will still see it cut off at 512 bytes.
        raising_tail_lines = [
            "IF v_errors.COUNT > 0 THEN",
            "    DECLARE",
            "        v_err_arr   JSON_ARRAY_T := JSON_ARRAY_T();",
            "        v_err_obj   JSON_OBJECT_T;",
            "        v_key       VARCHAR2(200);",
            "        v_shown     PLS_INTEGER := 0;",
            "        v_payload   JSON_OBJECT_T := JSON_OBJECT_T();",
            "        v_base_len  PLS_INTEGER;",
            "        v_running_len PLS_INTEGER;",
            "    BEGIN",
            f"        v_payload.put('mapping', {_quote(mapping_id)});",
            "        v_payload.put('total_errors', v_errors.COUNT);",
            "        v_payload.put('shown', 0);",
            "        v_payload.put('errors', v_err_arr);",
            "        v_base_len := LENGTHB(v_payload.to_string());",
            "        v_running_len := v_base_len;",
            "        v_key := v_errors.FIRST;",
            "        WHILE v_key IS NOT NULL AND v_shown < 20 LOOP",
            "            v_err_obj := JSON_OBJECT_T();",
            "            v_err_obj.put('rule', v_key);",
            "            v_err_obj.put('cause', v_errors(v_key));",
            "            EXIT WHEN v_running_len + LENGTHB(v_err_obj.to_string()) + 1"
            f" > {_ERROR_PAYLOAD_BYTE_BUDGET};",
            "            v_err_arr.append(v_err_obj);",
            "            v_running_len := v_running_len + LENGTHB(v_err_obj.to_string()) + 1;",
            "            v_shown := v_shown + 1;",
            "            v_key := v_errors.NEXT(v_key);",
            "        END LOOP;",
            "        v_payload := JSON_OBJECT_T();",
            f"        v_payload.put('mapping', {_quote(mapping_id)});",
            "        v_payload.put('total_errors', v_errors.COUNT);",
            "        v_payload.put('shown', v_shown);",
            "        v_payload.put('errors', v_err_arr);",
            f"        RAISE_APPLICATION_ERROR({self.error_code}, v_payload.to_string());",
            "    END;",
            "END IF;",
            *accumulator_put_lines,
            "p_out := v_out_obj.TO_CLOB();",
        ]

        safe_tail_lines = [
            "DECLARE",
            "    v_err_arr JSON_ARRAY_T := JSON_ARRAY_T();",
            "    v_err_obj JSON_OBJECT_T;",
            "    v_key     VARCHAR2(200);",
            "BEGIN",
            "    v_key := v_errors.FIRST;",
            "    WHILE v_key IS NOT NULL LOOP",
            "        v_err_obj := JSON_OBJECT_T();",
            "        v_err_obj.put('rule', v_key);",
            "        v_err_obj.put('cause', v_errors(v_key));",
            "        v_err_arr.append(v_err_obj);",
            "        v_key := v_errors.NEXT(v_key);",
            "    END LOOP;",
            "    p_err := v_err_arr.to_clob();",
            "END;",
            *accumulator_put_lines,
            "p_out := v_out_obj.TO_CLOB();",
        ]

        raising_proc = (
            f"CREATE OR REPLACE PROCEDURE map_{mapping_id} (\n"
            "    p_src IN  CLOB,\n"
            "    p_out OUT CLOB\n"
            ") AS\n"
            f"{_indent_block(shared_decls)}\n"
            "BEGIN\n"
            f"{_indent_block(body)}\n\n"
            f"{_indent_block(chr(10).join(raising_tail_lines))}\n"
            f"END map_{mapping_id};\n/"
        )

        safe_proc = (
            f"CREATE OR REPLACE PROCEDURE map_{mapping_id}_safe (\n"
            "    p_src IN  CLOB,\n"
            "    p_out OUT CLOB,\n"
            "    p_err OUT CLOB\n"
            ") AS\n"
            f"{_indent_block(shared_decls)}\n"
            "BEGIN\n"
            f"{_indent_block(body)}\n\n"
            f"{_indent_block(chr(10).join(safe_tail_lines))}\n"
            f"END map_{mapping_id}_safe;\n/"
        )

        parts = [*function_texts, raising_proc, safe_proc]
        return "\n\n".join(parts) + "\n"


def _decl_type(expected_kind: str) -> str:
    return _EXPECTED_TO_DECL_TYPE.get(expected_kind, "JSON_OBJECT_T")


def _indent_block(text: str, level: int = 1) -> str:
    pad = "    " * level
    return "\n".join(pad + ln if ln else ln for ln in text.split("\n"))
