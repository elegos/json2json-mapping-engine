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
mirroring `.fn.yaml`'s. Emitting the actual `DBMS_PARALLEL_EXECUTE` /
`PARALLEL_ENABLE` scaffolding for a resolved degree is *not* implemented
here — out of scope for this milestone; only the conflict-detection/
resolution logic (the part that must run during fusion itself) is.

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
from dataclasses import dataclass, field

from compiler.loop_iter import LoopIterError, parse_for_target


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


def _extract_filter(body: list[ast.stmt]) -> tuple[ast.expr | None, list[ast.stmt]]:
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


def _wrap_filter(filter_expr: ast.expr, body: list[ast.stmt]) -> list[ast.stmt]:
    guard = ast.If(test=ast.UnaryOp(op=ast.Not(), operand=filter_expr), body=body, orelse=[])
    return [ast.fix_missing_locations(guard)]


def _parallel_degree(fn_def: ast.FunctionDef) -> int | None:
    for dec in fn_def.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "parallel":
            for kw in dec.keywords:
                if (
                    kw.arg == "degree"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, int)
                ):
                    return kw.value.value
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


def fuse_loops(
    stmts: list[ast.stmt],
    rule_defs: dict[str, ast.FunctionDef],
    parallel_conflict: str = "exception",
    fusion_enabled: bool = True,
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
            try:
                item_var, index_var = parse_for_target(stmt.target)
            except LoopIterError as exc:
                raise LoopFusionError(str(exc)) from exc
            # `enumerate(...)`'s `start=` isn't part of the fusion key: two
            # loops differing only in start offset still iterate the exact
            # same underlying array in the exact same order.
            key = _iter_key(stmt.iter) if fusion_enabled else f"__unfused_{id(stmt)}"
            filter_expr, body = _extract_filter(stmt.body)
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
                if index_var is not None and group.index_var is not None and index_var != group.index_var:
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
            fused_body.extend(_wrap_filter(filter_expr, body) if filter_expr is not None else body)
        group.canonical.body = fused_body

    for stmt in result:
        if isinstance(stmt, ast.For):
            stmt.body = fuse_loops(stmt.body, rule_defs, parallel_conflict, fusion_enabled)

    return result
