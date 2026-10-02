"""Empty rules from an output schema (`transpiler/scaffold.py`)."""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.serve import serve
from transpiler.check import check_functional
from transpiler.model import (
    FieldRule,
    FunctionalFile,
    LoopRule,
    ObjectRule,
    functional_to_dict,
    is_unfinished,
    parse_functional,
)
from transpiler.scaffold import scaffold_rules

SCHEMA = {
    "type": "object",
    "required": ["Id"],
    "properties": {
        "Id": {"type": "string", "description": "The order id"},
        "Total": {"type": ["number", "null"]},
        "Paid": {"type": "boolean"},
        "Day": {"type": "string", "format": "date"},
        "Customer": {
            "type": "object",
            "properties": {
                "Name": {"type": "string"},
                "Tags": {"type": "array", "items": {"type": "string"}},
            },
        },
        "Lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"Sku": {"type": "string"}, "Qty": {"type": "integer"}},
            },
        },
        "Free": {"type": "object"},
        "x-bad": {"type": "string"},
    },
}


def _file(*rules: dict) -> FunctionalFile:
    return parse_functional({"id": "t", "rules": list(rules)}, "t")


DONE = {
    "kind": "field",
    "id": "done",
    "field": "Id",
    "type": "str",
    "transform": {"expression": "'x'"},
}


def test_every_property_gets_an_empty_rule_laid_out_as_the_schema() -> None:
    found = scaffold_rules(_file(DONE), SCHEMA)
    rules = {(getattr(r, "field", None) or getattr(r, "output", "")): r for r in found.file.rules}
    assert list(rules) == ["Id", "Total", "Paid", "Day", "$.Customer", "$.Lines[*]"]
    assert [rules[n].type for n in ("Total", "Paid", "Day")] == ["number", "bool", "date"]  # type: ignore[union-attr]
    customer, lines = rules["$.Customer"], rules["$.Lines[*]"]
    assert isinstance(customer, ObjectRule) and isinstance(lines, LoopRule)
    assert [r.field for r in customer.rules if isinstance(r, FieldRule)] == ["Name"]
    assert [r.field for r in lines.rules if isinstance(r, FieldRule)] == ["Sku", "Qty"]
    assert lines.source == "" and is_unfinished(lines)
    assert found.added == 8  # Total Paid Day, Customer + Name, Lines + Sku + Qty
    assert sorted(found.skipped) == [
        "Customer.Tags: an array that is not of objects",
        "Free: an object with no properties listed",
        "x-bad: not a valid field name",
    ]


def test_what_the_mapping_has_is_kept_and_a_second_run_adds_nothing() -> None:
    done = _file(DONE)
    found = scaffold_rules(done, SCHEMA)
    assert found.file.rules[0] == done.rules[0]  # the rule that was there, untouched
    assert scaffold_rules(found.file, SCHEMA).added == 0
    assert done.rules[0] is not found.file.rules[0]  # the input is not modified
    assert len(done.rules) == 1


def test_a_container_that_exists_gets_its_missing_children() -> None:
    lines = {
        "kind": "loop",
        "id": "l",
        "source": "$.items[*]",
        "output": "$.Lines[*]",
        "rules": [
            {
                "kind": "field",
                "id": "sku",
                "field": "Sku",
                "type": "str",
                "source": {"path": "@.sku"},
            }
        ],
    }
    found = scaffold_rules(_file(DONE, lines), SCHEMA)
    loop = next(r for r in found.file.rules if isinstance(r, LoopRule))
    assert loop.source == "$.items[*]"
    assert [r.field for r in loop.rules if isinstance(r, FieldRule)] == ["Sku", "Qty"]


def test_the_rules_made_are_unfinished_for_the_check() -> None:
    found = scaffold_rules(_file(DONE), SCHEMA)
    issues = check_functional(found.file, None, SCHEMA)
    assert {i.severity for i in issues} == {"warning"}  # `Id` is required and done
    bare = scaffold_rules(
        _file(
            {
                "kind": "field",
                "id": "n",
                "field": "Paid",
                "type": "bool",
                "transform": {"expression": "True"},
            }
        ),
        SCHEMA,
    )
    assert [
        i.severity for i in check_functional(bare.file, None, SCHEMA) if i.code == "unfinished"
    ] == ["error"]


def test_serve_scaffold_previews_then_applies(tmp_path: Path) -> None:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "t_output.schema.json").write_text(json.dumps(SCHEMA))
    tree = functional_to_dict(_file(DONE))
    base = {"op": "scaffold", "tree": tree, "project": str(tmp_path), "stem": "t"}
    out = io.StringIO()
    requests = [
        {"id": 1, **base},
        {"id": 2, **base, "apply": True},
        {"id": 3, **base, "stem": "none"},
    ]
    serve(io.StringIO("".join(json.dumps(r) + "\n" for r in requests)), out)
    preview, applied, missing = (json.loads(line) for line in out.getvalue().splitlines())
    assert preview["ok"] and preview["added"] == 8 and "tree" not in preview
    assert applied["ok"] and len(applied["tree"]["rules"]) == 6
    assert not missing["ok"] and "no output schema" in missing["error"]
