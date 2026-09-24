"""Type Checker (docs/ARCHITECTURE.md, §Compiler components, §Input/Output
type contracts).

Runs after the Scope Resolver, before the Function Linker / Code Generator.
Target-agnostic: works purely off the DSL type vocabulary and the
structured `SchemaTypes` produced by the Schema Generator (M1) — no
PL/SQL-specific knowledge here.

- **Reads** (`root.x`, `src.x`, or a loop-var chain) are validated against
  the input `SchemaTypes`, walking the class graph one attribute at a time.
  Without an input schema, every read is `Any` — unchecked, per §Input type
  contract.
- **Writes** (`out.<field> = ...`) are validated against the output
  `SchemaTypes`'s root class: the field must be declared, and the assigned
  expression's inferred DSL type must be compatible (same base type; a
  required non-nullable field cannot be fed by a rule whose return
  annotation includes `None`/`Null`). Without an output schema, every write
  is accepted as-is, per §Output type contract.
- **Required-field coverage** (§Output type contract, point 1) is checked
  once per module: every `required` field of the output root class must
  have at least one `out.<field> = ...` assignment somewhere in the module.

Scope: flat (module-level and single-loop-level) `out.<field>` writes only,
matching what the M2a/M2b Code Generator actually compiles — nested
`object`/`loop` output writes will extend this once nested codegen exists.
A union of classes (`oneOf`/`anyOf` alternatives) is only readable one level
further if the accessed field exists on *every* alternative (conservative:
no narrowing construct exists in the permitted subset to disambiguate).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from compiler.annotations import AnnotationError, resolve_dsl_type
from compiler.schema_generator import SchemaTypes
from compiler.scope_resolver import Scope, ScopeResolution

ANY = "Any"

_SCALAR_TYPES = {"str", "int", "number", "bool", "date", "datetime"}


class TypeCheckError(Exception):
    pass


def _strip_none(type_expr: str) -> tuple[list[str], bool]:
    parts = [p.strip() for p in type_expr.split("|")]
    nullable = "None" in parts or "Null" in parts
    remaining = [p for p in parts if p not in ("None", "Null")]
    return remaining, nullable


@dataclass
class _ExprTypeChecker:
    input_schema: SchemaTypes | None
    output_schema: SchemaTypes | None
    scope_type: dict[int, str]  # id(Scope) -> class name or ANY
    rule_defs: dict[str, ast.FunctionDef]

    # -- reads --------------------------------------------------------------

    def type_of(self, node: ast.expr, scope: Scope) -> str:
        """Resolve the DSL type of a read expression rooted at `root`/`src`/
        a loop var. Returns a schema class name, a scalar DSL type name
        (possibly `"T | None"`), `"list[X]"`, or `ANY`."""
        if isinstance(node, ast.Name):
            if node.id == "root":
                return self.input_schema.root_type if self.input_schema else ANY
            if node.id == "src":
                bound = scope
                if bound.loop_var is None:
                    raise TypeCheckError("`src` used outside a loop")
                return self.scope_type.get(id(bound), ANY)
            bound_scope = scope.resolve_name(node.id)
            if bound_scope is not None:
                return self.scope_type.get(id(bound_scope), ANY)
            return ANY  # local variable — untracked here, Code Generator infers it
        if isinstance(node, ast.Attribute):
            base_type = self.type_of(node.value, scope)
            return self._attr_type(base_type, node.attr)
        return ANY

    def type_of_in_function(self, node: ast.expr, param_types: dict[str, str]) -> str:
        """Like `type_of`, but for reads *inside a rule function's own
        body* — functions take explicit parameters and have no implicit
        access to the caller's `root`/`src`/loop scope (§codegen module
        docstring's calling convention), so resolution is purely by
        declared parameter name, not by scope chain."""
        if isinstance(node, ast.Name):
            return param_types.get(node.id, ANY)
        if isinstance(node, ast.Attribute):
            base_type = self.type_of_in_function(node.value, param_types)
            return self._attr_type(base_type, node.attr)
        return ANY

    def _attr_type(self, base_type: str, attr: str) -> str:
        if base_type == ANY or self.input_schema is None:
            return ANY
        candidates, _nullable = _strip_none(base_type)
        if len(candidates) > 1:
            # Union of classes — require the field on every alternative.
            resolved = {self._field_type(c, attr) for c in candidates}
            if len(resolved) != 1:
                raise TypeCheckError(
                    f"field '{attr}' is not consistently present on every "
                    f"alternative of '{base_type}'"
                )
            return next(iter(resolved))
        return self._field_type(candidates[0], attr)

    def _field_type(self, class_name: str, attr: str) -> str:
        if class_name == "JsonObj":
            return ANY
        cls = (self.input_schema.classes if self.input_schema else {}).get(class_name)
        if cls is None:
            if class_name in _SCALAR_TYPES or class_name.startswith("list["):
                raise TypeCheckError(f"cannot access field '{attr}' on scalar type '{class_name}'")
            raise TypeCheckError(f"unknown type '{class_name}'")
        for f in cls.fields:
            if f.name == attr:
                return f.type_expr
        raise TypeCheckError(f"field '{attr}' does not exist on type '{class_name}'")

    # -- DSL type inference for produced values (mirrors codegen's infer_type,
    # but at the DSL-type-name level, and schema-aware for attribute reads) --

    def infer_produced_type(self, node: ast.expr, scope: Scope) -> tuple[str, bool]:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "bool", False
            if isinstance(node.value, int):
                return "int", False
            if isinstance(node.value, float):
                return "number", False
            if node.value is None:
                return "Any", True
            return "str", False
        if isinstance(node, ast.Name) and node.id == "Null":
            return "Any", True
        if isinstance(node, ast.BinOp):
            return "number", False
        if isinstance(node, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
            return "bool", False
        if isinstance(node, ast.IfExp):
            return self.infer_produced_type(node.body, scope)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fname = node.func.id
            if fname == "coalesce":
                _t, _n = self.infer_produced_type(node.args[0], scope)
                return _t, False  # coalesce's whole point is resolving away nullability
            if fname == "if_else":
                return self.infer_produced_type(node.args[1], scope)
            if fname == "round":
                return "number", False
            if fname == "parse_date":
                return "date", False
            if fname in ("concat", "split_first"):
                return "str", False
            if fname in ("split_nth", "lookup"):
                return "str", True
            if fname == "count":
                return "int", False
            if fname in ("max", "min", "sum", "avg"):
                # Never null/omit — an aggregate over an (empty-or-not)
                # array always produces a value (max/min/avg over an empty
                # array is a runtime concern, not a static nullability one —
                # same stance codegen takes).
                return "number", False
            return ANY, True
        if isinstance(node, (ast.Name, ast.Attribute)):
            resolved = self.type_of(node, scope)
            if resolved == ANY:
                return ANY, True
            base, nullable = _strip_none(resolved)
            return (base[0] if len(base) == 1 else " | ".join(base)), nullable
        return ANY, True


def _base_type_from_rule(fn_def: ast.FunctionDef) -> tuple[str, bool]:
    if fn_def.returns is None:
        raise TypeCheckError(f"function '{fn_def.name}' is missing a return annotation")
    try:
        return resolve_dsl_type(fn_def.returns)
    except AnnotationError as exc:
        raise TypeCheckError(str(exc)) from exc


def check_module(
    tree: ast.Module,
    scope_resolution: ScopeResolution,
    input_schema: SchemaTypes | None = None,
    output_schema: SchemaTypes | None = None,
) -> None:
    root_scope = scope_resolution.root_scope
    scope_type: dict[int, str] = {}
    if input_schema is not None:
        scope_type[id(root_scope)] = input_schema.root_type
    else:
        scope_type[id(root_scope)] = ANY

    rule_defs = {
        stmt.name: stmt for stmt in ast.walk(tree) if isinstance(stmt, ast.FunctionDef)
    }
    checker = _ExprTypeChecker(input_schema, output_schema, scope_type, rule_defs)

    # Resolve each loop's element type from its (already scope-resolved)
    # source expression, walking outer-to-inner so parent types are ready.
    for _for_node, scope in sorted(
        scope_resolution.for_scopes.items(), key=lambda kv: kv[1].depth
    ):
        parent_scope = scope.parent or root_scope
        assert scope.source_expr is not None  # always set for a for-loop scope
        source_type = checker.type_of(scope.source_expr, parent_scope)
        if source_type == ANY:
            scope_type[id(scope)] = ANY
            continue
        candidates, _nullable = _strip_none(source_type)
        if len(candidates) != 1 or not candidates[0].startswith("list["):
            raise TypeCheckError(
                f"loop source does not resolve to an array type (got '{source_type}')"
            )
        scope_type[id(scope)] = candidates[0][len("list[") : -1]

    assigned_fields: set[str] = set()
    _walk_body(
        tree.body, root_scope, scope_resolution, checker, rule_defs, output_schema, assigned_fields
    )

    if output_schema is not None:
        root_cls = output_schema.classes[output_schema.root_type]
        missing = [f.name for f in root_cls.fields if f.required and f.name not in assigned_fields]
        if missing:
            raise TypeCheckError(
                f"required output field(s) not assigned: {', '.join(missing)}"
            )


def _walk_body(
    stmts: list[ast.stmt],
    scope: Scope,
    scope_resolution: ScopeResolution,
    checker: _ExprTypeChecker,
    rule_defs: dict[str, ast.FunctionDef],
    output_schema: SchemaTypes | None,
    assigned_fields: set[str],
) -> None:
    for stmt in stmts:
        if isinstance(stmt, ast.FunctionDef):
            _check_def_reads(stmt, checker)
            continue
        if isinstance(stmt, ast.For):
            inner_scope = scope_resolution.for_scopes[id(stmt)]
            _walk_body(
                stmt.body, inner_scope, scope_resolution, checker, rule_defs, output_schema,
                assigned_fields,
            )
            continue
        if isinstance(stmt, ast.If):
            # Loop Fusion (compiler/loop_fusion.py) normalizes `if cond:
            # continue` filters into `IF NOT (cond): <rest>` guards — the
            # writes inside still need checking/coverage-counting.
            _check_reads_in_expr(stmt.test, checker, scope)
            _walk_body(
                stmt.body, scope, scope_resolution, checker, rule_defs, output_schema,
                assigned_fields,
            )
            _walk_body(
                stmt.orelse, scope, scope_resolution, checker, rule_defs, output_schema,
                assigned_fields,
            )
            continue
        if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute):
            target = stmt.targets[0]
            if isinstance(target.value, ast.Name) and target.value.id == "out":
                field_name = target.attr
                assigned_fields.add(field_name)
                _check_write(field_name, stmt.value, checker, scope, rule_defs, output_schema)
            _check_reads_in_expr(stmt.value, checker, scope)
            continue
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Attribute)
            and stmt.value.func.attr == "append"
            and isinstance(stmt.value.func.value, ast.Attribute)
            and isinstance(stmt.value.func.value.value, ast.Name)
            and stmt.value.func.value.value.id == "out"
        ):
            field_name = stmt.value.func.value.attr
            assigned_fields.add(field_name)
            if stmt.value.args:
                _check_write(
                    field_name, stmt.value.args[0], checker, scope, rule_defs, output_schema,
                    unwrap_list=True,
                )
                _check_reads_in_expr(stmt.value.args[0], checker, scope)


def _check_def_reads(fn_def: ast.FunctionDef, checker: _ExprTypeChecker) -> None:
    param_types: dict[str, str] = {}
    for a in fn_def.args.args:
        type_name = a.annotation.id if isinstance(a.annotation, ast.Name) else None
        if (
            type_name is not None
            and checker.input_schema is not None
            and type_name in checker.input_schema.classes
        ):
            param_types[a.arg] = type_name
        else:
            param_types[a.arg] = ANY  # scalar DSL type, "Any", or unrecognized — unchecked

    for body_stmt in fn_def.body:
        for node in ast.walk(body_stmt):
            if isinstance(node, ast.Attribute):
                checker.type_of_in_function(node, param_types)


def _check_reads_in_expr(node: ast.expr, checker: _ExprTypeChecker, scope: Scope) -> None:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute):
            checker.type_of(sub, scope)


def _check_write(
    field_name: str,
    value: ast.expr,
    checker: _ExprTypeChecker,
    scope: Scope,
    rule_defs: dict[str, ast.FunctionDef],
    output_schema: SchemaTypes | None,
    unwrap_list: bool = False,
) -> None:
    if output_schema is None:
        return
    root_cls = output_schema.classes[output_schema.root_type]
    declared = next((f for f in root_cls.fields if f.name == field_name), None)
    if declared is None:
        raise TypeCheckError(f"assignment to undeclared output field 'out.{field_name}'")
    declared_type_expr = declared.type_expr
    if unwrap_list:
        bases, _ = _strip_none(declared_type_expr)
        list_bases = [b[len("list[") : -1] for b in bases if b.startswith("list[")]
        if not list_bases:
            raise TypeCheckError(
                f"'.append(...)' used on 'out.{field_name}', declared as "
                f"'{declared_type_expr}' — not a list type"
            )
        declared_type_expr = list_bases[0]
    declared_bases, declared_nullable = _strip_none(declared_type_expr)

    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in rule_defs
    ):
        produced_base, produced_nullable = _base_type_from_rule(rule_defs[value.func.id])
    else:
        produced_base, produced_nullable = checker.infer_produced_type(value, scope)

    if produced_base != ANY and produced_base not in declared_bases:
        raise TypeCheckError(
            f"field 'out.{field_name}' declared as '{declared.type_expr}' but the "
            f"assigned rule produces '{produced_base}'"
        )
    if produced_nullable and not declared_nullable:
        raise TypeCheckError(
            f"field 'out.{field_name}' is required and non-nullable but the assigned "
            f"rule may produce null/omit"
        )
