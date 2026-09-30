"""Target / Source editing (`transpiler.edit`) and the `mapper serve` worker."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cli.serve import serve
from transpiler.edit import add_rule, basename, delete_rule, retarget, set_source
from transpiler.model import (
    FieldRule,
    FnYamlError,
    FunctionalFile,
    LoopRule,
    ObjectRule,
    functional_to_dict,
    load_functional_file,
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


def test_serve_check_op() -> None:
    project = Path(__file__).parents[3] / "desktop" / "fixtures" / "orders-project"
    tree = functional_to_dict(load_functional_file(project / "mappings/functional/orders.fn.yaml"))
    tree["rules"][0]["field"] = "Nope"
    request = {"id": 1, "op": "check", "tree": tree, "project": str(project), "stem": "orders"}
    out = io.StringIO()
    serve(io.StringIO(json.dumps(request) + "\n"), out)
    answer = json.loads(out.getvalue())
    assert answer["ok"] and answer["diagnostics"][0]["rule"] == "rules[0]"


def test_add_field_at_root_gets_a_free_name_and_is_incomplete() -> None:
    once = add_rule(tree(), None, None, "field")
    twice = add_rule(once, None, None, "field")
    assert names(twice.rules)[-2:] == ["NewField", "NewField2"]
    new = twice.rules[-1]
    assert isinstance(new, FieldRule) and new.transform.expression is None


def test_add_inside_a_loop_and_at_an_index() -> None:
    result = add_rule(tree(), "rules[2]", 0, "object")
    loop = result.rules[2]
    assert isinstance(loop, LoopRule)
    assert names(loop.rules) == ["@.NewObject", "Sku"]


def test_add_loop_has_an_empty_source_and_the_array_suffix() -> None:
    result = add_rule(tree(), None, 1, "loop")
    new = result.rules[1]
    assert isinstance(new, LoopRule) and new.source == "" and new.output == "$.NewList[*]"


def test_add_rejects_a_field_as_parent_and_an_unknown_kind() -> None:
    with pytest.raises(FnYamlError):
        add_rule(tree(), "rules[0]", None, "field")
    with pytest.raises(FnYamlError):
        add_rule(tree(), None, None, "flow")


def test_add_lookup_gets_a_file_wide_free_label() -> None:
    from transpiler.model import LookupRule

    once = add_rule(tree(), None, None, "lookup")
    twice = add_rule(once, "rules[2]", None, "lookup")
    labels = [r.label for r in (once.rules[-1], twice.rules[2].rules[-1])]  # type: ignore[union-attr]
    assert labels == ["NewLookup", "NewLookup2"]
    assert isinstance(once.rules[-1], LookupRule) and once.rules[-1].entries == {"key": "value"}


def test_delete_removes_a_rule_with_its_children() -> None:
    assert names(delete_rule(tree(), "rules[2]").rules) == ["OrderId", "Note"]
    loop_gone = delete_rule(tree(), "rules[2].rules[0]")
    assert isinstance(loop_gone.rules[2], LoopRule) and loop_gone.rules[2].rules == []


def test_serve_add_and_delete() -> None:
    lines = [
        {
            "id": 1,
            "op": "add_rule",
            "tree": functional_to_dict(tree()),
            "parent": None,
            "index": None,
            "kind": "field",
        },
        {"id": 2, "op": "delete_rule", "tree": functional_to_dict(tree()), "path": "rules[0]"},
    ]
    out = io.StringIO()
    serve(io.StringIO("\n".join(json.dumps(x) for x in lines) + "\n"), out)
    first, second = (json.loads(x) for x in out.getvalue().splitlines())
    assert first["ok"] and len(first["tree"]["rules"]) == 4
    assert second["ok"] and len(second["tree"]["rules"]) == 2


def test_a_source_that_is_a_scalar_literal_is_a_constant() -> None:
    for text, value in (("27", 27), ("-1.5", -1.5), ("true", True), ("null", None), ('"x"', "x")):
        result = set_source(tree(), "rules[0]", text)
        rule = result.rules[0]
        assert isinstance(rule, FieldRule)
        assert rule.has_constant and rule.source_constant == value and rule.source_path is None


def test_changing_a_constant_back_to_a_path_and_rejecting_structures() -> None:
    constant = set_source(tree(), "rules[0]", "27")
    path = set_source(constant, "rules[0]", "id")
    rule = path.rules[0]
    assert isinstance(rule, FieldRule) and not rule.has_constant and rule.source_path == "$.id"
    with pytest.raises(FnYamlError):
        set_source(tree(), "rules[0]", "[1, 2]")
