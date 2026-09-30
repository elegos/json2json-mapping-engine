"""Per-rule checking (`transpiler.check`, `mapper fn check`)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from cli.main import app
from transpiler.check import check_functional, schemas_for
from transpiler.model import FieldRule, LoopRule, load_functional_file

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
