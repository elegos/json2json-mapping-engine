import ast

import pytest

from compiler.schema_generator import resolve_schema_types
from compiler.scope_resolver import resolve_scopes
from compiler.type_checker import TypeCheckError, check_module

INPUT_SCHEMA = {
    "title": "OrderEvent",
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "amount": {"type": "number"},
        "orders": {
            "type": "array",
            "items": {
                "title": "Order",
                "type": "object",
                "properties": {
                    "price": {"type": "number"},
                    "status": {"type": "string"},
                },
                "required": ["price", "status"],
            },
        },
    },
    "required": ["id", "orders"],
}

OUTPUT_SCHEMA = {
    "title": "OrderLine",
    "type": "object",
    "properties": {
        "order_id": {"type": "string"},
        "amount": {"type": "number"},
        "note": {"type": "string", "nullable": True},
    },
    "required": ["order_id", "amount"],
}


def _check(source: str, with_input=True, with_output=True):
    tree = ast.parse(source)
    scopes = resolve_scopes(tree)
    input_schema = resolve_schema_types(INPUT_SCHEMA, "OrderEvent") if with_input else None
    output_schema = resolve_schema_types(OUTPUT_SCHEMA, "OrderLine") if with_output else None
    check_module(tree, scopes, input_schema, output_schema)


def test_valid_read_and_write_passes():
    _check(
        "def order_id(root: OrderEvent) -> str:\n"
        "    return root.id\n\n"
        "out.order_id = order_id(root)\n\n"
        "def amount(root: OrderEvent) -> number:\n"
        "    return root.amount\n\n"
        "out.amount = amount(root)\n"
    )


def test_unknown_field_read_is_an_error():
    with pytest.raises(TypeCheckError, match="does not exist"):
        _check(
            "def order_id(root: OrderEvent) -> str:\n"
            "    return root.nope\n\n"
            "out.order_id = order_id(root)\n"
            "out.amount = 1.0\n"
        )


def test_write_to_undeclared_output_field_is_an_error():
    with pytest.raises(TypeCheckError, match="undeclared"):
        _check("out.order_id = root.id\nout.amount = root.amount\nout.bogus_field = root.id\n")


def test_missing_required_output_field_is_an_error():
    with pytest.raises(TypeCheckError, match="required output field"):
        _check("out.order_id = root.id\n")  # amount never assigned


def test_type_mismatch_on_write_is_an_error():
    with pytest.raises(TypeCheckError, match="declared as 'number'"):
        _check("out.order_id = root.id\nout.amount = root.id\n")  # str into number field


def test_nullable_rule_into_required_field_is_an_error():
    with pytest.raises(TypeCheckError, match="required and non-nullable"):
        _check(
            "def maybe_amount(root: OrderEvent) -> number | None:\n"
            "    return root.amount\n\n"
            "out.order_id = root.id\n"
            "out.amount = maybe_amount(root)\n"
        )


def test_nullable_rule_into_nullable_field_is_fine():
    _check(
        "def note(root: OrderEvent) -> str | None:\n"
        "    return root.id\n\n"
        "out.order_id = root.id\n"
        "out.amount = root.amount\n"
        "out.note = note(root)\n"
    )


def test_loop_element_type_resolved_from_array_field():
    _check("for order in root.orders:\n    out.order_id = order.status\nout.amount = root.amount\n")


def test_loop_element_unknown_field_is_an_error():
    with pytest.raises(TypeCheckError, match="does not exist"):
        _check(
            "for order in root.orders:\n"
            "    out.order_id = order.nonexistent\n"
            "out.amount = root.amount\n"
        )


def test_no_schema_means_unchecked():
    # Without schemas, both bogus reads and undeclared writes pass silently.
    _check(
        "out.anything = root.whatever.deeply.nested\n",
        with_input=False,
        with_output=False,
    )


def test_coalesce_resolves_nullability_away():
    # coalesce(x, default) always produces a non-null value even if x is nullable.
    _check("out.order_id = root.id\nout.amount = coalesce(root.amount, 0.0)\n")


def test_function_param_typed_to_nested_class_is_checked():
    # `order: Order` — the parameter, not any enclosing scope, drives
    # read-checking inside the function body (the compiler's actual
    # explicit-parameter calling convention, not zero-arg closures).
    with pytest.raises(TypeCheckError, match="does not exist"):
        _check(
            "def bad(order: Order) -> str:\n"
            "    return order.nonexistent\n\n"
            "out.order_id = root.id\n"
            "out.amount = root.amount\n"
            "for order in root.orders:\n"
            "    out.order_id = bad(order)\n"
        )


def test_function_param_typed_any_is_unchecked():
    _check(
        "def whatever(x: Any) -> str:\n"
        "    return x.anything.goes\n\n"
        "out.order_id = whatever(root)\n"
        "out.amount = root.amount\n"
    )


# -- nested dataclasses vs output schema ---------------------------------------

