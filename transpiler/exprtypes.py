"""Types of a functional expression, checked against what its context expects (M6.1b).

The type of an expression is inferred bottom-up (literals, operators, references read from
the input schema, the result of a built-in) and each place that *uses* a value states what
it expects: a built-in's parameter, an operand, the field the expression feeds. Expectations
flow down, so `round(lookup($.c, $.t))` into an `int` field is checked at every step: the
values of `$.t` against what `round` accepts, and what `round` returns against `int`.

Types are sets of JSON Schema type names, so they compare with the schemas as they are:
`{"string"}`, `{"integer"}`, `{"number"}`, `{"boolean"}`. An expected `number` accepts
`{"number", "integer"}`. `None` means "cannot tell" (no schema, a project function, an
unfollowed construct) and is compatible with everything: only clear contradictions are
reported. Only single-expression rules are typed; blocks with statements are left alone.
"""

from __future__ import annotations

import ast
import builtins
import textwrap
from collections.abc import Callable, Collection, Mapping
from typing import Any

from compiler.function_registry import FunctionInfo, builtin_functions

Ty = frozenset[str] | None

STRING: frozenset[str] = frozenset({"string"})
INTEGER: frozenset[str] = frozenset({"integer"})
NUMBER: frozenset[str] = frozenset({"number"})  # what a value that may have decimals is
NUMERIC: frozenset[str] = frozenset({"number", "integer"})  # what a numeric parameter accepts
BOOLEAN: frozenset[str] = frozenset({"boolean"})
SCALAR: frozenset[str] = frozenset({"string", "number", "integer", "boolean"})

_STR_METHODS = {
    "strip", "lstrip", "rstrip", "upper", "lower", "title", "capitalize", "replace", "format",
    "zfill", "ljust", "rjust",
}  # fmt: skip
_CASTS: dict[str, Ty] = {"str": STRING, "int": INTEGER, "float": NUMBER, "bool": BOOLEAN}


def annotation_type(text: str, *, parameter: bool) -> Ty:
    """The type set of a parameter / return annotation of a registered function; `None` when
    it says nothing (`Any`, no annotation). A numeric parameter accepts integers."""
    names = {n.strip() for n in text.split("|")} - {"None", ""}
    if not names or "Any" in names:
        return None
    found: set[str] = set()
    for n in names:
        if n in ("str", "date", "datetime"):
            found.add("string")
        elif n == "int":
            found.add("integer")
        elif n == "float":
            found |= {"number", "integer"} if parameter else {"number"}
        elif n == "bool":
            found.add("boolean")
        elif n.startswith(("list[", "list")):
            found.add("array")
        else:
            return None
    return frozenset(found)


def signature_table(
    functions: Mapping[str, FunctionInfo],
) -> dict[str, tuple[tuple[Ty, ...], Ty]]:
    """name -> (parameter expectations, returns) for the functions typed by their annotations;
    the `@special` built-ins (typed by hand in `_call`) are not in it."""
    table: dict[str, tuple[tuple[Ty, ...], Ty]] = {}
    for info in functions.values():
        if info.special:
            continue
        params = tuple(annotation_type(p.annotation, parameter=True) for p in info.params)
        table[info.name] = (params, annotation_type(info.returns, parameter=False))
    return table


_BUILTINS = builtin_functions()
# the built-ins as the registry (`compiler/builtins.py`) says
SIGNATURES = signature_table(_BUILTINS)
HANDLED = {name for name, info in _BUILTINS.items() if info.special}


def describe(ty: Ty) -> str:
    return "/".join(sorted(ty)) if ty else "anything"


def compatible(actual: Ty, want: Ty) -> bool:
    return actual is None or want is None or bool(actual & want)


