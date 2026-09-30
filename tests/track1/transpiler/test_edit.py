"""Target / Source editing (`transpiler.edit`) and the `mapper serve` worker."""

from __future__ import annotations

import io
import json

import pytest

from cli.serve import serve
from transpiler.edit import basename, retarget, set_source
from transpiler.model import (
    FieldRule,
    FnYamlError,
    FunctionalFile,
    LoopRule,
    ObjectRule,
    functional_to_dict,
    parse_functional,
)

RAW = {
    "id": "t",
    "rules": [
        {
            "kind": "field",
            "id": "a",
            "field": "OrderId",
            "type": "str",
            "transform": {"expression": "$.id"},
        },
        {
            "kind": "field",
            "id": "b",
            "field": "Note",
            "type": "str",
            "transform": {"expression": "$.note"},
        },
        {
            "kind": "loop",
            "id": "l",
            "source": "$.items[*]",
            "output": "$.Lines[*]",
            "label": "item",
            "rules": [
                {
                    "kind": "field",
                    "id": "s",
                    "field": "Sku",
                    "type": "str",
                    "transform": {"expression": "@item.sku"},
                }
            ],
        },
    ],
}


def tree() -> FunctionalFile:
    return parse_functional(json.loads(json.dumps(RAW)), default_id="t")


def names(rules) -> list[str]:
    return [r.field if isinstance(r, FieldRule) else r.output for r in rules]


def test_dollar_and_bare_are_the_same_field() -> None:
    assert names(retarget(tree(), "rules[0]", "$.Id2").rules)[0] == "Id2"
    assert names(retarget(tree(), "rules[0]", "Id2").rules)[0] == "Id2"


def test_dotted_target_creates_the_object_and_moves_the_field() -> None:
    result = retarget(tree(), "rules[1]", "Customer.Note")
    assert names(result.rules) == ["OrderId", "$.Lines[*]", "$.Customer"]
    customer = result.rules[2]
    assert isinstance(customer, ObjectRule) and names(customer.rules) == ["Note"]


def test_second_dotted_target_reuses_the_object() -> None:
    once = retarget(tree(), "rules[1]", "Customer.Note")
    twice = retarget(once, "rules[0]", "Customer.Id")
    customers = [r for r in twice.rules if isinstance(r, ObjectRule)]
    assert len(customers) == 1 and names(customers[0].rules) == ["Note", "Id"]


def test_nested_containers_use_the_relative_prefix() -> None:
    result = retarget(tree(), "rules[1]", "A.B.C")
    a = next(r for r in result.rules if isinstance(r, ObjectRule))
    b = a.rules[0]
    assert isinstance(b, ObjectRule) and (a.output, b.output) == ("$.A", "@.B")
    assert names(b.rules) == ["C"]


def test_a_path_through_a_loop_lands_in_each_element() -> None:
    result = retarget(tree(), "rules[1]", "Lines.Tax.Rate")
    loop = next(r for r in result.rules if isinstance(r, LoopRule))
    tax = loop.rules[-1]
    assert isinstance(tax, ObjectRule) and tax.output == "@.Tax" and names(tax.rules) == ["Rate"]
    assert basename(loop.output) == "Lines"


def test_bare_path_is_relative_to_the_parent_and_dollar_is_absolute() -> None:
    inside = retarget(tree(), "rules[2].rules[0]", "Info.Code")
    loop = next(r for r in inside.rules if isinstance(r, LoopRule))
    assert names(loop.rules) == ["@.Info"]
    out = retarget(tree(), "rules[2].rules[0]", "$.Sku")
    assert "Sku" in names(out.rules)  # moved to the document root


def test_errors() -> None:
    with pytest.raises(FnYamlError, match="already a rule"):
        retarget(tree(), "rules[1]", "OrderId")
    with pytest.raises(FnYamlError, match="declare the loop"):
        retarget(tree(), "rules[1]", "Parts[*].X")
    with pytest.raises(FnYamlError, match="invalid Target"):
        retarget(tree(), "rules[1]", "a b")
    with pytest.raises(FnYamlError, match="not an array"):
        retarget(tree(), "rules[1]", "X[*]")


def test_renaming_a_loop_keeps_its_array_suffix() -> None:
    result = retarget(tree(), "rules[2]", "Rows")
    assert result.rules[2].output == "$.Rows[*]"  # type: ignore[union-attr]


def test_source_gets_its_scope_prefix() -> None:
    top = set_source(tree(), "rules[0]", "id")
    assert top.rules[0].source_path == "$.id"  # type: ignore[union-attr]
    loop = set_source(tree(), "rules[2]", "orders[*]")
    assert loop.rules[2].source == "$.orders[*]"  # type: ignore[union-attr]
    nested = set_source(tree(), "rules[2].rules[0]", "sku")
    assert nested.rules[2].rules[0].source_path == "sku"  # type: ignore[union-attr]


def test_the_original_is_not_modified() -> None:
    original = tree()
    retarget(original, "rules[1]", "Customer.Note")
    assert names(original.rules) == ["OrderId", "Note", "$.Lines[*]"]


def test_serve_answers_one_line_per_request() -> None:
    requests = [
        {"id": 1, "op": "ping"},
        {
            "id": 2,
            "op": "retarget",
            "tree": functional_to_dict(tree()),
            "path": "rules[1]",
            "value": "C.Note",
        },
        {
            "id": 3,
            "op": "retarget",
            "tree": functional_to_dict(tree()),
            "path": "rules[1]",
            "value": "OrderId",
        },
        {"id": 4, "op": "nope"},
    ]
    out = io.StringIO()
    serve(io.StringIO("".join(json.dumps(r) + "\n" for r in requests) + "not json\n"), out)
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a["id"] for a in answers] == [1, 2, 3, 4, None]
    assert answers[0]["ok"] and answers[1]["ok"]
    assert answers[1]["tree"]["rules"][2]["output"] == "$.C"
    assert not answers[2]["ok"] and "already a rule" in answers[2]["error"]
    assert not answers[3]["ok"] and not answers[4]["ok"]

