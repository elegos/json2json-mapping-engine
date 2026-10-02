import json
from pathlib import Path

import pytest

from compiler.schema_generator import (
    SchemaGeneratorError,
    generate_input_stub,
    generate_output_dataclasses,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(rel: str) -> dict:
    return json.loads((FIXTURES / rel).read_text())


def test_input_stub_matches_golden_including_oneof_and_pattern_properties():
    schema = _load("order_event_input.schema.json")
    stub = generate_input_stub(schema, "OrderEvent", source="schemas/order_event_input.schema.json")
    expected = (FIXTURES / "golden_stubs" / "order_event.pyi").read_text()
    assert stub == expected


def test_output_dataclass_matches_golden():
    schema = _load("order_line_output.schema.json")
    module = generate_output_dataclasses(
        schema, "OrderLine", source="schemas/order_line_output.schema.json"
    )
    expected = (FIXTURES / "golden_dataclasses" / "order_line.py").read_text()
    assert module == expected


def test_oneof_alternatives_get_named_stubs():
    schema = _load("order_event_input.schema.json")
    stub = generate_input_stub(schema, "OrderEvent")
    assert "class PaymentCard:" in stub
    assert "class PaymentBank:" in stub
    assert "payment: PaymentCard | PaymentBank" in stub


def test_pattern_properties_falls_back_to_jsonobj():
    schema = _load("order_event_input.schema.json")
    stub = generate_input_stub(schema, "OrderEvent")
    assert "meta: JsonObj" in stub


def test_required_output_fields_have_no_default_and_come_first():
    schema = _load("order_line_output.schema.json")
    module = generate_output_dataclasses(schema, "OrderLine")
    lines = [ln for ln in module.splitlines() if ln.strip().startswith(("order_id", "shipped_at"))]
    order_id_idx = next(i for i, ln in enumerate(lines) if "order_id" in ln)
    shipped_at_idx = next(i for i, ln in enumerate(lines) if "shipped_at" in ln)
    assert order_id_idx < shipped_at_idx
    assert "    order_id: int" in module
    assert "shipped_at: date | None = None" in module


def test_unsupported_multi_type_union_raises():
    schema = {
        "type": "object",
        "properties": {"weird": {"type": ["string", "integer"]}},
    }
    with pytest.raises(SchemaGeneratorError):
        generate_input_stub(schema, "Weird")
