import ast

import pytest

from compiler.loop_iter import LoopIterError, parse_for_iter, parse_for_target


def _iter(src: str) -> ast.expr:
    return ast.parse(src).body[0].iter  # type: ignore[attr-defined]


def _target(src: str) -> ast.expr:
    return ast.parse(src).body[0].target  # type: ignore[attr-defined]


def test_plain_for_target():
    assert parse_for_target(_target("for x in y: pass")) == ("x", None)


def test_enumerate_target():
    assert parse_for_target(_target("for i, x in y: pass")) == ("x", "i")


def test_plain_iter_has_no_enumerate_or_sort():
    spec = parse_for_iter(_iter("for x in root.items: pass"))
    assert spec.enumerate_start is None
    assert spec.sort_key is None
    assert ast.dump(spec.array_expr) == ast.dump(ast.parse("root.items", mode="eval").body)


def test_enumerate_default_start_is_zero():
    spec = parse_for_iter(_iter("for i, x in enumerate(root.items): pass"))
    assert spec.enumerate_start == 0


def test_enumerate_positional_start():
    spec = parse_for_iter(_iter("for i, x in enumerate(root.items, 1): pass"))
    assert spec.enumerate_start == 1


def test_enumerate_keyword_start():
    spec = parse_for_iter(_iter("for i, x in enumerate(root.items, start=5): pass"))
    assert spec.enumerate_start == 5


def test_sorted_requires_key():
    with pytest.raises(LoopIterError, match="key"):
        parse_for_iter(_iter("for x in sorted(root.items): pass"))


def test_sorted_key_and_reverse():
    spec = parse_for_iter(_iter('for x in sorted(root.items, key="price", reverse=True): pass'))
    assert spec.sort_key == "price"
    assert spec.sort_reverse is True


def test_enumerate_of_sorted_composes():
    spec = parse_for_iter(
        _iter('for i, x in enumerate(sorted(root.items, key="price"), start=1): pass')
    )
    assert spec.enumerate_start == 1
    assert spec.sort_key == "price"
    assert ast.dump(spec.array_expr) == ast.dump(ast.parse("root.items", mode="eval").body)


def test_bad_target_shape_raises():
    with pytest.raises(LoopIterError):
        parse_for_target(_target("for a, b, c in y: pass"))


def test_parse_filtering_comprehension_inside_enumerate_and_around_sorted():
    import ast

    from compiler.loop_iter import parse_for_iter

    node = ast.parse(
        'enumerate([x for x in sorted(root.items, key="p", reverse=True) if x.a == 1 if x.b], start=1)',
        mode="eval",
    ).body
    spec = parse_for_iter(node)
    assert (spec.enumerate_start, spec.sort_key, spec.sort_reverse, spec.filter_var) == (
        1,
        "p",
        True,
        "x",
    )
    assert ast.unparse(spec.array_expr) == "root.items"
    assert ast.unparse(spec.filter_expr) == "x.a == 1 and x.b"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "src",
    [
        "[x.id for x in root.items if x.a]",  # a projection, not a filter
        "[x for x in root.items]",  # no condition
        "[x for x in root.items for y in x.sub if y]",  # two `for` clauses
    ],
)
def test_parse_rejects_non_filter_comprehensions(src: str):
    import ast

    from compiler.loop_iter import LoopIterError, parse_for_iter

    with pytest.raises(LoopIterError):
        parse_for_iter(ast.parse(src, mode="eval").body)
