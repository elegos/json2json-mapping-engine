"""An object whose Source selects one list element: `$.list[condition]`."""

from __future__ import annotations

import pytest

from compiler.pipeline import compile_source
from transpiler.check import check_functional
from transpiler.edit import set_source
from transpiler.model import FnYamlError, ObjectRule, parse_functional
from transpiler.selector import normalize_condition, split_selector
from transpiler.serialize import functional_to_raw
from transpiler.transpile import transpile_file_model


def tree(source: str = "$.myList[discriminator = 'MY D' and other = $.rootElement]"):
    return parse_functional(
        {
            "id": "t",
            "rules": [
                {"kind": "field", "field": "A", "type": "str", "source": {"path": "id"}},
                {
                    "kind": "object",
                    "output": "MyObject",
                    "source": source,
                    "rules": [
                        {
                            "kind": "field",
                            "field": "Id",
                            "type": "str",
                            "source": {"path": "remarks"},
                            "transform": {"expression": 'split_first(value, "|")'},
                        },
                        {
                            "kind": "field",
                            "field": "Name",
                            "type": "str",
                            "source": {"path": "name"},
                        },
                    ],
                },
            ],
        },
        "t",
    )


def test_split_finds_the_condition_but_not_a_position() -> None:
    assert split_selector("$.l[a = 'x]']") == ("$.l", "a = 'x]'")
    assert split_selector("$.a[0].l[b == 1 and c[0] == 2]") == ("$.a[0].l", "b == 1 and c[0] == 2")
    for plain in ("$.l", "$.l[*]", "$.l[0]", "$.l[]"):
        assert split_selector(plain) is None


def test_the_condition_is_written_in_full() -> None:
    assert (
        normalize_condition("discriminator = 'a=b' and other == $.r and not @.z and f(x) > n")
        == "@.discriminator == 'a=b' and @.other == $.r and not @.z and f(@.x) > @.n"
    )


def test_the_loader_spells_out_source_and_children() -> None:
    obj = tree().rules[1]
    assert isinstance(obj, ObjectRule)
    assert obj.source == "$.myList[@.discriminator == 'MY D' and @.other == $.rootElement]"
    assert obj.rules[0].source_path == "@.remarks"  # type: ignore[union-attr]
    assert functional_to_raw(tree())["rules"][1]["source"] == obj.source


def test_a_source_without_a_condition_or_with_a_guard_is_rejected() -> None:
    with pytest.raises(FnYamlError, match="selects one element"):
        tree("$.myList[*]")
    raw = functional_to_raw(tree())
    raw["rules"][1]["guard"] = "$.x"
    with pytest.raises(FnYamlError, match="guard or a source"):
        parse_functional(raw, "t")


def test_transpile_loops_over_the_list_and_returns_the_first_match() -> None:
    text = transpile_file_model(tree())
    assert "for myo_src in root.myList:" in text
    assert "if not (myo_src.discriminator == 'MY D' and myo_src.other == root.rootElement):" in text
    assert "return myo_list[0]" in text
    assert "out.MyObject = myo_first(root)" in text
    compile_source(text, "t")  # and it compiles


def test_a_selecting_object_inside_another_object() -> None:
    raw = {
        "id": "t",
        "rules": [
            {
                "kind": "object",
                "output": "Outer",
                "rules": [
                    {
                        "kind": "object",
                        "output": "Inner",
                        "source": "@root.items[kind = 'x']",
                        "rules": [
                            {
                                "kind": "field",
                                "field": "K",
                                "type": "str",
                                "source": {"path": "kind"},
                            }
                        ],
                    }
                ],
            }
        ],
    }
    text = transpile_file_model(parse_functional(raw, "t"))
    assert "Inner=" in text and "_first(root)" in text
    compile_source(text, "t")


SCHEMA_IN = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "rootElement": {"type": "string"},
        "myList": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "discriminator": {"type": "string"},
                    "other": {"type": "string"},
                    "remarks": {"type": "string"},
                    "name": {"type": "string"},
                },
            },
        },
    },
}
SCHEMA_OUT = {
    "type": "object",
    "properties": {
        "A": {"type": "string"},
        "MyObject": {
            "type": "object",
            "properties": {"Id": {"type": "string"}, "Name": {"type": "string"}},
            "required": ["Id", "Name"],
        },
    },
    "required": ["A"],
}


def test_check_resolves_the_item_fields_against_the_input_schema() -> None:
    errors = [i for i in check_functional(tree(), SCHEMA_IN, SCHEMA_OUT) if i.severity == "error"]
    assert errors == []
    bad = tree("$.myList[nope = 'x']")
    messages = [i.message for i in check_functional(bad, SCHEMA_IN, SCHEMA_OUT)]
    assert any("nope" in m for m in messages)
    missing_list = tree("$.nolist[a = 1]")
    assert any(
        "nolist" in i.message and i.column == "source"
        for i in check_functional(missing_list, SCHEMA_IN, SCHEMA_OUT)
    )


def test_set_source_on_an_object() -> None:
    file = tree("$.myList[a = 1]")
    changed = set_source(file, "rules[1]", "myList[d = 'z']")
    obj = changed.rules[1]
    assert isinstance(obj, ObjectRule) and obj.source == "$.myList[@.d == 'z']"
    plain = set_source(file, "rules[1]", "")
    assert isinstance(plain.rules[1], ObjectRule) and plain.rules[1].source is None
    with pytest.raises(FnYamlError, match="selects one element"):
        set_source(file, "rules[1]", "myList")
    # inside it a bare Source is relative to the selected element
    inner = set_source(file, "rules[1].rules[1]", "name")
    assert inner.rules[1].rules[1].source_path == "@.name"  # type: ignore[union-attr]
