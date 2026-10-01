"""Completion of the Target / Source / Expression cells (`transpiler.complete`)."""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.serve import serve
from transpiler.check import schemas_for
from transpiler.complete import complete
from transpiler.model import functional_to_dict, load_functional_file, parse_functional

PROJECT = Path(__file__).parents[3] / "desktop" / "fixtures" / "orders-project"
FILE = load_functional_file(PROJECT / "mappings/functional/orders.fn.yaml")
INP, OUT = schemas_for(PROJECT, "orders")


def labels(path: str, column: str, text: str, cursor: int | None = None) -> list[str]:
    found = complete(FILE, path, column, text, len(text) if cursor is None else cursor, INP, OUT)
    return [i.label for i in found.items]


def index_of(rule_id: str) -> str:
    return next(f"rules[{i}]" for i, r in enumerate(FILE.rules) if r.id == rule_id)


LINES = index_of("lines")
CURRENCY = index_of("cur")


def test_dollar_dot_lists_the_input_fields() -> None:
    found = labels(CURRENCY, "expression", "lookup($.")
    assert {"id", "country", "ref", "items", "metadata", "parties"} <= set(found)


def test_a_prefix_filters_and_an_array_inserts_its_star() -> None:
    found = complete(FILE, CURRENCY, "expression", "len($.it", 8, INP, OUT)
    assert [i.label for i in found.items] == ["items"]
    assert found.items[0].insert == "items[*]" and found.items[0].detail.startswith("array")
    assert found.from_ == 6  # replaces "it"


def test_after_an_array_step_the_element_fields_are_listed() -> None:
    assert labels(CURRENCY, "expression", "count($.items[*].") == ["sku", "qty", "total"]


def test_at_dot_is_the_loop_element_and_at_alone_lists_labels() -> None:
    inside = f"{LINES}.rules[0]"
    assert labels(inside, "expression", "@.") == ["sku", "qty", "total"]
    names = labels(inside, "expression", "@")
    assert {".", "item", "countryCurrency", "metadata", "root", "index"} <= set(names)
    assert labels(inside, "expression", "@it") == ["item"]
    assert labels(inside, "expression", "@item.") == ["sku", "qty", "total"]


def test_aliases_and_root_are_anchors() -> None:
    assert labels(CURRENCY, "expression", "@metadata.") == ["source"]
    assert "id" in labels(CURRENCY, "expression", "@root.")


def test_a_bare_name_in_an_expression_offers_functions_and_value() -> None:
    found = labels(CURRENCY, "expression", "lo")
    assert "lookup" in found and "value" not in found
    assert "value" in labels(CURRENCY, "expression", "val")
    fn = complete(FILE, CURRENCY, "expression", "spl", 3, INP, OUT).items
    assert [i.label for i in fn] == ["split_first", "split_nth"]
    assert fn[0].insert == "split_first(" and fn[0].detail == "split_first(s, sep)"
    assert "before the first" in fn[0].doc and fn[0].origin == "built-in"


def test_nothing_is_offered_inside_a_string_or_without_a_known_anchor() -> None:
    assert labels(CURRENCY, "expression", 'concat("$.') == []
    assert labels(CURRENCY, "expression", "@nope.") == []


def test_source_bare_names_are_fields_of_the_current_element() -> None:
    assert "country" in labels(CURRENCY, "source", "")
    assert labels(f"{LINES}.rules[0]", "source", "") == ["sku", "qty", "total"]
    assert labels(CURRENCY, "source", "cou") == ["country"]


def test_source_condition_reads_the_element_of_the_list() -> None:
    customer = index_of("cust")
    text = "$.parties["
    assert labels(customer, "source", text) == ["role", "name", "remarks"]
    assert labels(customer, "source", text + "role = 'CUSTOMER' and na") == ["name"]


def test_target_offers_the_output_properties_not_used_by_a_sibling() -> None:
    # every output field of the fixture has a rule: only the rule's own name is left
    assert labels(CURRENCY, "target", "") == ["Currency"]
    assert labels(CURRENCY, "target", "Cu") == ["Currency"]
    assert labels(CURRENCY, "target", "Customer.") == ["Name", "Code"]
    assert labels(CURRENCY, "target", "$.Cur") == ["Currency"]


