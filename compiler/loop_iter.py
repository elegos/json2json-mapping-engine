"""Shared, target-agnostic parsing of a `for` statement's `iter`/`target`
(docs/ARCHITECTURE.md discussion: progressive index and sort-before-iterate).

Two idioms layer on top of the base `for x in <array_expr>:` grammar,
written exactly as real Python would (never executed as Python — same
"Python as syntax" convention as everywhere else in `.map.py`):

    for i, x in enumerate(root.items):              # 0-based index
    for i, x in enumerate(root.items, start=1):      # 1-based index
    for x in sorted(root.items, key="price"):        # sort before iterating
    for x in sorted(root.items, key="price", reverse=True):
    for i, x in enumerate(sorted(root.items, key="price")):   # composed
    for i, x in enumerate([x for x in root.items if x.status == "A"]):   # filter first

A comprehension in the iterable is a filter applied *before* `enumerate()`, so
exactly as in real Python the index counts the elements that passed it (unlike
`if cond: continue` in the body, where `enumerate()` has already numbered the
skipped ones). It may wrap `sorted(...)`: sort, then filter, then number.
The Loop Fusion Optimizer lowers it (`compiler/loop_fusion.py`).

`sorted()`'s `key=` takes a **field name string**, not a callable — a
deliberate deviation from real Python's `sorted(iterable, key=<callable>)`
signature, forced by the language subset banning `lambda`. Since `.map.py`
is never executed as real Python, this doesn't need to be literally
runnable, just recognizable.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


class LoopIterError(Exception):
    pass


@dataclass(frozen=True)
class ForIterSpec:
    array_expr: ast.expr
    sort_key: str | None = None
    sort_reverse: bool = False
    enumerate_start: int | None = None  # None = no `enumerate()` wrapper
    filter_expr: ast.expr | None = None  # comprehension `if` conditions, AND-ed
    filter_var: str | None = None  # the comprehension's own loop variable


def parse_for_iter(node: ast.expr) -> ForIterSpec:
    enumerate_start: int | None = None
    inner = node

    if (
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id == "enumerate"
    ):
        if not inner.args:
            raise LoopIterError("enumerate() requires an iterable argument")
        start = 0
        if len(inner.args) >= 2:
            start = _require_int_literal(inner.args[1], "enumerate() start")
        for kw in inner.keywords:
            if kw.arg == "start":
                start = _require_int_literal(kw.value, "enumerate() start")
        enumerate_start = start
        inner = inner.args[0]

    filter_expr: ast.expr | None = None
    filter_var: str | None = None
    if isinstance(inner, ast.ListComp):
        filter_var, filter_expr, inner = _parse_filter_comprehension(inner)

    sort_key: str | None = None
    sort_reverse = False
    if (
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id == "sorted"
    ):
        if not inner.args:
            raise LoopIterError("sorted() requires an iterable argument")
        key_node = next((kw.value for kw in inner.keywords if kw.arg == "key"), None)
        if key_node is None:
            raise LoopIterError('sorted() requires key="<field name>"')
        if not (isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)):
            raise LoopIterError("sorted() key= must be a string literal field name")
        sort_key = key_node.value
        for kw in inner.keywords:
            if kw.arg == "reverse":
                if not (isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool)):
                    raise LoopIterError("sorted() reverse= must be a bool literal")
                sort_reverse = kw.value.value
        inner = inner.args[0]

    return ForIterSpec(
        array_expr=inner,
        sort_key=sort_key,
        sort_reverse=sort_reverse,
        enumerate_start=enumerate_start,
        filter_expr=filter_expr,
        filter_var=filter_var,
    )


def _parse_filter_comprehension(node: ast.ListComp) -> tuple[str, ast.expr, ast.expr]:
    """`[x for x in <iter> if c1 if c2]` -> `("x", c1 and c2, <iter>)`. Only the
    identity projection is allowed: this is a filter, not a transformation."""
    if len(node.generators) != 1:
        raise LoopIterError("a loop-iterable comprehension takes exactly one `for` clause")
    gen = node.generators[0]
    if gen.is_async or not isinstance(gen.target, ast.Name):
        raise LoopIterError("a loop-iterable comprehension must iterate a single plain name")
    if not (isinstance(node.elt, ast.Name) and node.elt.id == gen.target.id):
        raise LoopIterError(
            f"a loop-iterable comprehension may only filter: write `[{gen.target.id} for "
            f"{gen.target.id} in ... if <cond>]`"
        )
    if not gen.ifs:
        raise LoopIterError("a loop-iterable comprehension needs an `if` condition")
    cond = gen.ifs[0] if len(gen.ifs) == 1 else ast.BoolOp(op=ast.And(), values=list(gen.ifs))
    return gen.target.id, cond, gen.iter


def _require_int_literal(node: ast.expr, what: str) -> int:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    raise LoopIterError(f"{what} must be an int literal")


def parse_for_target(target: ast.expr) -> tuple[str, str | None]:
    """Returns `(item_var_name, index_var_name_or_None)`."""
    if isinstance(target, ast.Name):
        return target.id, None
    if (
        isinstance(target, ast.Tuple)
        and len(target.elts) == 2
        and isinstance(target.elts[0], ast.Name)
        and isinstance(target.elts[1], ast.Name)
    ):
        idx_name, item_name = target.elts[0], target.elts[1]
        return item_name.id, idx_name.id
    raise LoopIterError("for-loop target must be a simple name, or `index, item` (enumerate())")
