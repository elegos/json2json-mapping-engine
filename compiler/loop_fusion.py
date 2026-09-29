"""Loop Fusion Optimizer (docs/ARCHITECTURE.md, §Loop Fusion Optimizer).

Standalone and target-agnostic — a pure AST rewrite pass operating between
the Type Checker and the Code Generator. Reused by both the compiler
(bootstrap mode, this module) and the transpiler (M5, Stage 4, same
module): "the compiler's own Loop Fusion phase [receives] already-fused
loops and acts as a no-op" for `.fn.yaml`-sourced mappings, while
hand-written `.map.py` files still need it applied here.

**What this does:** groups sibling `for` statements (at the same nesting
level) that iterate a *structurally identical* source expression into one
generated loop, renaming the merged loops' variables to a single canonical
name and concatenating their bodies in original relative order. Also
normalizes the bootstrap `if <cond>: continue` filtering idiom into a
per-branch `IF NOT (<cond>): <rest>` guard — always, whether or not fusion
actually merges multiple loops — so the Code Generator only ever has to
handle one shape (a plain `IF`), never `continue`. This is exactly the
"iterate the unfiltered array once, push each rule's filter into a
per-branch IF" resolution documented for `.fn.yaml` `loop` rules with
differing `filter:` values, applied at the bootstrap-mode AST level.

**`@parallel(degree=N)` conflict check** — before fusing a group, every
rule function called from within it that declares `@parallel` must agree
on `degree`; resolved per `optimizer.parallel_conflict` (exception|max|min),
mirroring `.fn.yaml`'s. The backend, not this module, turns the
declaration into target scaffolding (PL/SQL: the `map_<id>_fn` wrapper); only
the conflict-detection/resolution logic (the part that must run during
fusion itself) lives here.

**Cross-rule data-dependency DAG** — deliberately not built here. The
architecture's own illustrative example ("Field F depends on sum(D)")
requires an aggregation built-in (`sum`) that doesn't exist in the built-in
library (§Built-in functions lists none) — and today's rule functions take
explicit typed parameters with no shared mutable state, so there is no
mechanism by which one rule could depend on another's output at all. With
nothing to build edges from, a real DAG/cycle-detection pass would be
inert scaffolding tested against fabricated inputs. Deferred until an
aggregation built-in exists and creates real edges to detect — at that
point this module gains a dependency pass; the fusion/parallel/filter
logic here is unaffected by that addition.
"""

from __future__ import annotations

import ast
import copy
import itertools
from dataclasses import dataclass, field

from compiler.loop_iter import LoopIterError, parse_for_iter, parse_for_target


class LoopFusionError(Exception):
    pass


def _iter_key(node: ast.expr) -> str:
    """Structural-equality key for a source expression, ignoring source
    positions (two `root.orders` reads at different lines are the same
    source array)."""
    return ast.dump(node, annotate_fields=False)


class _RenameLoopVar(ast.NodeTransformer):
    def __init__(self, old: str, new: str):
        self.old = old
        self.new = new

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id == self.old:
            return ast.copy_location(ast.Name(id=self.new, ctx=node.ctx), node)
        return node


def extract_continue_filter(body: list[ast.stmt]) -> tuple[ast.expr | None, list[ast.stmt]]:
    """If `body` starts with a bare `if <cond>: continue` (no `elif`/
    `else`), return `(<cond>, remaining body)`; otherwise `(None, body)`."""
    if (
        body
        and isinstance(body[0], ast.If)
        and len(body[0].body) == 1
        and isinstance(body[0].body[0], ast.Continue)
        and not body[0].orelse
    ):
        return body[0].test, body[1:]
    return None, body


def wrap_filter(filter_expr: ast.expr, body: list[ast.stmt]) -> list[ast.stmt]:
    # `continue when not X` -> `if X`: same truthiness (a NULL condition still skips),
    # without the `NOT (NOT ...)` the naive wrap would emit.
    if isinstance(filter_expr, ast.UnaryOp) and isinstance(filter_expr.op, ast.Not):
        test = filter_expr.operand
    else:
        test = ast.UnaryOp(op=ast.Not(), operand=filter_expr)
    guard = ast.If(test=test, body=body, orelse=[])
    return [ast.fix_missing_locations(guard)]


