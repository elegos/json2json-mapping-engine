import ast

import pytest

from compiler.loop_fusion import LoopFusionError, fuse_loops


def _rule_defs(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {s.name: s for s in tree.body if isinstance(s, ast.FunctionDef)}


def test_fuses_sibling_loops_over_the_same_source_into_one():
    tree = ast.parse(
        "for a in root.items:\n"
        "    out.X.append(a.id)\n"
        "for b in root.items:\n"
        "    out.Y.append(b.price)\n"
    )
    fused = fuse_loops(tree.body, _rule_defs(tree))
    for_stmts = [s for s in fused if isinstance(s, ast.For)]
    assert len(for_stmts) == 1
    assert len(fused) == 1  # the second `for` was merged away, not left behind


def test_renames_the_merged_loop_variable_to_the_canonical_one():
    tree = ast.parse(
        "for a in root.items:\n"
        "    out.X.append(a.id)\n"
        "for b in root.items:\n"
        "    out.Y.append(b.price)\n"
    )
    fused = fuse_loops(tree.body, _rule_defs(tree))
    dumped = ast.dump(fused[0])
    assert "id='b'" not in dumped  # every reference to `b` renamed to `a`


def test_different_source_arrays_are_not_fused():
    tree = ast.parse(
        "for a in root.items:\n"
        "    out.X.append(a.id)\n"
        "for b in root.other_items:\n"
        "    out.Y.append(b.price)\n"
    )
    fused = fuse_loops(tree.body, _rule_defs(tree))
    for_stmts = [s for s in fused if isinstance(s, ast.For)]
    assert len(for_stmts) == 2


def test_fusion_disabled_keeps_loops_separate():
    tree = ast.parse(
        "for a in root.items:\n"
        "    out.X.append(a.id)\n"
        "for b in root.items:\n"
        "    out.Y.append(b.price)\n"
    )
    fused = fuse_loops(tree.body, _rule_defs(tree), fusion_enabled=False)
    for_stmts = [s for s in fused if isinstance(s, ast.For)]
    assert len(for_stmts) == 2


def test_continue_filter_is_normalized_to_if_not_guard():
    tree = ast.parse(
        "for a in root.items:\n"
        "    if a.status == 'INACTIVE':\n"
        "        continue\n"
        "    out.X.append(a.id)\n"
    )
    fused = fuse_loops(tree.body, _rule_defs(tree))
    for_stmt = fused[0]
    assert isinstance(for_stmt, ast.For)
    guard = for_stmt.body[0]
    assert isinstance(guard, ast.If)
    assert isinstance(guard.test, ast.UnaryOp) and isinstance(guard.test.op, ast.Not)
    assert not any(isinstance(s, ast.Continue) for s in ast.walk(for_stmt))


def test_fused_loops_with_different_filters_each_keep_their_own_guard():
    tree = ast.parse(
        "for a in root.items:\n"
        "    if a.kind != 'A':\n"
        "        continue\n"
        "    out.X.append(a.id)\n"
        "for b in root.items:\n"
        "    if b.kind != 'B':\n"
        "        continue\n"
        "    out.Y.append(b.price)\n"
    )
    fused = fuse_loops(tree.body, _rule_defs(tree))
    for_stmt = fused[0]
    assert isinstance(for_stmt, ast.For)
    guards = [s for s in for_stmt.body if isinstance(s, ast.If)]
    assert len(guards) == 2  # each original loop's filter survives as its own branch


def test_nested_loops_are_fused_independently_per_level():
    tree = ast.parse(
        "for a in root.items:\n"
        "    for x in a.sub:\n"
        "        out.X.append(x.v)\n"
        "    for y in a.sub:\n"
        "        out.Y.append(y.v)\n"
    )
    fused = fuse_loops(tree.body, _rule_defs(tree))
    outer = fused[0]
    assert isinstance(outer, ast.For)
    inner_fors = [s for s in outer.body if isinstance(s, ast.For)]
    assert len(inner_fors) == 1  # the two inner loops over `a.sub` were fused too


def test_parallel_degree_mismatch_is_a_fusion_error():
    tree = ast.parse(
        "@parallel(degree=2)\n"
        "def rule_a(x: Any) -> str:\n"
        "    return x.id\n\n"
        "@parallel(degree=4)\n"
        "def rule_b(x: Any) -> str:\n"
        "    return x.id\n\n"
        "for a in root.items:\n"
        "    out.X.append(rule_a(a))\n"
        "for b in root.items:\n"
        "    out.Y.append(rule_b(b))\n"
    )
    with pytest.raises(LoopFusionError, match="@parallel"):
        fuse_loops(tree.body, _rule_defs(tree))


def test_parallel_degree_mismatch_resolved_by_max():
    tree = ast.parse(
        "@parallel(degree=2)\n"
        "def rule_a(x: Any) -> str:\n"
        "    return x.id\n\n"
        "@parallel(degree=4)\n"
        "def rule_b(x: Any) -> str:\n"
        "    return x.id\n\n"
        "for a in root.items:\n"
        "    out.X.append(rule_a(a))\n"
        "for b in root.items:\n"
        "    out.Y.append(rule_b(b))\n"
    )
    fused = fuse_loops(tree.body, _rule_defs(tree), parallel_conflict="max")
    for_stmts = [s for s in fused if isinstance(s, ast.For)]
    assert len(for_stmts) == 1


def test_matching_parallel_degrees_do_not_conflict():
    tree = ast.parse(
        "@parallel(degree=4)\n"
        "def rule_a(x: Any) -> str:\n"
        "    return x.id\n\n"
        "@parallel(degree=4)\n"
        "def rule_b(x: Any) -> str:\n"
        "    return x.id\n\n"
        "for a in root.items:\n"
        "    out.X.append(rule_a(a))\n"
        "for b in root.items:\n"
        "    out.Y.append(rule_b(b))\n"
    )
    fused = fuse_loops(tree.body, _rule_defs(tree))
    for_stmts = [s for s in fused if isinstance(s, ast.For)]
    assert len(for_stmts) == 1


def test_enumerate_loops_fuse_and_rename_both_index_and_item():
    tree = ast.parse(
        "for i, a in enumerate(root.items):\n"
        "    out.X.append(a.id)\n"
        "for j, b in enumerate(root.items):\n"
        "    out.Y.append(b.price)\n"
    )
    fused = fuse_loops(tree.body, _rule_defs(tree))
    for_stmts = [s for s in fused if isinstance(s, ast.For)]
    assert len(for_stmts) == 1
    dumped = ast.dump(fused[0])
    assert "id='j'" not in dumped and "id='b'" not in dumped
