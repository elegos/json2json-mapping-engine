"""Where the arrays of the output come into existence.

An output array exists even when nothing is appended to it (a loop over no element gives `[]`),
but only where the mapping writes it: the arrays a group writes (the body of an `if` at the top of
the mapping) exist when the group's guard holds, not otherwise. The pass puts a bare `out.<array>`
statement where the array must be created, so that every backend reads the same rule."""

from __future__ import annotations

import ast


def _appended(statements: list[ast.stmt]) -> list[str]:
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


def _touch(names: list[str], guarded: bool = False) -> list[ast.stmt]:
    """`out.<array>` statements; `guarded` (an attribute of the node) marks the ones inside an `if`,
    which a backend must create conditionally."""
    touches: list[ast.stmt] = []
    for n in names:
        node = ast.Expr(
            value=ast.Attribute(value=ast.Name(id="out", ctx=ast.Load()), attr=n, ctx=ast.Load())
        )
        node.guarded = guarded  # pyright: ignore[reportAttributeAccessIssue]
        touches.append(node)
    return touches


def _open(statements: list[ast.stmt], created: set[str], guarded: bool = False) -> list[ast.stmt]:
    """`statements` with a touch of each array they write that is not created yet: before them,
    for the ones written outside any `if`; at the start of an `if` branch for the ones only it
    writes."""
    plain = [s for s in statements if not isinstance(s, ast.If)]
    here = [n for n in _appended(plain) if n not in created]
    created = created | set(here)
    result: list[ast.stmt] = _touch(here, guarded)
    for stmt in statements:
        if isinstance(stmt, ast.If):
            stmt = ast.If(
                test=stmt.test,
                body=_branch(stmt.body, created),
                orelse=_orelse(stmt.orelse, created),
            )
        result.append(stmt)
    return result


def _branch(body: list[ast.stmt], created: set[str]) -> list[ast.stmt]:
    return _open(body, created, guarded=True)


def _orelse(orelse: list[ast.stmt], created: set[str]) -> list[ast.stmt]:
    if len(orelse) == 1 and isinstance(orelse[0], ast.If):
        inner = orelse[0]
        return [
            ast.If(
                test=inner.test,
                body=_branch(inner.body, created),
                orelse=_orelse(inner.orelse, created),
            )
        ]
    return _branch(orelse, created) if orelse else []


_BODY = (ast.For, ast.If, ast.Assign, ast.Expr)


def open_output_arrays(tree: ast.Module) -> None:
    """Rewrites the mapping body in `tree` (the statements that write `out`, after the rules and
    the directives)."""
    body: list[ast.stmt] = [
        s
        for s in tree.body
        if isinstance(s, _BODY)
        and not (isinstance(s, ast.Assign) and isinstance(s.targets[0], ast.Name))
    ]
    if not body:
        return
    first = tree.body.index(body[0])
    rest = [s for s in tree.body if not any(s is b for b in body)]
    tree.body = [*rest[:first], *_open(body, set()), *rest[first:]]
    ast.fix_missing_locations(tree)
