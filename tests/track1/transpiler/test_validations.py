"""The `validations:` section of a functional file: loaded and written back, checked against the
schemas (`$` is the input for the input side and the output for the output side), and transpiled to
the directive and check functions the compiler reads."""

from __future__ import annotations

import ast
from typing import Any

import pytest

from transpiler.check import check_functional
from transpiler.model import FnYamlError, parse_functional
from transpiler.serialize import functional_to_raw
from transpiler.transpile import transpile_file_model

INPUT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "vatId": {"type": "string"},
        "qty": {"type": "number"},
    },
}
OUTPUT: dict[str, Any] = {
    "type": "object",
    "properties": {"id": {"type": "string"}, "total": {"type": "number"}},
}


def raw(**validations: Any) -> dict[str, Any]:
    return {
        "name": "V",
        "id": "v",
        "validations": validations,
        "rules": [
            {"kind": "field", "id": "id", "field": "id", "type": "str", "source": {"path": "$.id"}},
        ],
    }


VAT = {
    "id": "vat",
    "expect": "not $.vatId or (is_digits($.vatId) and length($.vatId) == 11)",
    "code": "REQ-16",
    "message": "The VAT number must have 11 digits",
}


def test_the_section_is_loaded_and_written_back_as_it_was() -> None:
    source = raw(
        input={"schema": True, "checks": [VAT, {**VAT, "id": "q", "code": "Q", "action": "warn"}]},
        output={"checks": [{"id": "t", "expect": "$.total >= 0", "code": "NEG"}]},
    )
    file = parse_functional(source, "v")
    assert file.validations.input.schema and not file.validations.output.schema
    assert [c.action for c in file.validations.input.checks] == ["reject", "warn"]
    assert file.validations.output.checks[0].message == "NEG"  # no message: the code
    written = functional_to_raw(file)["validations"]
    assert written["input"]["checks"][0] == VAT
    assert written["input"]["checks"][1]["action"] == "warn"
    assert written["output"]["checks"] == [{"id": "t", "expect": "$.total >= 0", "code": "NEG"}]
    assert parse_functional(functional_to_raw(file), "v").validations == file.validations


@pytest.mark.parametrize(
    ("validations", "message"),
    [
        ({"middle": {}}, "unknown key"),
        ({"input": {"schema": "yes"}}, "true or false"),
        ({"input": {"checks": [{"id": "a", "code": "A"}]}}, "missing required key 'expect'"),
        ({"input": {"checks": [{"expect": "1", "code": "A"}]}}, "missing required key 'id'"),
        ({"input": {"checks": [{"id": "a", "expect": "1", "code": "A", "action": "stop"}]}}, "reject"),
        ({"input": {"checks": [{"id": "a", "expect": "1", "code": "a b"}]}}, "invalid code"),
        ({"input": {"checks": [{"id": "a", "expect": " ", "code": "A"}]}}, "'expect' is empty"),
        (
            {"input": {"checks": [{"id": "a", "expect": "1", "code": "A"}]},
             "output": {"checks": [{"id": "a", "expect": "1", "code": "B"}]}},
            "used twice",
        ),
        (
            {"input": {"checks": [{"id": "a", "expect": "1", "code": "A"},
                                  {"id": "b", "expect": "1", "code": "A"}]}},
            "code 'A' is used twice",
        ),
        ({"input": {"checks": [{"id": "a", "expect": "1", "code": "SCHEMA_INPUT"}]}}, "used twice"),
    ],
)  # fmt: skip
def test_a_malformed_section_is_refused(validations: dict[str, Any], message: str) -> None:
    with pytest.raises(FnYamlError, match=message):
        parse_functional(raw(**validations), "v")


def test_the_checks_become_functions_and_a_directive() -> None:
    file = parse_functional(
        raw(
            input={"schema": True, "checks": [VAT]},
            output={"checks": [{"id": "t", "expect": "$.total >= 0", "code": "NEG"}]},
        ),
        "v",
    )
    text = transpile_file_model(file)
    tree = ast.parse(text)
    functions = {
        n.name: ast.unparse(n.body[0]) for n in tree.body if isinstance(n, ast.FunctionDef)
    }
    assert functions["check_input_vat"].startswith("return not root.vatId or")
    assert functions["check_output_t"] == "return root.total >= 0"
    directive = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "__validation__"
    )
    assert '"fn":"check_input_vat"' in directive and '"schema":true' in directive
    assert '"code":"REQ-16"' in directive and '"fn":"check_output_t"' in directive


def test_a_file_without_validations_has_no_directive() -> None:
    text = transpile_file_model(parse_functional(raw(), "v"))
    assert "__validation__" not in text and "check_" not in text


def _issues(**validations: Any) -> list[str]:
    file = parse_functional(raw(**validations), "v")
    return [f"{i.rule}: {i.message}" for i in check_functional(file, INPUT, OUTPUT)]


def test_the_input_checks_are_read_against_the_input_and_the_output_ones_against_the_output() -> (
    None
):
    assert _issues(input={"checks": [VAT]}) == []
    assert _issues(output={"checks": [{"id": "t", "expect": "$.total >= 0", "code": "N"}]}) == []
    bad_in = _issues(input={"checks": [{"id": "a", "expect": "$.vat > 0", "code": "A"}]})
    assert bad_in and "'vat' is not in the input schema" in bad_in[0]
    assert bad_in[0].startswith("validations.input.checks[0]")
    bad_out = _issues(output={"checks": [{"id": "a", "expect": "$.qty > 0", "code": "A"}]})
    assert bad_out and "'qty' is not in the output schema" in bad_out[0]


def test_an_expression_that_does_not_parse_is_reported_on_the_check() -> None:
    found = _issues(input={"checks": [{"id": "a", "expect": "$.qty >", "code": "A"}]})
    assert len(found) == 1 and found[0].startswith("validations.input.checks[0]")


def test_the_json_schema_check_needs_a_schema() -> None:
    file = parse_functional(raw(input={"schema": True}, output={"schema": True}), "v")
    found = [i.message for i in check_functional(file, INPUT, None)]
    assert found == [
        "the output is validated against its JSON Schema, but the mapping has no output schema"
    ]


def test_the_tree_goes_to_the_desktop_and_back() -> None:
    from transpiler.model import functional_from_dict, functional_to_dict

    file = parse_functional(
        raw(
            input={"schema": True, "checks": [VAT]},
            output={"checks": [{**VAT, "id": "o", "code": "O"}]},
        ),
        "v",
    )
    assert functional_from_dict(functional_to_dict(file)).validations == file.validations


def test_two_people_adding_different_checks_merge() -> None:
    import yaml

    from transpiler.merge import merge_texts

    def text(*checks: dict[str, Any]) -> str:
        return yaml.safe_dump(raw(input={"checks": list(checks)}), sort_keys=False)

    other = {"id": "b", "expect": "$.qty > 0", "code": "B"}
    third = {"id": "c", "expect": "$.qty < 9", "code": "C"}
    merged, conflicts = merge_texts(text(VAT), text(VAT, other), text(VAT, third))
    assert not conflicts
    ids = [c["id"] for c in yaml.safe_load(merged)["validations"]["input"]["checks"]]
    assert sorted(ids) == ["b", "c", "vat"]