def _parallel_degree(fn_def: ast.FunctionDef) -> int | None:
    for dec in fn_def.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "parallel"
        ):
            # `@parallel(4)` is an alias of `@parallel(degree=4)`
            values = [*dec.args, *(kw.value for kw in dec.keywords if kw.arg == "degree")]
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, int):
                    return value.value
    return None


def _rule_names_called_in(stmts: list[ast.stmt]) -> set[str]:
    names: set[str] = set()
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                names.add(node.func.id)
    return names


def _check_parallel_conflict(
    member_bodies: list[list[ast.stmt]],
    rule_defs: dict[str, ast.FunctionDef],
    parallel_conflict: str,
) -> None:
    degrees: set[int] = set()
    detail: list[str] = []
    for body in member_bodies:
        for name in _rule_names_called_in(body):
            fn_def = rule_defs.get(name)
            if fn_def is None:
                continue
            degree = _parallel_degree(fn_def)
            if degree is not None:
                degrees.add(degree)
                detail.append(f"{name}=@parallel(degree={degree})")
    if len(degrees) <= 1:
        return
    if parallel_conflict == "max":
        return
    if parallel_conflict == "min":
        return
    raise LoopFusionError(
        "conflicting @parallel(degree=...) among fused loop rules: " + ", ".join(detail)
    )


@dataclass
class _Group:
    canonical: ast.For
    item_var: str
    index_var: str | None
    members: list[tuple[ast.expr | None, list[ast.stmt]]] = field(default_factory=list)


NEXT_INDEX = "__next_index__"


def next_index_call(start: int, counter_id: int) -> ast.Call:
    return ast.Call(
        func=ast.Name(id=NEXT_INDEX, ctx=ast.Load()),
        args=[ast.Constant(value=start), ast.Constant(value=counter_id)],
        keywords=[],
    )


def _has_filtered_iter(stmt: ast.For) -> bool:
    try:
        return parse_for_iter(stmt.iter).filter_expr is not None
    except LoopIterError:
        return False


def lower_filtered_iter(stmt: ast.For, counter: itertools.count) -> ast.For:
    """`for [i,] x in [enumerate(][x for x in A if c][)]:` -> `for x in A:` whose
    body opens with `if not c: continue`, then (when indexed) the internal
    statement `i = __next_index__(start, k)`. `k` names a counter owned by this
    one branch, advanced only for elements that passed `c` — which is why fusing
    several such loops over one array gives each its own counter."""
    try:
        spec = parse_for_iter(stmt.iter)
        item_var, index_var = parse_for_target(stmt.target)
    except LoopIterError as exc:
        raise LoopFusionError(str(exc)) from exc
    if spec.filter_expr is None:
        return stmt
    assert spec.filter_var is not None
    cond = copy.deepcopy(spec.filter_expr)
    if spec.filter_var != item_var:
        cond = _RenameLoopVar(spec.filter_var, item_var).visit(cond)

    iterable: ast.expr = spec.array_expr
    if spec.sort_key is not None:
        keywords = [ast.keyword(arg="key", value=ast.Constant(value=spec.sort_key))]
        if spec.sort_reverse:
            keywords.append(ast.keyword(arg="reverse", value=ast.Constant(value=True)))
        iterable = ast.Call(
            func=ast.Name(id="sorted", ctx=ast.Load()), args=[iterable], keywords=keywords
        )

    body: list[ast.stmt] = []
    if index_var is not None:
        target = ast.Name(id=index_var, ctx=ast.Store())
        body.append(
            ast.Assign(
                targets=[target], value=next_index_call(spec.enumerate_start or 0, next(counter))
            )
        )
    # A body-level `if c2: continue` runs *after* the element was numbered (real
    # Python: `enumerate()` counted it), so it stays nested behind the marker.
    body_filter, rest = extract_continue_filter(stmt.body)
    body += wrap_filter(body_filter, rest) if body_filter is not None else stmt.body
    guard = ast.If(test=ast.UnaryOp(op=ast.Not(), operand=cond), body=[ast.Continue()], orelse=[])
    lowered = ast.For(
        target=ast.Name(id=item_var, ctx=ast.Store()),
        iter=iterable,
        body=[guard, *body],
        orelse=[],
    )
    return ast.fix_missing_locations(ast.copy_location(lowered, stmt))


