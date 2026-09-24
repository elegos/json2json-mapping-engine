"""Naive PL/SQL Code Generator — bootstrap mode, no Loop Fusion (M2a).

Emits the twin `map_<id>` / `map_<id>_safe` procedures described in
docs/ARCHITECTURE.md §Generated artifact / §Runtime error semantics.

Scope of this milestone (documented, not silently assumed):
- One PL/SQL nested `FUNCTION fn_<rule_id>` per field rule, called from a
  per-rule guarded block that accumulates (never fails fast) — §Runtime
  error semantics, "one rule = one function".
- "Omit field" (bare `return`) is implemented via a dedicated PL/SQL
  exception `e_field_omitted`, raised instead of returning a sentinel value;
  the call site catches it before `WHEN OTHERS` and simply skips the
  `.put()` call. This achieves the same observable three-way emission
  contract (§Return semantics) as the doc's illustrative two-flag snippet,
  via a different (simpler, idiomatic-PL/SQL) mechanism.
- Standalone `CREATE OR REPLACE PROCEDURE` per mapping, not yet wrapped in
  the `[target.plsql] package` — package assembly across multiple mapping
  files is a Build CLI (M3) concern.
- `for` loops over source arrays (and therefore Loop Fusion) are out of
  scope for this milestone — see M2b. Attempting to compile a module-level
  `for` raises `NotImplementedError` with a clear message.
- String sizing from JSON Schema `maxLength` is not wired up yet (no schema
  is passed into this backend at this milestone) — `str` fields default to
  a generic `VARCHAR2(4000 CHAR)`. `size_string_type` implements the actual
  M0-locked rule for when schema info is threaded through (M2b/M3).
- The RAISE_APPLICATION_ERROR payload truncates at 20 entries (§Runtime
  error semantics); the additional ~2048-byte budget truncation is not yet
  implemented — pending confirmation from the M0.5 Oracle spike of the
  exact byte math against a real instance.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from compiler.backends.base import CodeGenerator, FieldRule
from compiler.function_linker import FunctionLinker
from compiler.scope_resolver import Scope

# PL/SQL requires a VARCHAR2 *variable* declaration to carry a size (unlike
# a function RETURN type, which must NOT — see `_DSL_TO_PLSQL_RETURN` below).
_EXPECTED_TO_DECL_TYPE = {
    "VARCHAR2": "VARCHAR2(4000 CHAR)",
    "NUMBER": "NUMBER",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
}

# PL/SQL disallows size/scale constraints on a function's RETURN type
# (PLS-00263) — nested field-rule functions must declare an unconstrained
# type here even though the DSL type maps to a constrained one elsewhere.
_DSL_TO_PLSQL_RETURN = {
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

# Conservative target for the *entries* JSON, leaving margin under the
# ~1899-byte ceiling observed for `DBMS_UTILITY.FORMAT_ERROR_STACK` against a
# real Oracle 23ai instance (M0.5 spike) — see the comment at `raising_tail`.
_ERROR_PAYLOAD_BYTE_BUDGET = 1800


class CodeGenError(Exception):
    pass


def resolve_dsl_type(annotation: ast.expr) -> tuple[str, bool]:
    """Unwrap `T | None` / `T | Null` to (base DSL type name, nullable)."""
    nullable = False
    node = annotation
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left, right = node.left, node.right
        for side in (left, right):
            if (isinstance(side, ast.Constant) and side.value is None) or (
                isinstance(side, ast.Name) and side.id == "Null"
            ):
                nullable = True
        non_null = [
            s
            for s in (left, right)
            if not (isinstance(s, ast.Constant) and s.value is None)
            and not (isinstance(s, ast.Name) and s.id == "Null")
        ]
        if len(non_null) != 1:
            raise CodeGenError("unsupported union annotation")
        node = non_null[0]
    if not isinstance(node, ast.Name):
        raise CodeGenError(f"unsupported type annotation: {ast.dump(node)}")
    return node.id, nullable


@dataclass
class _Ctx:
    scope: Scope
    local_prefix: str
    function_linker: FunctionLinker
    locals: dict[str, str] = field(default_factory=dict)  # name -> PL/SQL type
    declarations: list[str] = field(default_factory=list)


def _quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


class _ExprTranslator:
    def __init__(self, ctx: _Ctx):
        self.ctx = ctx

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
        if name == "root":
            return "v_srcroot"
        if name == "src":
            scope = self.ctx.scope
            if scope.loop_var is None:
                raise CodeGenError("`src` used outside a loop")
            return f"v_{scope.loop_var}"
        bound = self.ctx.scope.resolve_name(name)
        if bound is not None:
            return f"v_{name}"
        if name in self.ctx.locals:
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
            if isinstance(side, ast.Constant) and isinstance(side.value, (int, float)) and not isinstance(
                side.value, bool
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
        impl = self.ctx.function_linker.resolve(node.func.id)
        args = [self.translate(a, expected) for a in node.args]
        return impl.render("plsql", args)


def infer_type(node: ast.expr, ctx: _Ctx) -> str:
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
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "coalesce":
        return infer_type(node.args[0], ctx)
    if isinstance(node, ast.Name) and node.id in ctx.locals:
        return ctx.locals[node.id]
    return "VARCHAR2"


def _indent(lines: list[str], level: int = 1) -> list[str]:
    pad = "    " * level
    return [pad + ln for ln in lines]


def _translate_body(stmts: list[ast.stmt], ctx: _Ctx, return_expected: str) -> list[str]:
    translator = _ExprTranslator(ctx)
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
                out.append("RAISE e_field_omitted;")
            elif isinstance(stmt.value, ast.Name) and stmt.value.id == "Null":
                out.append("RETURN NULL;")
            else:
                out.append(f"RETURN {translator.translate(stmt.value, return_expected)};")
        elif isinstance(stmt, ast.If):
            out.extend(_translate_if(stmt, ctx, return_expected, translator))
        else:
            raise CodeGenError(f"unsupported statement in field-rule body: {type(stmt).__name__}")
    return out


def _translate_if(
    stmt: ast.If, ctx: _Ctx, return_expected: str, translator: _ExprTranslator
) -> list[str]:
    lines = [f"IF {translator.translate(stmt.test, 'BOOLEAN')} THEN"]
    lines.extend(_indent(_translate_body(stmt.body, ctx, return_expected)))
    orelse = stmt.orelse
    while len(orelse) == 1 and isinstance(orelse[0], ast.If):
        elif_stmt = orelse[0]
        lines.append(f"ELSIF {translator.translate(elif_stmt.test, 'BOOLEAN')} THEN")
        lines.extend(_indent(_translate_body(elif_stmt.body, ctx, return_expected)))
        orelse = elif_stmt.orelse
    if orelse:
        lines.append("ELSE")
        lines.extend(_indent(_translate_body(orelse, ctx, return_expected)))
    lines.append("END IF;")
    return lines


@dataclass
class _CompiledRule:
    id: str
    plsql_return_type: str
    function_text: str
    out_field: str


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
        return "\n".join(
            [
                "BEGIN",
                f"    v_out_obj.put({_quote(out_field)}, fn_{rule.id}());",
                "EXCEPTION",
                "    WHEN e_field_omitted THEN",
                "        NULL;",
                "    WHEN OTHERS THEN",
                f"        IF NOT v_errors.EXISTS({_quote(rule.id)}) THEN",
                f"            v_errors({_quote(rule.id)}) := SQLERRM;",
                "        END IF;",
                "END;",
            ]
        )

    def emit_loop(self, loop_var: str, source_expr: str, body: str) -> str:
        raise NotImplementedError(
            "for-loops over source arrays are out of scope for M2a (naive, "
            "no-fusion codegen) — see M2b Loop Fusion Optimizer"
        )

    def emit_procedure_pair(
        self, mapping_id: str, declarations: str, body: str, error_code: int
    ) -> str:
        raise NotImplementedError("use compile_module — kept for interface completeness")

    # -- module compilation -----------------------------------------------

    def compile_module(self, tree: ast.Module, mapping_id: str, scope_resolution) -> str:
        root_scope = scope_resolution.root_scope
        rule_defs: dict[str, ast.FunctionDef] = {}
        assignments: list[ast.Assign] = []

        for stmt in tree.body:
            if isinstance(stmt, ast.ImportFrom):
                continue
            if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
                continue  # __id__ directive, already handled by the caller
            if isinstance(stmt, ast.FunctionDef):
                rule_defs[stmt.name] = stmt
                continue
            if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute):
                assignments.append(stmt)
                continue
            raise NotImplementedError(
                f"module-level {type(stmt).__name__} is out of scope for M2a "
                "(naive, no-fusion codegen)"
            )

        compiled: list[_CompiledRule] = []

        for assign in assignments:
            target = assign.targets[0]
            assert isinstance(target, ast.Attribute)
            if not (isinstance(target.value, ast.Name) and target.value.id == "out"):
                raise CodeGenError("only `out.<field> = ...` assignments are supported")
            out_field = target.attr
            value = assign.value

            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in rule_defs
                and not value.args
            ):
                fn_def = rule_defs[value.func.id]
                rule_id = fn_def.name
                if fn_def.returns is None:
                    raise CodeGenError(f"function '{rule_id}' is missing a return annotation")
                base_type, _nullable = resolve_dsl_type(fn_def.returns)
                return_expected = _DSL_TO_EXPECTED.get(base_type, "VARCHAR2")
                ctx = _Ctx(scope=root_scope, local_prefix=rule_id, function_linker=self.function_linker)
                body_lines = _translate_body(fn_def.body, ctx, return_expected)
                decls = "\n    ".join(ctx.declarations)
                plsql_type = _DSL_TO_PLSQL_RETURN.get(base_type, "VARCHAR2")
                fn_text = (
                    f"FUNCTION fn_{rule_id} RETURN {plsql_type} IS\n"
                    f"    {decls}\n" if decls else f"FUNCTION fn_{rule_id} RETURN {plsql_type} IS\n"
                )
                fn_text += "BEGIN\n" + "\n".join(_indent(body_lines)) + f"\nEND fn_{rule_id};"
            else:
                rule_id = out_field
                ctx = _Ctx(scope=root_scope, local_prefix=rule_id, function_linker=self.function_linker)
                inferred = infer_type(value, ctx)
                translator = _ExprTranslator(ctx)
                expr_text = translator.translate(value, inferred)
                plsql_type = {
                    "VARCHAR2": "VARCHAR2",
                    "NUMBER": "NUMBER",
                    "BOOLEAN": "BOOLEAN",
                    "DATE": "DATE",
                    "TIMESTAMP": "TIMESTAMP",
                }[inferred]
                fn_text = (
                    f"FUNCTION fn_{rule_id} RETURN {plsql_type} IS\n"
                    "BEGIN\n"
                    f"    RETURN {expr_text};\n"
                    f"END fn_{rule_id};"
                )

            compiled.append(
                _CompiledRule(
                    id=rule_id, plsql_return_type=plsql_type, function_text=fn_text, out_field=out_field
                )
            )

        return self._render_procedure_pair(mapping_id, compiled)

    # -- rendering ----------------------------------------------------------

    def _render_procedure_pair(self, mapping_id: str, rules: list[_CompiledRule]) -> str:
        nested_functions = "\n\n".join(r.function_text for r in rules)
        guard_blocks = "\n\n".join(
            self.emit_field_guard(FieldRule(id=r.id, return_type=r.plsql_return_type, body=""), r.out_field)
            for r in rules
        )

        shared_decls = "\n".join(
            [
                "v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);",
                "v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();",
                "TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);",
                "v_errors   t_error_map;",
                "e_field_omitted EXCEPTION;",
                "",
                _indent_block(nested_functions),
            ]
        )

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
        raising_tail = "\n".join(
            [
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
                "p_out := v_out_obj.TO_CLOB();",
            ]
        )

        safe_tail = "\n".join(
            [
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
                "p_out := v_out_obj.TO_CLOB();",
            ]
        )

        raising_proc = (
            f"CREATE OR REPLACE PROCEDURE map_{mapping_id} (\n"
            "    p_src IN  CLOB,\n"
            "    p_out OUT CLOB\n"
            ") AS\n"
            f"{_indent_block(shared_decls)}\n"
            "BEGIN\n"
            f"{_indent_block(guard_blocks)}\n\n"
            f"{_indent_block(raising_tail)}\n"
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
            f"{_indent_block(guard_blocks)}\n\n"
            f"{_indent_block(safe_tail)}\n"
            f"END map_{mapping_id}_safe;\n/"
        )

        return raising_proc + "\n\n" + safe_proc + "\n"


def _indent_block(text: str, level: int = 1) -> str:
    pad = "    " * level
    return "\n".join(pad + ln if ln else ln for ln in text.split("\n"))
