"""Shared, target-agnostic annotation parsing.

Used by both the Type Checker and the Code Generator — parsing a `T | None`
/ `T | Null` return annotation into (base DSL type name, nullable) is not
specific to any target language.
"""

from __future__ import annotations

import ast


class AnnotationError(Exception):
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
            raise AnnotationError("unsupported union annotation")
        node = non_null[0]
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "list"
        and isinstance(node.slice, ast.Name)
    ):
        return f"list[{node.slice.id}]", nullable
    if not isinstance(node, ast.Name):
        raise AnnotationError(f"unsupported type annotation: {ast.dump(node)}")
    return node.id, nullable