def fuse_loops(
    stmts: list[ast.stmt],
    rule_defs: dict[str, ast.FunctionDef],
    parallel_conflict: str = "exception",
    fusion_enabled: bool = True,
    lower_filtered_iters: bool = True,
) -> list[ast.stmt]:
    """See `_fuse`. `lower_filtered_iters=False` leaves loops whose iterable is a
    filtering comprehension untouched (not lowered, not fused): the transpiler
    uses it so its `.map.py` output stays plain, readable Python — the compiler
    lowers and fuses those loops itself."""
    return _fuse(
        stmts, rule_defs, parallel_conflict, fusion_enabled, itertools.count(), lower_filtered_iters
    )


def _fuse(
    stmts: list[ast.stmt],
    rule_defs: dict[str, ast.FunctionDef],
    parallel_conflict: str,
    fusion_enabled: bool,
    counter: itertools.count,
    lower_filtered: bool = True,
) -> list[ast.stmt]:
    """Rewrite `stmts`: merge sibling same-source `for` loops (if
    `fusion_enabled`) and normalize `if cond: continue` filters into
    per-branch `IF NOT (cond)` guards (always). Recurses into every `for`
    body so nested levels are fused independently. Handles both plain
    `for x in ...:` and `for i, x in enumerate(...):` targets (§loop_iter)."""
    groups: dict[str, _Group] = {}
    result: list[ast.stmt] = []

    for stmt in stmts:
        if isinstance(stmt, ast.For):
            if not lower_filtered and _has_filtered_iter(stmt):
                result.append(stmt)
                continue
            stmt = lower_filtered_iter(stmt, counter)
            try:
                item_var, index_var = parse_for_target(stmt.target)
            except LoopIterError as exc:
                raise LoopFusionError(str(exc)) from exc
            # `enumerate(...)`'s `start=` isn't part of the fusion key: two
            # loops differing only in start offset still iterate the exact
            # same underlying array in the exact same order.
            key = _iter_key(stmt.iter) if fusion_enabled else f"__unfused_{id(stmt)}"
            filter_expr, body = extract_continue_filter(stmt.body)
            if key not in groups:
                groups[key] = _Group(canonical=stmt, item_var=item_var, index_var=index_var)
                groups[key].members.append((filter_expr, body))
                result.append(stmt)
            else:
                group = groups[key]
                if item_var != group.item_var:
                    renamer = _RenameLoopVar(item_var, group.item_var)
                    body = [renamer.visit(copy.deepcopy(n)) for n in body]
                    if filter_expr is not None:
                        filter_expr = renamer.visit(copy.deepcopy(filter_expr))
                if (
                    index_var is not None
                    and group.index_var is not None
                    and index_var != group.index_var
                ):
                    idx_renamer = _RenameLoopVar(index_var, group.index_var)
                    body = [idx_renamer.visit(copy.deepcopy(n)) for n in body]
                    if filter_expr is not None:
                        filter_expr = idx_renamer.visit(copy.deepcopy(filter_expr))
                group.members.append((filter_expr, body))
        else:
            result.append(stmt)

    for group in groups.values():
        member_bodies = [m[1] for m in group.members]
        if len(group.members) > 1:
            _check_parallel_conflict(member_bodies, rule_defs, parallel_conflict)
        fused_body: list[ast.stmt] = []
        for filter_expr, body in group.members:
            fused_body.extend(wrap_filter(filter_expr, body) if filter_expr is not None else body)
        group.canonical.body = fused_body

    for stmt in result:
        if isinstance(stmt, ast.For):
            stmt.body = _fuse(
                stmt.body, rule_defs, parallel_conflict, fusion_enabled, counter, lower_filtered
            )

    return result
