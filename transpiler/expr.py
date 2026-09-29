"""Stage 3 — Expression Parser (docs/ARCHITECTURE.md, §Expression language).

An expression block is Python: optional local assignments, then a value
(`return` is optional on the last line). After anchor resolution `ast.parse()`
is all the parsing needed. This stage also:

- mangles local variable names with the rule's id prefix (`base` ->
  `ord_lin_base`) so fields sharing one composite function cannot collide;
- rewrites a trailing bare expression into a `return`;
- reports what the block can do (`return Null`, bare `return`), which drive the
  generated function's return annotation.

Blocks are used for `transform.expression`, `transform.code_override` (developer
dialect — same shape, no anchors) and `guard`.
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass

from transpiler.model import FnYamlError

_RESERVED_PARAMS = {"root", "out", "Null"}
_RESERVED_PATTERN = re.compile(r"^(src|index)\d*$")


@dataclass
class Block:
    stmts: list[ast.stmt]  # finalized: every path ends in a Return
    returns_null: bool
    can_omit: bool

    @property
    def is_simple(self) -> bool:
        """assign* then one `return <value>` — expressible as a dataclass kwarg."""
        *pre, last = self.stmts
        return (
            all(isinstance(s, ast.Assign) for s in pre)
            and isinstance(last, ast.Return)
            and last.value is not None
            and not self.returns_null
        )

    @property
    def pre(self) -> list[ast.stmt]:
        return self.stmts[:-1]

    @property
    def value(self) -> ast.expr:
        last = self.stmts[-1]
        assert isinstance(last, ast.Return) and last.value is not None
        return last.value


class _Rename(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id in self.mapping:
            return ast.copy_location(ast.Name(id=self.mapping[node.id], ctx=node.ctx), node)
        return node


def _assigned_names(stmts: list[ast.stmt]) -> set[str]:
    names: set[str] = set()
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
    return names


def _check_shape(stmts: list[ast.stmt], where: str) -> None:
    for stmt in stmts:
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise FnYamlError(f"{where}: only `name = <expression>` assignments are allowed")
        elif isinstance(stmt, ast.If):
            _check_shape(stmt.body, where)
            _check_shape(stmt.orelse, where)
        elif isinstance(stmt, (ast.Return, ast.Expr)):
            pass
        else:
            raise FnYamlError(
                f"{where}: unsupported statement '{type(stmt).__name__}' in an expression block "
                "(allowed: assignments, if/elif/else, return, a final expression)"
            )


def _finalize(stmts: list[ast.stmt], where: str, top: bool = True) -> list[ast.stmt]:
    """Turn the trailing expression into a return; require every path to end in one."""
    if not stmts:
        raise FnYamlError(f"{where}: empty block")
    *head, last = stmts
    for s in head:
        if isinstance(s, ast.Expr):
            raise FnYamlError(f"{where}: a bare expression is only allowed as the last line")
    if isinstance(last, ast.Expr):
        last = ast.Return(value=last.value)
    elif isinstance(last, ast.If):
        if not last.orelse:
            raise FnYamlError(f"{where}: an 'if' at the end of a block needs an 'else' branch")
        last.body = _finalize(last.body, where, top=False)
        last.orelse = _finalize(last.orelse, where, top=False)
    elif not isinstance(last, ast.Return):
        raise FnYamlError(f"{where}: the block must end with a value or a return")
    return [*head, last]


def parse_block(text: str, prefix: str, where: str) -> Block:
    try:
        tree = ast.parse(textwrap.dedent(text).strip("\n"))
    except SyntaxError as exc:
        raise FnYamlError(f"{where}: invalid expression: {exc.msg} (line {exc.lineno})") from exc
    _check_shape(tree.body, where)

    names = _assigned_names(tree.body)
    clash = {n for n in names if n in _RESERVED_PARAMS or _RESERVED_PATTERN.match(n)}
    if clash:
        raise FnYamlError(f"{where}: cannot assign reserved name(s): {', '.join(sorted(clash))}")
    renamer = _Rename({n: f"{prefix}_{n}" for n in names})
    body = [renamer.visit(s) for s in tree.body]
    stmts = _finalize(body, where)

    returns_null = can_omit = False
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Return):
                if node.value is None:
                    can_omit = True
                elif isinstance(node.value, ast.Name) and node.value.id == "Null":
                    returns_null = True
    for stmt in stmts:
        ast.fix_missing_locations(stmt)
    return Block(stmts=stmts, returns_null=returns_null, can_omit=can_omit)
