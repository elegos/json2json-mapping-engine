"""AST allow-list validator (docs/ARCHITECTURE.md, §Language subset, §Compiler components).

Security gate: in bootstrap mode `.map.py` files are hand-written and enter
the build as-is. This module is the sole barrier against arbitrary Python
execution reaching the Code Generator — it must run before every other
compiler phase and reject any construct outside the permitted subset,
regardless of where in the tree it appears.
"""

from __future__ import annotations

import ast

_ALWAYS_BLOCKED_NODE_TYPES: tuple[type[ast.AST], ...] = (
    ast.Lambda,
    ast.Yield,
    ast.YieldFrom,
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Await,
    ast.Global,
    ast.Nonlocal,
    ast.Try,
    ast.With,
    ast.Starred,
)

_BLOCKED_CALL_NAMES = {"exec", "eval"}

# The sole exception to the module-scope assignment ban (§Language subset).
_RESERVED_MODULE_ASSIGNS = ("__id__", "__validation__")


class ValidatorError(Exception):
    """Raised when a `.map.py` source contains a construct outside the
    permitted subset. Carries the offending line number when available."""

    def __init__(self, message: str, node: ast.AST | None = None):
        lineno = getattr(node, "lineno", None)
        if lineno is not None:
            message = f"line {lineno}: {message}"
        super().__init__(message)


class Validator(ast.NodeVisitor):
    def __init__(self):
        self._function_depth = 0

    def validate(self, tree: ast.Module) -> None:
        self._function_depth = 0
        self.visit(tree)

    # -- generic gate -----------------------------------------------------

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, _ALWAYS_BLOCKED_NODE_TYPES):
            raise ValidatorError(f"{type(node).__name__} is not a permitted construct", node)
        super().generic_visit(node)

    # -- imports ------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        raise ValidatorError("`import` is not permitted (only `from __mapping__ import ...`)", node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module != "__mapping__":
            raise ValidatorError(
                f"`from {node.module} import ...` is not permitted — only "
                "`from __mapping__ import ...` is allowed",
                node,
            )
        # The __mapping__ import is an IDE stub only; nothing further to check.

    # -- classes --------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        is_dataclass = any(
            (isinstance(d, ast.Name) and d.id == "dataclass")
            or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
            for d in node.decorator_list
        )
        if not is_dataclass:
            raise ValidatorError(
                "`class` is only permitted as an `@dataclass` output type definition", node
            )
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue  # docstring
            if isinstance(stmt, ast.Pass):
                continue
            raise ValidatorError("`@dataclass` bodies may not contain methods", stmt)

    # -- functions ------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        args = node.args
        if args.vararg is not None or args.kwarg is not None:
            raise ValidatorError("`*args` / `**kwargs` are not permitted", node)
        if args.kwonlyargs:
            raise ValidatorError("keyword-only parameters are not permitted", node)
        for a in args.args:
            if a.annotation is None:
                raise ValidatorError(
                    f"parameter '{a.arg}' is missing a type annotation (hard-typed subset)", node
                )
        if node.returns is None:
            raise ValidatorError(
                f"function '{node.name}' is missing a return type annotation", node
            )
        self._function_depth += 1
        try:
            for stmt in node.body:
                self.visit(stmt)
        finally:
            self._function_depth -= 1

    # -- assignments ------------------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                if self._function_depth == 0:
                    if (
                        target.id in _RESERVED_MODULE_ASSIGNS
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)
                    ):
                        continue
                    raise ValidatorError(
                        "local variable assignment is only permitted inside a "
                        "per-field function body (§Language subset)",
                        node,
                    )
            elif isinstance(target, ast.Attribute):
                pass  # `out.field = ...` — always permitted
            else:
                raise ValidatorError("unsupported assignment target", node)
        self.visit(node.value)

    # -- calls ------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALL_NAMES:
            raise ValidatorError(f"`{node.func.id}` is not permitted", node)
        self.generic_visit(node)