def test_target_inside_a_loop() -> None:
    family = f"{LINES}.rules[2]"
    assert labels(family, "target", "F") == ["Family"]
    assert labels(family, "target", "@.F") == ["Family"]


def test_without_schemas_only_the_names_are_offered() -> None:
    found = complete(FILE, CURRENCY, "expression", "$.", 2, None, None)
    assert found.items == []
    anchors = complete(FILE, CURRENCY, "expression", "@", 1, None, None)
    assert "countryCurrency" in [i.label for i in anchors.items]


def test_serve_complete_op() -> None:
    request = {
        "id": 1,
        "op": "complete",
        "tree": functional_to_dict(FILE),
        "project": str(PROJECT),
        "stem": "orders",
        "path": CURRENCY,
        "column": "expression",
        "text": "len($.co",
        "cursor": 8,
    }
    out = io.StringIO()
    serve(io.StringIO(json.dumps(request) + "\n"), out)
    answer = json.loads(out.getvalue())
    assert answer["ok"] and answer["from"] == 6
    assert [i["label"] for i in answer["items"]] == ["country"]


def test_code_dialect_completes_root_src_and_functions() -> None:
    file = parse_functional(
        {
            "id": "t",
            "rules": [
                {
                    "kind": "loop",
                    "id": "l",
                    "source": "$.items[*]",
                    "output": "$.Lines[*]",
                    "rules": [
                        {
                            "kind": "field",
                            "id": "s",
                            "field": "Sku",
                            "type": "str",
                            "transform": {"expression": "@.sku"},
                        }
                    ],
                }
            ],
        },
        "t",
    )
    item = {"type": "object", "properties": {"sku": {"type": "string"}}}
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "items": {"type": "array", "items": item}},
    }

    def inserts(text: str) -> list[str]:
        found = complete(file, "rules[0].rules[0]", "code", text, len(text), schema, None)
        return [i.insert for i in found.items]

    assert {"root", "src", "index", "concat(", "Null"} <= set(inserts(""))
    assert inserts("sr")[0] == "src"
    assert inserts("src.") == ["sku"]
    assert inserts("root.") == ["name", "items"]
    assert inserts("root.items[0].") == ["sku"]
    assert inserts("nope.") == []
    described = {
        i.insert: i.detail
        for i in complete(file, "rules[0].rules[0]", "code", "s", 1, schema, None).items
    }
    assert described["src"] == "element of the loop over $.items[*]"


def test_code_dialect_describes_a_selecting_object() -> None:
    file = parse_functional(
        {
            "id": "t",
            "rules": [
                {
                    "kind": "object",
                    "id": "o",
                    "output": "$.Customer",
                    "source": "$.parties[@.role == 'X']",
                    "rules": [
                        {
                            "kind": "field",
                            "id": "n",
                            "field": "Name",
                            "type": "str",
                            "source": {"path": "@.name"},
                        }
                    ],
                }
            ],
        },
        "t",
    )
    found = complete(file, "rules[0].rules[0]", "code", "s", 1, None, None)
    by = {i.insert: i.detail for i in found.items}
    assert by["src"].startswith("element selected by the object's Source")
    assert "index" not in by


def test_code_dialect_suggests_the_variables_assigned_above() -> None:
    file = parse_functional(
        {
            "id": "t",
            "rules": [
                {
                    "kind": "field",
                    "id": "a",
                    "field": "A",
                    "type": "str",
                    "source": {"path": "$.name"},
                }
            ],
        },
        "t",
    )
    text = "yadda = root.name\nreturn y"
    found = complete(file, "rules[0]", "code", text, len(text), None, None)
    assert [i.insert for i in found.items][:1] == ["yadda"]
    # not the variable being assigned on the line itself
    own = "yadda"
    again = complete(file, "rules[0]", "code", own, len(own), None, None)
    assert "yadda" not in [i.insert for i in again.items]
