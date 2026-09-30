"""Per-rule checking (`transpiler.check`, `mapper fn check`)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from cli.main import app
from transpiler.check import check_functional, schemas_for
from transpiler.model import FieldRule, LoopRule, load_functional_file, parse_functional

PROJECT = Path(__file__).parents[3] / "desktop" / "fixtures" / "orders-project"
FN = PROJECT / "mappings" / "functional" / "orders.fn.yaml"
runner = CliRunner()


def check(mutate=None):
    tree = load_functional_file(FN)
    if mutate:
        mutate(tree)
    inp, out = schemas_for(PROJECT, "orders")
    return check_functional(tree, inp, out)


def errors(issues):
    return [(i.rule, i.column, i.message) for i in issues if i.severity == "error"]


def test_the_orders_fixture_is_clean() -> None:
    assert check() == []


def test_unknown_target_and_wrong_type() -> None:
    def mutate(tree):
        tree.rules[0].field = "Nope"
        tree.rules[1].type = "int"

    found = errors(check(mutate))
    assert ("rules[0]", "target", "'Nope' is not in the output schema") in found
    assert any(r == "rules[1]" and c == "type" for r, c, _ in found)
    # the required output field OrderId is now missing
    assert any("requires OrderId" in m for _, _, m in found)


def test_optional_rule_for_a_required_schema_field() -> None:
    def mutate(tree):
        tree.rules[0].required = False

    assert ("rules[0]", "req", "required by the output schema") in errors(check(mutate))


def test_source_and_reference_must_exist_in_the_input() -> None:
    def mutate(tree):
        tree.rules[0].source_path = "$.idd"
        tree.rules[1].transform.expression = 'lookup($.contry, $.currencies, "N/A")'
        loop = tree.rules[3]
        loop.rules[0].transform.expression = "@.skuu"

    found = errors(check(mutate))
    assert ("rules[0]", "source", "'idd' is not in the input schema") in found
    assert any(r == "rules[1]" and c == "expression" and "contry" in m for r, c, m in found)
    assert any(r == "rules[3].rules[0]" and "skuu" in m for r, _, m in found)


def test_a_method_call_is_not_a_missing_field() -> None:
    def mutate(tree):
        tree.rules[0].transform.expression = "$.id.upper()"

    assert check(mutate) == []


def test_expression_syntax_and_anchors() -> None:
    def mutate(tree):
        tree.rules[0].transform.expression = "$.id +"
        tree.rules[1].transform.expression = "@.country"  # outside a loop

    found = errors(check(mutate))
    assert any(r == "rules[0]" and c == "expression" for r, c, _ in found)
    assert any(r == "rules[1]" and "outside a loop" in m for r, _, m in found)


def test_one_bad_rule_does_not_hide_the_others() -> None:
    def mutate(tree):
        tree.rules[0].transform.expression = "$.id +"
        tree.rules[2].field = "Nope"

    rules = {r for r, _, _ in errors(check(mutate))}
    assert {"rules[0]", "rules[2]"} <= rules


def test_loop_targets_must_be_arrays_in_the_schema() -> None:
    def mutate(tree):
        loop = next(r for r in tree.rules if isinstance(r, LoopRule))
        loop.output = "$.Currency[*]"

    assert any(c == "type" for _, c, _ in errors(check(mutate)))


def test_duplicate_names_in_a_container() -> None:
    def mutate(tree):
        loop = next(r for r in tree.rules if isinstance(r, LoopRule))
        field = next(r for r in loop.rules if isinstance(r, FieldRule))
        loop.rules.append(field)

    assert any("already a rule" in m for _, _, m in errors(check(mutate)))


def test_without_schemas_only_the_form_is_checked() -> None:
    tree = load_functional_file(FN)
    tree.rules[0].field = "Nope"
    assert check_functional(tree, None, None) == []


def test_fn_check_command(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "p"
    shutil.copytree(PROJECT, project)
    monkeypatch.chdir(project)
    target = "mappings/functional/orders.fn.yaml"
    ok = runner.invoke(app, ["fn", "check", target])
    assert ok.exit_code == 0 and json.loads(ok.stdout) == {"ok": True, "diagnostics": []}

    text = (project / target).read_text().replace("field: OrderId", "field: Nope")
    (project / target).write_text(text)
    bad = runner.invoke(app, ["fn", "check", target])
    assert bad.exit_code == 1
    payload = json.loads(bad.stdout)
    assert payload["ok"] is False and payload["diagnostics"][0]["rule"] == "rules[0]"


def test_a_loop_without_a_source_is_flagged() -> None:
    from transpiler.edit import add_rule

    file = add_rule(load_functional_file(FN), None, None, "loop")
    issues = check_functional(file)
    assert any(i.column == "source" and "needs a source" in i.message for i in issues)


def _lookup_issues(table_schema: dict, field_type: str = "str", expression: str | None = None):
    inp = {"type": "object", "properties": {"c": {"type": "string"}, "t": table_schema}}
    json_type = {"str": "string", "int": "integer"}[field_type]
    out = {"type": "object", "properties": {"X": {"type": json_type}}}
    file = parse_functional(
        {
            "id": "t",
            "rules": [
                {
                    "kind": "field",
                    "field": "X",
                    "type": field_type,
                    "transform": {"expression": expression or 'lookup($.c, $.t, "N/A")'},
                }
            ],
        },
        default_id="t",
    )
    return [i.message for i in check_functional(file, inp, out) if i.severity == "error"]


def test_lookup_table_from_the_input_with_compatible_values_is_fine() -> None:
    table = {"type": "object", "additionalProperties": {"type": "string"}}
    assert _lookup_issues(table) == []
    assert _lookup_issues({"type": "object", "properties": {"a": {"type": "string"}}}) == []


def test_lookup_table_with_incompatible_values_is_an_error() -> None:
    table = {"type": "object", "additionalProperties": {"type": "integer"}}
    [message] = _lookup_issues(table)
    assert "integer values" in message and "'str'" in message
    assert _lookup_issues(table, "int") == []


def test_lookup_table_that_is_not_an_object_is_an_error() -> None:
    [message] = _lookup_issues({"type": "array", "items": {"type": "string"}})
    assert "must be an object" in message


def test_lookup_table_reference_that_does_not_exist_is_an_error() -> None:
    table = {"type": "object", "additionalProperties": {"type": "string"}}
    [message] = _lookup_issues(table, expression='lookup($.c, $.nope, "N/A")')
    assert "'nope' is not in the input schema" in message


def test_lookup_inside_a_larger_expression_only_checks_the_table_shape() -> None:
    table = {"type": "object", "additionalProperties": {"type": "integer"}}
    assert _lookup_issues(table, expression='str(lookup($.c, $.t, "N/A"))') == []
