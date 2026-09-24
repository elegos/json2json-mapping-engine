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
        "def order_id() -> str:\n"
        "    return root.id\n\n"
        "out.order_id = order_id()\n\n"
        "def amount() -> number:\n"
        "    return root.amount\n\n"
        "out.amount = amount()\n"
    )


def test_unknown_field_read_is_an_error():
    with pytest.raises(TypeCheckError, match="does not exist"):
        _check(
            "def order_id() -> str:\n"
            "    return root.nope\n\n"
            "out.order_id = order_id()\n"
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
            "def maybe_amount() -> number | None:\n"
            "    return root.amount\n\n"
            "out.order_id = root.id\n"
            "out.amount = maybe_amount()\n"
        )


def test_nullable_rule_into_nullable_field_is_fine():
    _check(
        "def note() -> str | None:\n"
        "    return root.id\n\n"
        "out.order_id = root.id\n"
        "out.amount = root.amount\n"
        "out.note = note()\n"
    )


def test_loop_element_type_resolved_from_array_field():
    _check(
        "for order in root.orders:\n"
        "    out.order_id = order.status\n"
        "out.amount = root.amount\n"
    )


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
    _check(
        "out.order_id = root.id\n"
        "out.amount = coalesce(root.amount, 0.0)\n"
    )
