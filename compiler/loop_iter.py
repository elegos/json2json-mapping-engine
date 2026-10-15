"""Shared, target-agnostic parsing of a `for` statement's `iter`/`target`
(docs/ARCHITECTURE.md discussion: progressive index and sort-before-iterate).

Two idioms layer on top of the base `for x in <array_expr>:` grammar,
written exactly as real Python would (never executed as Python — same
"Python as syntax" convention as everywhere else in `.map.py`):

    for i, x in enumerate(root.items):              # 0-based index
    for i, x in enumerate(root.items, start=1):      # 1-based index
    for x in sorted(root.items, key="price"):        # sort before iterating
    for x in sorted(root.items, key="price", reverse=True):
    for x in sorted(root.items, by=to_number(x.code), kind="number", nulls="first"):  # a computed key
    for x in sorted(sorted(root.items, by=x.b), key="a"):    # several keys: the last first (stable)
    for i, x in enumerate(sorted(root.items, key="price")):   # composed
    for i, x in enumerate([x for x in root.items if x.status == "A"]):   # filter first

A comprehension in the iterable is a filter applied *before* `enumerate()`, so
exactly as in real Python the index counts the elements that passed it (unlike
`if cond: continue` in the body, where `enumerate()` has already numbered the
skipped ones). It may wrap `sorted(...)`: sort, then filter, then number.
The Loop Fusion Optimizer lowers it (`compiler/loop_fusion.py`).

`sorted()`'s `key=` takes a **field name string**, not a callable — a
deliberate deviation from real Python's `sorted(iterable, key=<callable>)`
signature, forced by the language subset banning `lambda`. `by=` takes an expression of the loop's
own variable (the one the `for` names), evaluated once per element, and `kind=` its type
(`"number"` or `"str"`: how the keys compare). Either may carry `reverse=True` and
`nulls="first"` (default: an element with no key goes last, in both directions); elements with
equal keys keep their order, so several keys are nested calls, the least important innermost.
Since `.map.py` is never executed as real Python, this doesn't need to be literally runnable,
just recognizable.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


class LoopIterError(Exception):
    pass


@dataclass(frozen=True)
class SortSpec:
    """One ordering of the elements: by a field (`field`) or by an expression of the element (`by`,
    typed `kind`)."""

    field: str | None = None
    by: ast.expr | None = None
    kind: str | None = None  # "number" | "str": how an expression's keys compare
    reverse: bool = False
    nulls_first: bool = False


@dataclass(frozen=True)
class ForIterSpec:
    array_expr: ast.expr
    # the orderings, in the order they are applied (the last one decides first)
    sorts: tuple[SortSpec, ...] = ()
    enumerate_start: int | None = None  # None = no `enumerate()` wrapper
    filter_expr: ast.expr | None = None  # comprehension `if` conditions, AND-ed
    filter_var: str | None = None  # the comprehension's own loop variable

    @property
    def sort_key(self) -> str | None:
        """The field of a single ordering by a field (what the earlier form of the language had)."""
        only = self.sorts[0] if len(self.sorts) == 1 else None
        return only.field if only is not None else None

    @property
    def sort_reverse(self) -> bool:
        return len(self.sorts) == 1 and self.sorts[0].reverse


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

    sorts: list[SortSpec] = []
    while (
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id == "sorted"
    ):
        if not inner.args:
            raise LoopIterError("sorted() requires an iterable argument")
        sorts.append(parse_sort(inner))
        inner = inner.args[0]
    sorts.reverse()  # the innermost call is applied first

    return ForIterSpec(
        array_expr=inner,
        sorts=tuple(sorts),
        enumerate_start=enumerate_start,
        filter_expr=filter_expr,
        filter_var=filter_var,
    )


def parse_sort(call: ast.Call) -> SortSpec:
    keywords = {kw.arg: kw.value for kw in call.keywords}
    unknown = set(keywords) - {"key", "by", "kind", "reverse", "nulls"}
    if unknown:
        raise LoopIterError(f"sorted() has no option {min(map(str, unknown))!r}")
    reverse = False
    if "reverse" in keywords:
        node = keywords["reverse"]
        if not (isinstance(node, ast.Constant) and isinstance(node.value, bool)):
            raise LoopIterError("sorted() reverse= must be a bool literal")
        reverse = node.value
    nulls_first = False
    if "nulls" in keywords:
        node = keywords["nulls"]
        if not (isinstance(node, ast.Constant) and node.value in ("first", "last")):
            raise LoopIterError('sorted() nulls= must be "first" or "last"')
        nulls_first = node.value == "first"
    if ("key" in keywords) == ("by" in keywords):
        raise LoopIterError('sorted() takes one of key="<field name>" or by=<expression>')
    if "key" in keywords:
        key = keywords["key"]
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            raise LoopIterError("sorted() key= must be a string literal field name")
        return SortSpec(field=key.value, reverse=reverse, nulls_first=nulls_first)
    kind_node = keywords.get("kind")
    if not (isinstance(kind_node, ast.Constant) and kind_node.value in ("number", "str")):
        raise LoopIterError('sorted(by=...) needs kind="number" or kind="str"')
    return SortSpec(
        by=keywords["by"], kind=kind_node.value, reverse=reverse, nulls_first=nulls_first
    )


def sorted_call(inner: ast.expr, sorts: tuple[SortSpec, ...]) -> ast.expr:
    """`inner` wrapped in the `sorted(...)` calls of `sorts` (the first applied is the innermost)."""
    node = inner
    for spec in sorts:
        keywords: list[ast.keyword] = []
        if spec.field is not None:
            keywords.append(ast.keyword(arg="key", value=ast.Constant(value=spec.field)))
        else:
            assert spec.by is not None
            keywords.append(ast.keyword(arg="by", value=spec.by))
            keywords.append(ast.keyword(arg="kind", value=ast.Constant(value=spec.kind)))
        if spec.reverse:
            keywords.append(ast.keyword(arg="reverse", value=ast.Constant(value=True)))
        if spec.nulls_first:
            keywords.append(ast.keyword(arg="nulls", value=ast.Constant(value="first")))
        node = ast.Call(func=ast.Name(id="sorted", ctx=ast.Load()), args=[node], keywords=keywords)
    return node


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
