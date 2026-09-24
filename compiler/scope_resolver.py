"""Scope Resolver (docs/ARCHITECTURE.md, §Compiler components).

Builds the `root` / `src` / `out` context chain per nested loop, and records
which loop (if any) lexically encloses each per-field `def`. Runs after the
Validator and before the Type Checker / Code Generator.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class Scope:
    """One level of the `root`/`src`/`out` context chain.

    `loop_var` is the Python identifier bound by the enclosing `for`
    (`None` for the module-level root scope). `source_expr` is the source
    AST expression the loop iterates over (unresolved — path resolution is
    the Code Generator's job).
    """

    loop_var: str | None
    source_expr: ast.expr | None
    parent: Scope | None
    depth: int = field(default=0)

    def resolve_name(self, name: str) -> Scope | None:
        """Walk up the chain looking for the scope that binds `name`.
        Returns the *scope introducing that binding* — `self` if `name`
        is this scope's own loop variable, otherwise the nearest ancestor
        that binds it, or `None` if unbound (caller falls back to
        `root`/`src` magic names)."""
        scope: Scope | None = self
        while scope is not None:
            if scope.loop_var == name:
                return scope
            scope = scope.parent
        return None


class ScopeResolverError(Exception):
    pass


@dataclass
class ScopeResolution:
    root_scope: Scope
    for_scopes: dict[int, Scope]  # id(ast.For) -> Scope introduced by that loop
    def_scopes: dict[int, Scope]  # id(ast.FunctionDef) -> lexically enclosing Scope


class _Resolver(ast.NodeVisitor):
    def __init__(self):
        self.root_scope = Scope(loop_var=None, source_expr=None, parent=None, depth=0)
        self.for_scopes: dict[int, Scope] = {}
        self.def_scopes: dict[int, Scope] = {}
        self._stack: list[Scope] = [self.root_scope]

    def _current(self) -> Scope:
        return self._stack[-1]

    def visit_For(self, node: ast.For) -> None:
        if not isinstance(node.target, ast.Name):
            raise ScopeResolverError("for-loop target must be a simple name")
        scope = Scope(
            loop_var=node.target.id,
            source_expr=node.iter,
            parent=self._current(),
            depth=self._current().depth + 1,
        )
        self.for_scopes[id(node)] = scope
        self._stack.append(scope)
        try:
            for stmt in node.body:
                self.visit(stmt)
        finally:
            self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # A `def` field-rule function is lexically nested at its current
        # position — it does not introduce a new loop scope itself, but it
        # captures whichever scope encloses it (module root or nearest for).
        self.def_scopes[id(node)] = self._current()
        # Do not descend into the function body here — statement-level
        # translation inside the body is handled by the Code Generator,
        # which reuses this same captured scope for name resolution.


def resolve_scopes(tree: ast.Module) -> ScopeResolution:
    resolver = _Resolver()
    for stmt in tree.body:
        resolver.visit(stmt)
    return ScopeResolution(
        root_scope=resolver.root_scope,
        for_scopes=resolver.for_scopes,
        def_scopes=resolver.def_scopes,
    )
