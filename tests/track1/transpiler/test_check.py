"""Per-rule checking (`transpiler.check`, `mapper fn check`)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from cli.main import app
from transpiler.check import check_functional, schemas_for
from transpiler.model import (
    FieldRule,
    LoopRule,
    SchemasSection,
    Transform,
    load_functional_file,
    parse_functional,
)

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
        loop = next(r for r in tree.rules if r.kind == "loop")
        loop.rules[0].transform.expression = "@.skuu"

    found = errors(check(mutate))
    assert ("rules[0]", "source", "'idd' is not in the input schema") in found
    assert any(r == "rules[1]" and c == "expression" and "contry" in m for r, c, m in found)
    assert any(r.endswith(".rules[0]") and "skuu" in m for r, _, m in found)


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
    first = tree.rules[0]
    assert isinstance(first, FieldRule)
    first.field = "Nope"
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
    # nothing defined in it yet: ignored, not malformed
    issues = check_functional(file)
    assert [
        (i.column, i.severity, i.message)
        for i in issues
        if i.rule == f"rules[{len(file.rules) - 1}]"
    ] == [("source", "warning", "ignored until a Source is defined")]
    # once a rule inside it does something, the missing Source is an error
    loop = file.rules[-1]
    assert isinstance(loop, LoopRule)
    loop.rules.append(
        FieldRule(id=None, field="X", type="str", source_path="@.x", transform=Transform("@.x"))
    )
    issues = check_functional(file)
    assert any(i.column == "source" and "needs a source" in i.message for i in issues)


def _lookup_issues(table_schema: dict, field_type: str = "str", expression: str | None = None):
    inp = {"type": "object", "properties": {"c": {"type": "string"}, "t": table_schema}}
    json_type = {"str": "string", "int": "integer", "number": "number"}[field_type]
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
    [message] = _lookup_issues(table, expression="lookup($.c, $.t, 0)")
    assert "the expression is integer" in message and "'str'" in message
    assert _lookup_issues(table, "int", "lookup($.c, $.t, 0)") == []


def test_lookup_table_that_is_not_an_object_is_an_error() -> None:
    [message] = _lookup_issues({"type": "array", "items": {"type": "string"}})
    assert "must be an object" in message


def test_lookup_table_reference_that_does_not_exist_is_an_error() -> None:
    table = {"type": "object", "additionalProperties": {"type": "string"}}
    [message] = _lookup_issues(table, expression='lookup($.c, $.nope, "N/A")')
    assert "'nope' is not in the input schema" in message


def test_lookup_default_must_fit_the_table_values() -> None:
    table = {"type": "object", "additionalProperties": {"type": "integer"}}
    [message] = _lookup_issues(table, "int", 'lookup($.c, $.t, "N/A")')
    assert "argument 3 of lookup()" in message


INT_TABLE = {"type": "object", "additionalProperties": {"type": "integer"}}
STR_TABLE = {"type": "object", "additionalProperties": {"type": "string"}}


def test_a_lookup_inside_a_function_is_checked_both_ways() -> None:
    # the values must suit the function's parameter, and its result the field
    assert _lookup_issues(INT_TABLE, "number", "round(lookup($.c, $.t, 0), 2)") == []
    [message] = _lookup_issues(INT_TABLE, "int", "round(lookup($.c, $.t, 0), 2)")
    assert "the expression is number" in message and "'int'" in message
    [message] = _lookup_issues(STR_TABLE, "number", 'round(lookup($.c, $.t, "0"), 2)')
    assert "argument 1 of round() is string" in message
    [message] = _lookup_issues(INT_TABLE, "str", 'split_first(lookup($.c, $.t, 0), "-")')
    assert "argument 1 of split_first() is integer" in message
    assert _lookup_issues(INT_TABLE, "str", "str(lookup($.c, $.t, 0))") == []


def test_expression_types_beyond_lookup() -> None:
    assert _lookup_issues(STR_TABLE, "str", 'concat($.c, "-", 1)') == []
    [message] = _lookup_issues(STR_TABLE, "int", "$.c.strip()")
    assert "the expression is string" in message
    [message] = _lookup_issues(STR_TABLE, "number", "$.c * 2")
    assert "operand of '*' is string" in message
    [message] = _lookup_issues(STR_TABLE, "int", "1 / 2")
    assert "the expression is number" in message
    [message] = _lookup_issues(STR_TABLE, "str", 'if_else($.c, "a", "b")')
    assert "argument 1 of if_else() is string" in message
    [message] = _lookup_issues(STR_TABLE, "int", 'if_else($.c == "x", 1, "b")')
    assert "a branch is string" in message
    assert _lookup_issues(STR_TABLE, "int", "project_fn($.c)") == []


def test_every_builtin_is_typed_or_knowingly_left_out() -> None:
    from compiler.backends.plsql.builtins import BUILTIN_FUNCTIONS
    from transpiler.exprtypes import HANDLED, SIGNATURES

    assert set(BUILTIN_FUNCTIONS) <= set(SIGNATURES) | HANDLED


def _named_lookup_issues(lookup_type: str | None, entries: dict, field_type: str, expression: str):
    lookup: dict = {"kind": "lookup", "label": "tab", "entries": entries}
    file = parse_functional(
        {
            "id": "t",
            "rules": [
                lookup,
                {
                    "kind": "field",
                    "field": "X",
                    "type": field_type,
                    "transform": {"expression": expression},
                },
            ],
        },
        default_id="t",
    )
    file.rules[0].type = lookup_type  # type: ignore[union-attr]  # set after loading: some tests want it invalid
    return [i.message for i in check_functional(file) if i.severity == "error"]


def test_a_lookup_rule_is_typed_by_its_declared_type() -> None:
    call = "lookup($.c, @tab, {})"
    assert _named_lookup_issues("int", {"a": 1}, "int", call.format("0")) == []
    [message] = _named_lookup_issues("int", {"a": 1}, "str", call.format("0"))
    assert "the expression is integer" in message
    # declared number: an `int` field cannot take it although the entries look like ints
    [message] = _named_lookup_issues("number", {"a": 1}, "int", call.format("0"))
    assert "the expression is number" in message
    assert _named_lookup_issues("str", {"a": "x"}, "str", call.format('"-"')) == []


def test_a_lookup_without_a_declared_type_is_typed_by_its_entries() -> None:
    call = 'lookup($.c, @tab, "-")'
    [message] = _named_lookup_issues(None, {"a": 1}, "str", "lookup($.c, @tab, 0)")
    assert "the expression is integer" in message
    assert _named_lookup_issues(None, {"a": 1, "b": "x"}, "str", call) == []  # mixed: not typed


def test_lookup_values_must_have_the_declared_type() -> None:
    [message] = _named_lookup_issues("int", {"a": 1, "b": "x"}, "int", "lookup($.c, @tab, 0)")
    assert "'b'" in message and "not a int" in message
    [message] = _named_lookup_issues("int", {"a": True}, "int", "lookup($.c, @tab, 0)")
    assert "'a'" in message
    [message] = _named_lookup_issues("bogus", {"a": 1}, "int", "0")
    assert "'type' must be one of" in message


def test_guards_and_filters_take_any_value_but_their_insides_are_checked() -> None:
    inp = {
        "type": "object",
        "properties": {
            "c": {"type": "string"},
            "items": {
                "type": "array",
                "items": {"type": "object", "properties": {"q": {"type": "string"}}},
            },
        },
    }
    raw = {
        "id": "t",
        "rules": [
            {
                "kind": "object",
                "output": "$.O",
                "guard": "$.c",  # a text as a condition: fine
                "rules": [
                    {
                        "kind": "field",
                        "field": "A",
                        "type": "str",
                        "transform": {"expression": "$.c"},
                    }
                ],
            },
            {
                "kind": "loop",
                "source": "$.items[*]",
                "output": "$.L[*]",
                "filter": "@.q * 2 > 1",  # arithmetic on text: an error
                "rules": [
                    {
                        "kind": "field",
                        "field": "B",
                        "type": "str",
                        "transform": {"expression": "@.q"},
                    }
                ],
            },
        ],
    }
    messages = [
        (i.rule, i.message) for i in check_functional(parse_functional(raw, "t"), inp, None)
    ]
    assert messages == [("rules[1]", "an operand of '*' is string, but must be numeric")]


def _value_issues(expression: str | None, source: dict, field_type: str = "str", inp=None):
    transform = {"expression": expression} if expression else {}
    file = parse_functional(
        {
            "id": "t",
            "rules": [
                {
                    "kind": "field",
                    "field": "X",
                    "type": field_type,
                    "source": source,
                    "transform": transform,
                }
            ],
        },
        default_id="t",
    )
    return [i.message for i in check_functional(file, inp, None) if i.severity == "error"]


VALUE_SCHEMA = {
    "type": "object",
    "properties": {"s": {"type": "string"}, "n": {"type": "integer"}},
}


def test_no_expression_is_typed_by_the_source() -> None:
    assert _value_issues(None, {"path": "$.s"}, "str", VALUE_SCHEMA) == []
    [message] = _value_issues(None, {"path": "$.s"}, "int", VALUE_SCHEMA)
    assert "the expression is string" in message and "'int'" in message
    assert _value_issues(None, {"path": "$.nope"}, "int", VALUE_SCHEMA) == [
        "'nope' is not in the input schema"
    ]


def test_value_is_typed_by_the_source() -> None:
    assert _value_issues("value + 1", {"path": "$.n"}, "int", VALUE_SCHEMA) == []
    messages = _value_issues("value * 2", {"path": "$.s"}, "int", VALUE_SCHEMA)
    assert any("operand of '*' is string" in m for m in messages)


def test_a_constant_source_has_its_own_type() -> None:
    assert _value_issues(None, {"constant": 27}, "int") == []
    assert _value_issues(None, {"constant": "x"}, "int")[0].startswith("the expression is string")
    assert _value_issues(None, {"constant": None}, "int") == []


def test_value_without_a_source_is_reported() -> None:
    file = parse_functional(
        {
            "id": "t",
            "rules": [
                {
                    "kind": "field",
                    "field": "X",
                    "type": "str",
                    "transform": {"expression": "value"},
                }
            ],
        },
        default_id="t",
    )
    assert [i.message for i in check_functional(file)] == [
        "`value` is used but the rule has no Source"
    ]


def _call_issues(expression: str, status: str = "auto") -> list[str]:
    key = "code_override" if status == "manual" else "expression"
    raw = {
        "id": "t",
        "rules": [
            {
                "kind": "field",
                "id": "a",
                "field": "A",
                "type": "str",
                "source": {"path": "$.name"},
                "transform": {"status": status, key: expression},
            }
        ],
    }
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    file = parse_functional(raw, "t")
    return [i.message for i in check_functional(file, schema, None) if i.severity == "error"]


def test_a_call_with_the_wrong_number_of_arguments_is_an_error() -> None:
    assert _call_issues("split_first(value)")[0].startswith(
        "split_first() takes 2 argument(s), 1 given"
    )
    assert _call_issues("split_first(value, ',')") == []
    assert _call_issues("concat(value, 'a', 'b')") == []  # variadic
    assert _call_issues("round(1.5, 1, 2)")[0].startswith("round() takes")


def test_a_code_override_error_is_on_the_status_column() -> None:
    raw = {
        "id": "t",
        "rules": [
            {
                "kind": "field",
                "id": "a",
                "field": "A",
                "type": "str",
                "transform": {"status": "manual", "code_override": "split_first(root.name)"},
            }
        ],
    }
    issues = check_functional(parse_functional(raw, "t"), None, None)
    assert [(i.column, i.severity) for i in issues] == [("status", "error")]


def test_a_code_override_is_checked_too() -> None:
    assert _call_issues("split_first(root.name)", "manual")[0].startswith("split_first() takes 2")
    assert _call_issues("split_first(root.name, ',')", "manual") == []
    block = "x = split_first(root.name)\nx"
    assert _call_issues(block, "manual")[0].startswith("split_first() takes 2")


def test_a_code_override_name_that_nothing_defines_is_an_error() -> None:
    assert _call_issues("root.name + missing", "manual") == ["'missing' is not defined"]
    assert _call_issues("x = root.name\nx + y + y", "manual") == ["'y' is not defined"]
    # `src`/`index` exist only inside a loop; the root, the block's variables and functions do
    assert _call_issues("src.name", "manual") == ["'src' is not defined"]
    assert _call_issues("index", "manual") == ["'index' is not defined"]
    ok = "parts = [p.strip() for p in str(root.name).split(',')]\nlen(parts)"
    assert _call_issues(ok, "manual") == []
    assert _call_issues("coalesce(root.name, Null)", "manual") == []


def test_schemas_for_follows_the_schemas_section(tmp_path: Path) -> None:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text('{"title": "convention"}')
    (tmp_path / "elsewhere.json").write_text('{"title": "override"}')
    assert schemas_for(tmp_path, "m") == ({"title": "convention"}, None)
    refs = SchemasSection(input="elsewhere.json", output="missing.json")
    assert schemas_for(tmp_path, "m", refs) == ({"title": "override"}, None)


def _unfinished_issues(output_schema: dict | None) -> list[tuple[str, str, str]]:
    raw = {
        "id": "t",
        "rules": [
            {"kind": "field", "id": "a", "field": "A", "type": "str"},
            {
                "kind": "field",
                "id": "b",
                "field": "B",
                "type": "str",
                "transform": {"expression": "'x'"},
            },
        ],
    }
    file = parse_functional(raw, "t")
    return [(i.rule, i.severity, i.message) for i in check_functional(file, None, output_schema)]


def test_an_unfinished_rule_is_a_warning_unless_the_output_schema_requires_it() -> None:
    assert _unfinished_issues(None) == [
        ("rules[0]", "warning", "ignored until a Source is defined")
    ]
    optional = {"type": "object", "properties": {"A": {"type": "string"}, "B": {"type": "string"}}}
    assert _unfinished_issues(optional)[0][1] == "warning"
    required = {**optional, "required": ["A"]}
    [(rule, severity, message)] = _unfinished_issues(required)
    assert (rule, severity) == ("rules[0]", "error")
    assert "required by the output schema" in message