class ExprTyper:
    """`env` maps the names the anchors resolve to (`root`, `_L1`, …) to schema nodes;
    `schemas` offers `types(node)`, `prop(node, name)` and `values(node)` on such nodes."""

    def __init__(
        self,
        schemas: Any,
        env: dict[str, Any],
        report: Callable[[str], None],
        functions: Mapping[str, FunctionInfo] | None = None,
    ):
        # the project's functions replace the built-ins of the same name
        self.signatures = signature_table(functions) if functions is not None else SIGNATURES
        self.special = (
            {n for n, f in functions.items() if f.special} if functions is not None else HANDLED
        )
        self.registry = functions if functions is not None else _BUILTINS
        self.schemas = schemas
        self.env = env
        self.report = report

    # -- entry -----------------------------------------------------------------

    def check(self, text: str, want: Ty, what: str) -> None:
        """Report when the single expression `text` cannot produce `want`."""
        try:
            node = ast.parse(text.strip(), mode="eval").body
        except SyntaxError:
            return  # a block, or an error the form check reports
        actual = self.infer(node, want)
        if not compatible(actual, want):
            self.report(f"the expression is {describe(actual)}, but {what}")

    def check_block(self, text: str, extra_names: Collection[str] = ()) -> None:
        """The calls of a block of statements (a developer's override): each is checked for its
        arguments, but the block is not compared with a type: its result is not one expression.
        A name that is not in scope is reported: `env`, `extra_names` (what the scope offers
        besides the schema nodes, e.g. `index`), the block's own variables, the registry."""
        try:
            tree = ast.parse(textwrap.dedent(text).strip("\n"))
        except SyntaxError:
            return  # reported by the form check
        self._undefined(tree, set(extra_names))
        for stmt in ast.walk(tree):
            for field in ("value", "test"):
                expr = getattr(stmt, field, None)
                if isinstance(expr, ast.expr) and isinstance(
                    stmt, ast.Assign | ast.Return | ast.Expr | ast.If
                ):
                    self.infer(expr)

    def _undefined(self, tree: ast.AST, extra: set[str]) -> None:
        """Names read in the block that nothing defines. A variable counts as defined anywhere
        in the block (use before assignment is not looked for); Python's own builtins are not
        reported, whether the target accepts them is not this check's call."""
        known = {*self.env, *extra, *self.registry, *_CASTS, *dir(builtins), "Null"}
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store | ast.Del):
                known.add(n.id)
            elif isinstance(n, ast.arg):
                known.add(n.arg)
            elif isinstance(n, ast.FunctionDef | ast.ClassDef):
                known.add(n.name)
        reported: set[str] = set()
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Name)
                and isinstance(n.ctx, ast.Load)
                and n.id not in known
                and n.id not in reported
            ):
                reported.add(n.id)
                self.report(f"'{n.id}' is not defined")

    def _arity(self, node: ast.Call, name: str) -> None:
        """A call of a registered function must fit its parameters."""
        info = self.registry.get(name)
        if info is None or any(k.arg is None for k in node.keywords):
            return
        if any(isinstance(a, ast.Starred) for a in node.args):
            return
        given = len(node.args) + len(node.keywords)
        required = sum(1 for p in info.params if p.default is None and not p.variadic)
        variadic = any(p.variadic for p in info.params)
        most = None if variadic else len(info.params)
        if given < required or (most is not None and given > most):
            takes = (
                f"{required}"
                if most == required
                else f"{required} to {most}"
                if most is not None
                else f"at least {required}"
            )
            self.report(f"{name}() takes {takes} argument(s), {given} given: {info.signature()}")

    # -- references ------------------------------------------------------------

    def _node(self, node: ast.expr) -> Any:
        """The schema node a `root.a.b` / `_L1.x` chain points at, else None."""
        if isinstance(node, ast.Name):
            found = self.env.get(node.id)
            return found if isinstance(found, dict) else None
        if isinstance(node, ast.Attribute):
            base = self._node(node.value)
            if base is None:
                return None
            found = self.schemas.prop(base, node.attr)
            return found if isinstance(found, dict) else None
        return None

    def _of_node(self, node: Any) -> Ty:
        types = self.schemas.types(node) if isinstance(node, dict) else set()
        return frozenset(types) if types else None

    # -- inference -------------------------------------------------------------

    def infer(self, node: ast.expr, want: Ty = None) -> Ty:
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool):
                return BOOLEAN
            if isinstance(v, int):
                return INTEGER
            if isinstance(v, float):
                return NUMBER
            return STRING if isinstance(v, str) else None
        if isinstance(node, ast.JoinedStr):
            return STRING
        if isinstance(node, ast.Name | ast.Attribute):
            found = self._node(node)
            if found is not None:
                return self._of_node(found)
            if isinstance(node, ast.Attribute):
                self.infer(node.value)
            return None
        if isinstance(node, ast.BinOp):
            return self._binop(node)
        if isinstance(node, ast.UnaryOp):
            inner = self.infer(node.operand)
            return BOOLEAN if isinstance(node.op, ast.Not) else inner
        if isinstance(node, ast.Compare):
            for part in (node.left, *node.comparators):
                self.infer(part)
            return BOOLEAN
        if isinstance(node, ast.BoolOp):
            for part in node.values:
                self.infer(part)
            return None
        if isinstance(node, ast.IfExp):
            self.infer(node.test)
            return self._branches([node.body, node.orelse], want)
        if isinstance(node, ast.Call):
            return self._call(node, want)
        return None

    def _operand(self, node: ast.expr, op: str, allow_text: bool = False) -> Ty:
        ty = self.infer(node)
        want = NUMERIC | STRING if allow_text else NUMERIC
        if not compatible(ty, want):
            self.report(f"an operand of '{op}' is {describe(ty)}, but must be numeric")
        return ty

    def _binop(self, node: ast.BinOp) -> Ty:
        op = {
            ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//",
            ast.Mod: "%", ast.Pow: "**",
        }.get(type(node.op))  # fmt: skip
        if op is None:
            return None
        if op == "+":
            left, right = self.infer(node.left), self.infer(node.right)
            if left == STRING or right == STRING:
                for ty in (left, right):
                    if not compatible(ty, STRING):
                        self.report(f"'+' joins text with {describe(ty)}: convert it with str()")
                return STRING
            for ty in (left, right):
                if not compatible(ty, NUMERIC):
                    self.report(f"an operand of '+' is {describe(ty)}, but must be numeric")
        else:
            left = self._operand(node.left, op)
            right = self._operand(node.right, op)
        if op == "/" or op == "**":
            return NUMBER
        if left is None or right is None:
            return None
        return INTEGER if left == right == INTEGER else NUMBER

    def _branches(self, nodes: list[ast.expr], want: Ty) -> Ty:
        """Alternatives feeding one result: each is checked against what the result must be."""
        found: list[Ty] = []
        for branch in nodes:
            ty = self.infer(branch, want)
            if want is not None and not compatible(ty, want):
                self.report(f"a branch is {describe(ty)}, but {describe(want)} is expected")
                ty = want
            found.append(ty)
        if any(t is None for t in found):
            return None
        return frozenset().union(*(t for t in found if t is not None))

    def _arg(self, fname: str, index: int, node: ast.expr, want: Ty) -> Ty:
        ty = self.infer(node, want)
        if not compatible(ty, want):
            self.report(
                f"argument {index + 1} of {fname}() is {describe(ty)}, but must be {describe(want)}"
            )
        return ty

    def _call(self, node: ast.Call, want: Ty) -> Ty:
        if isinstance(node.func, ast.Attribute):
            self.infer(node.func.value)
            for arg in node.args:
                self.infer(arg)
            return STRING if node.func.attr in _STR_METHODS else None
        if not isinstance(node.func, ast.Name):
            return None
        name, args = node.func.id, node.args
        if name in _CASTS:
            for arg in args:
                self.infer(arg)
            return _CASTS[name]
        self._arity(node, name)
        if name == "lookup" and name in self.special:
            return self._lookup(args, want)
        if name == "if_else" and name in self.special and len(args) == 3:
            self._arg(name, 0, args[0], BOOLEAN)
            return self._branches(args[1:], want)
        if name == "coalesce" and name in self.special and args:
            return self._branches(args, want)
        if name == "concat" and name in self.special:
            for arg in args:
                self.infer(arg)
            return STRING
        if name == "count" and name in self.special:
            for arg in args:
                self.infer(arg)
            return INTEGER
        if name in self.signatures:
            params, returns = self.signatures[name]
            for i, arg in enumerate(args):
                self._arg(name, i, arg, params[i] if i < len(params) else None)
            return returns
        for arg in args:
            self.infer(arg)
        return None

    def _lookup(self, args: list[ast.expr], want: Ty) -> Ty:
        if len(args) not in (2, 3):
            return None
        self._arg("lookup", 0, args[0], SCALAR)
        table = args[1]
        values: Ty = None
        if isinstance(table, ast.Dict):  # a named lookup, or an inline dict
            found = [self.infer(v) for v in table.values]
            values = None if any(t is None for t in found) else frozenset().union(*found)  # type: ignore[arg-type]
        else:
            schema = self._node(table)
            if schema is not None:
                kinds = self.schemas.types(schema)
                if kinds and "object" not in kinds:
                    self.report(
                        f"argument 2 of lookup() is {describe(frozenset(kinds))}, "
                        "but a lookup table must be an object"
                    )
                else:
                    listed = self.schemas.values(schema)
                    typed = [self.schemas.types(v) for v in listed or []]
                    if listed and all(typed):
                        values = frozenset().union(*typed)
        if len(args) == 3:
            # a default of a number table may be a whole number
            accepts = values | {"integer"} if values and "number" in values else values
            self._arg("lookup", 2, args[2], accepts)
        return values
