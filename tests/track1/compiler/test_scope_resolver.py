import ast

from compiler.scope_resolver import resolve_scopes


def _as_for(stmt: ast.stmt) -> ast.For:
    assert isinstance(stmt, ast.For)
    return stmt


def test_root_scope_has_no_loop_var():
    tree = ast.parse("out.X = root.id\n")
    resolution = resolve_scopes(tree)
    assert resolution.root_scope.loop_var is None
    assert resolution.root_scope.parent is None


def test_nested_for_loops_build_a_parent_chain():
    tree = ast.parse(
        "for order in root.orders:\n"
        "    for line in order.items:\n"
        "        out.Amount = line.price\n"
    )
    resolution = resolve_scopes(tree)
    outer_for = _as_for(tree.body[0])
    inner_for = _as_for(outer_for.body[0])

    outer_scope = resolution.for_scopes[id(outer_for)]
    inner_scope = resolution.for_scopes[id(inner_for)]

    assert outer_scope.loop_var == "order"
    assert outer_scope.parent is resolution.root_scope
    assert inner_scope.loop_var == "line"
    assert inner_scope.parent is outer_scope
    assert inner_scope.depth == outer_scope.depth + 1


def test_resolve_name_walks_up_the_chain():
    tree = ast.parse(
        "for order in root.orders:\n"
        "    for line in order.items:\n"
        "        out.Amount = line.price\n"
    )
    resolution = resolve_scopes(tree)
    outer_for = _as_for(tree.body[0])
    inner_for = _as_for(outer_for.body[0])
    inner_scope = resolution.for_scopes[id(inner_for)]

    assert inner_scope.resolve_name("line") is inner_scope
    assert inner_scope.resolve_name("order") is resolution.for_scopes[id(outer_for)]
    assert inner_scope.resolve_name("nonexistent") is None


def test_def_scope_captures_lexically_enclosing_scope():
    tree = ast.parse(
        "for order in root.orders:\n"
        "    def line_amount() -> number:\n"
        "        return order.price\n"
        "    out.Amount = line_amount()\n"
    )
    resolution = resolve_scopes(tree)
    for_node = _as_for(tree.body[0])
    def_node = for_node.body[0]
    assert resolution.def_scopes[id(def_node)] is resolution.for_scopes[id(for_node)]
