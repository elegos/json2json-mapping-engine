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
