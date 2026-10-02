"""A checked mapping (`.map.py` tree) -> a Python module.

The mapping is already Python, so the module is the same tree rewritten for the run-time
rules of `runtime.py`: paths through the input become `_get` calls (null where something is
missing), arithmetic and ordering propagate null, a call of a rule function goes through
`_rule` (which isolates its failures), a dataclass becomes `_record`, and the statements of the
mapping body become `_run(root, out)`. Types are annotations only: they are dropped.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from compiler.backends.base import CodeGenError, CompiledUnit
from compiler.function_registry import FunctionInfo

_ARITH = {
    ast.Add: "_add",
    ast.Sub: "_sub",
    ast.Mult: "_mul",
    ast.Div: "_div",
    ast.FloorDiv: "_floordiv",
    ast.Mod: "_mod",
}
_ORDER = {ast.Lt: "_lt", ast.LtE: "_le", ast.Gt: "_gt", ast.GtE: "_ge"}


@dataclass
class PythonUnit(CompiledUnit):
    """One compiled mapping: the text of its module and what was learned compiling it."""

    mapping_id: str
    source: str
    rules: list[str] = field(default_factory=list)
    parallel: dict[str, int] = field(default_factory=dict)  # rule -> @parallel degree
    # rule function -> the project functions it calls that have no code for Python: the rule
    # cannot run here, and says so instead of failing for a reason of its own
    unavailable: dict[str, list[str]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "mapping_id": self.mapping_id,
            "source": self.source,
            "rules": self.rules,
            "parallel": self.parallel,
            "unavailable": self.unavailable,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PythonUnit:
        return cls(
            data["mapping_id"],
            data["source"],
            data["rules"],
            data["parallel"],
            data.get("unavailable", {}),
        )


def _name(identifier: str) -> ast.Name:
    return ast.Name(id=identifier, ctx=ast.Load())


def _call(function: str, *args: ast.expr, keywords: list[ast.keyword] | None = None) -> ast.Call:
    return ast.Call(func=_name(function), args=list(args), keywords=keywords or [])


def _is_dataclass(node: ast.ClassDef) -> bool:
    return any(isinstance(d, ast.Name) and d.id == "dataclass" for d in node.decorator_list)


class _Rewriter(ast.NodeTransformer):
    def __init__(self, rules: set[str], dataclasses: set[str]):
        self.rules = rules
        self.dataclasses = dataclasses

    # -- declarations ------------------------------------------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.decorator_list = []
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None
        self.generic_visit(node)
        return node

    def visit_Return(self, node: ast.Return) -> ast.Return:
        if node.value is None:
            node.value = _name("OMIT")
        else:
            node.value = self.visit(node.value)
        return node

    def visit_Name(self, node: ast.Name) -> ast.expr:
        if node.id == "Null":
            return ast.Constant(value=None)
        return node

    # -- reading the input -------------------------------------------------------------
    def _chain(self, node: ast.expr) -> tuple[ast.expr, list[ast.expr]]:
        """`a.b[0].c` -> (a, ['b', 0, 'c'] as expressions)."""
        steps: list[ast.expr] = []
        while isinstance(node, ast.Attribute | ast.Subscript):
            if isinstance(node, ast.Attribute):
                steps.append(ast.Constant(value=node.attr))
                node = node.value
            else:
                if isinstance(node.slice, ast.Slice):
                    raise CodeGenError("slices are not supported in a path")
                steps.append(self.visit(node.slice))
                node = node.value
        return node, steps[::-1]

    def _path(self, node: ast.Attribute | ast.Subscript) -> ast.expr:
        base, steps = self._chain(node)
        if isinstance(base, ast.Name) and base.id == "out":
            if isinstance(node, ast.Attribute) and node.value is base:
                return node  # `out.F`: a field to set, or the array to append to
            raise CodeGenError("`out` can only be assigned a field or have one appended to")
        if not isinstance(node.ctx, ast.Load):
            raise CodeGenError("only fields of `out` can be assigned")
        return _call("_get", self.visit(base), *steps)

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        return self._path(node)

    def visit_Subscript(self, node: ast.Subscript) -> ast.expr:
        return self._path(node)

    # -- operators ---------------------------------------------------------------------
    def visit_BinOp(self, node: ast.BinOp) -> ast.expr:
        helper = _ARITH.get(type(node.op))
        if helper is None:
            raise CodeGenError(f"operator {type(node.op).__name__} is not supported")
        return _call(helper, self.visit(node.left), self.visit(node.right))

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.expr:
        if isinstance(node.op, ast.USub):
            return _call("_neg", self.visit(node.operand))
        return self.generic_visit(node)  # type: ignore[return-value]

    def visit_Compare(self, node: ast.Compare) -> ast.expr:
        if len(node.ops) == 1 and type(node.ops[0]) in _ORDER:
            return _call(
                _ORDER[type(node.ops[0])], self.visit(node.left), self.visit(node.comparators[0])
            )
        return self.generic_visit(node)  # type: ignore[return-value]

    # -- calls and loops ---------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> ast.expr:
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in self.dataclasses:
                if node.args:
                    raise CodeGenError(f"'{func.id}(...)' construction requires keyword arguments")
                keywords = [
                    ast.keyword(arg=k.arg, value=self.visit(k.value)) for k in node.keywords
                ]
                return _call("_record", keywords=keywords)
            if func.id in self.rules:
                if node.keywords:
                    raise CodeGenError(f"rule '{func.id}' is called with positional arguments")
                return _call(
                    "_rule", ast.Constant(value=func.id), func, *[self.visit(a) for a in node.args]
                )
        elif isinstance(func, ast.Attribute) and func.attr == "append" and len(node.args) == 1:
            return _call("_append", self.visit(func.value), self.visit(node.args[0]))
        elif isinstance(func, ast.Attribute):
            raise CodeGenError(f"method call .{func.attr}(...) is not supported")
        return self.generic_visit(node)  # type: ignore[return-value]

    def visit_For(self, node: ast.For) -> ast.For:
        node.iter = _call("_each", self.visit(node.iter))
        node.body = [self.visit(s) for s in node.body]
        node.orelse = [self.visit(s) for s in node.orelse]
        return node


def _parallel_degree(node: ast.FunctionDef) -> int | None:
    for dec in node.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "parallel"
        ):
            for kw in dec.keywords:
                if (
                    kw.arg == "degree"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, int)
                ):
                    return kw.value.value
    return None


def _output_arrays(statements: list[ast.stmt]) -> list[str]:
    """The fields of `out` the mapping body appends to: their arrays exist even when empty."""
    found: list[str] = []
    for stmt in statements:
        for node in ast.walk(stmt):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "out"
                and node.func.value.attr not in found
            ):
                found.append(node.func.value.attr)
    return found


def _called_names(node: ast.AST) -> set[str]:
    return {
        n.func.id
        for n in ast.walk(node)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }


def _function(source: str) -> ast.FunctionDef:
    (function,) = ast.parse(source).body
    assert isinstance(function, ast.FunctionDef)
    return function


def _without_annotations(source: str) -> ast.FunctionDef:
    """A project function's code as it runs here: the types are for the checker, and names such
    as `number` or `Null` in them would not exist in the module."""
    function = _function(source)
    function.returns = None
    for arg in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]:
        arg.annotation = None
    for arg in (function.args.vararg, function.args.kwarg):
        if arg is not None:
            arg.annotation = None
    return function


def _project_definitions(
    tree: ast.Module, project: dict[str, FunctionInfo]
) -> tuple[list[ast.FunctionDef], set[str]]:
    """The project functions the mapping calls (and those they call), as definitions for the
    module; and the names among them that have no code for Python (they raise when called)."""
    definitions: list[ast.FunctionDef] = []
    missing: set[str] = set()
    pending = sorted(_called_names(tree) & set(project))
    done: set[str] = set()
    while pending:
        name = pending.pop(0)
        if name in done:
            continue
        done.add(name)
        info = project[name]
        if "python" in info.overrides:
            names = [p.name for p in info.params if not p.variadic]
            body = info.overrides["python"].format(**{n: n for n in names})
            definition = _function(f"def {name}({', '.join(names)}):\n    return {body}\n")
        elif info.python_code:
            definition = _without_annotations(info.source)
            pending += sorted((_called_names(definition) & set(project)) - done)
        else:
            missing.add(name)
            definition = _function(
                f"def {name}(*args, **kwargs):\n    raise MissingImplementation({name!r})\n"
            )
        definitions.append(definition)
    return definitions, missing


def compile_module(
    tree: ast.Module, mapping_id: str, project: dict[str, FunctionInfo] | None = None
) -> PythonUnit:
    functions: list[ast.FunctionDef] = []
    body: list[ast.stmt] = []
    dataclasses: set[str] = set()
    parallel: dict[str, int] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef):
            if _is_dataclass(stmt):
                dataclasses.add(stmt.name)
        elif isinstance(stmt, ast.FunctionDef):
            functions.append(stmt)
        elif isinstance(stmt, ast.ImportFrom) or (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "__id__"
        ):
            continue
        else:
            body.append(stmt)
    rules = {f.name for f in functions}
    for f in functions:
        degree = _parallel_degree(f)
        if degree is not None:
            parallel[f.name] = degree

    rewriter = _Rewriter(rules, dataclasses)
    project_defs, missing = _project_definitions(tree, project or {})
    new_functions = [*project_defs, *(rewriter.visit(f) for f in functions)]
    unavailable = {
        f.name: sorted(_called_names(f) & missing) for f in functions if _called_names(f) & missing
    }
    arrays = [
        ast.Expr(value=ast.Attribute(value=_name("out"), attr=name, ctx=ast.Load()))
        for name in _output_arrays(body)
    ]
    run_body: list[ast.stmt] = [*arrays, *(rewriter.visit(s) for s in body)] or [ast.Pass()]
    run = ast.FunctionDef(
        name="_run",
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg="root"), ast.arg(arg="out")],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=run_body,
        decorator_list=[],
        returns=None,
        type_params=[],
    )
    entry = ast.parse(
        f"def map_{mapping_id}(source):\n"
        f"    return _execute({mapping_id!r}, _run, source, True)[0]\n\n\n"
        f"def map_{mapping_id}_safe(source):\n"
        f"    return _execute({mapping_id!r}, _run, source, False)\n"
    ).body
    module = ast.Module(body=[*new_functions, run, *entry], type_ignores=[])
    ast.fix_missing_locations(module)
    header = (
        f"# Generated by `mapper` for the mapping {mapping_id!r} — do not edit.\n"
        "from j2jme_runtime import *\n\n\n"
    )
    return PythonUnit(
        mapping_id, header + ast.unparse(module) + "\n", sorted(rules), parallel, unavailable
    )