NESTED_OUTPUT_SCHEMA = {
    "title": "Result",
    "type": "object",
    "properties": {
        "Orders": {
            "type": "array",
            "items": {
                "title": "OrderOut",
                "type": "object",
                "properties": {
                    "OrderId": {"type": "string"},
                    "Tax": {
                        "title": "TaxOut",
                        "type": "object",
                        "nullable": True,
                        "properties": {"Rate": {"type": "number"}},
                        "required": ["Rate"],
                    },
                    "Lines": {
                        "type": "array",
                        "items": {
                            "title": "LineOut",
                            "type": "object",
                            "properties": {
                                "Pos": {"type": "integer"},
                                "Price": {"type": "number"},
                                "Note": {"type": "string"},
                            },
                            "required": ["Pos", "Price"],
                        },
                    },
                },
                "required": ["OrderId", "Lines"],
            },
        }
    },
    "required": ["Orders"],
}

NESTED_BASE = (
    "@dataclass\nclass Line:\n    Pos: int\n    Price: number\n\n"
    "@dataclass\nclass Tax:\n    Rate: number\n\n"
    "@dataclass\nclass Order:\n    OrderId: str\n    Tax: Tax | None\n    Lines: list[Line]\n\n"
    "def line_rule(root: Any, l: Any, j: int) -> Line:\n"
    "    return Line(Pos=j, Price=l.price)\n\n"
    "def tax_rule(root: Any, o: Any) -> Tax | None:\n"
    "    return Tax(Rate=o.rate)\n\n"
    "def order_rule(root: Any, o: Any) -> Order:\n"
    "    lines = []\n"
    "    for j, l in enumerate(o.lines):\n"
    "        lines.append(line_rule(root, l, j))\n"
    "    return Order(OrderId=o.id, Tax=tax_rule(root, o), Lines=lines)\n\n"
    "for o in root.orders:\n"
    "    out.Orders.append(order_rule(root, o))\n"
)


def _check_nested(source: str) -> None:
    tree = ast.parse(source)
    check_module(
        tree,
        resolve_scopes(tree),
        None,
        resolve_schema_types(NESTED_OUTPUT_SCHEMA, "Result"),
    )


def test_nested_dataclasses_matching_schema_pass():
    _check_nested(NESTED_BASE)


def test_nested_undeclared_field_is_an_error():
    with pytest.raises(TypeCheckError, match=r"Orders\.Lines\[\]\.Extra.*not declared"):
        _check_nested(
            NESTED_BASE.replace(
                "    Price: number\n\n@dataclass\nclass Tax",
                "    Price: number\n    Extra: str\n\n@dataclass\nclass Tax",
                1,
            ).replace("Price=l.price)", "Price=l.price, Extra='x')")
        )


def test_nested_field_type_mismatch_is_an_error():
    with pytest.raises(TypeCheckError, match=r"Orders\.Lines\[\]\.Price.*produces 'str'"):
        _check_nested(NESTED_BASE.replace("Price: number", "Price: str", 1))


def test_nested_required_field_missing_is_an_error():
    with pytest.raises(TypeCheckError, match="required field 'Price'"):
        _check_nested(
            NESTED_BASE.replace(
                "    Price: number\n\n@dataclass\nclass Tax", "\n@dataclass\nclass Tax", 1
            ).replace("Line(Pos=j, Price=l.price)", "Line(Pos=j)")
        )


def test_nested_nullable_into_required_is_an_error():
    with pytest.raises(TypeCheckError, match="non-nullable"):
        _check_nested(NESTED_BASE.replace("OrderId: str", "OrderId: str | None", 1))


def test_nested_list_of_wrong_class_is_an_error():
    with pytest.raises(TypeCheckError, match="collects 'Tax'"):
        _check_nested(
            NESTED_BASE.replace(
                "lines.append(line_rule(root, l, j))", "lines.append(tax_rule(root, l))"
            )
        )


def test_constructor_unknown_keyword_is_an_error():
    with pytest.raises(TypeCheckError, match="has no field 'Bogus'"):
        _check_nested(NESTED_BASE.replace("Line(Pos=j,", "Line(Bogus=1, Pos=j,"))


def test_constructor_missing_field_is_an_error():
    with pytest.raises(TypeCheckError, match="missing required field"):
        _check_nested(NESTED_BASE.replace("Line(Pos=j, Price=l.price)", "Line(Pos=j)"))


def test_constructor_nullable_rule_into_non_nullable_field_is_an_error():
    with pytest.raises(TypeCheckError, match="may produce null/omit"):
        _check_nested(NESTED_BASE.replace("Tax: Tax | None", "Tax: Tax", 1))


def test_bare_return_in_non_nullable_rule_is_an_error():
    with pytest.raises(
        TypeCheckError, match="rule 'r' is annotated non-nullable but returns nothing"
    ):
        _check(
            "def r(root: OrderEvent) -> str:\n"
            "    if root.id != None:\n"
            "        return root.id\n"
            "    return\n\n"
            "out.order_id = r(root)\n",
            with_output=False,
        )


def test_return_none_in_non_nullable_rule_is_an_error():
    with pytest.raises(TypeCheckError, match="returns None"):
        _check(
            "def r(root: OrderEvent) -> str:\n    return None\n\nout.order_id = r(root)\n",
            with_output=False,
        )


def test_bare_return_in_nullable_rule_is_fine():
    _check(
        "def r(root: OrderEvent) -> str | None:\n"
        "    if root.id != None:\n"
        "        return root.id\n"
        "    return\n\n"
        "out.note = r(root)\n",
        with_output=False,
    )
