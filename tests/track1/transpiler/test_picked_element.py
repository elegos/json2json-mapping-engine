"""A path with a condition in it, `$.items[marker = 'TOTALS'].qty`: the field of the first element
that satisfies it, read in a Source, an expression or a guard (also through a `paths` alias)."""

from __future__ import annotations

import pytest

from compiler.pipeline import compile_source
from transpiler.model import FnYamlError, parse_functional
from transpiler.selector import find_selections, replace_selections
from transpiler.transpile import transpile_file_model


def mapping(rules: list, paths: dict | None = None):
    raw: dict = {"id": "t", "rules": rules}
    if paths:
        raw["paths"] = paths
    return parse_functional(raw, "t")


def field(name: str, path: str | None = None, expression: str | None = None, **more):
    rule: dict = {"kind": "field", "field": name, "type": "str", **more}
    if path:
        rule["source"] = {"path": path}
    if expression:
        rule["transform"] = {"expression": expression}
    return rule


def test_selections_are_found_outside_strings_only() -> None:
    text = "f($.items[marker = 'a]b'].qty, '$.x[y = 1]', $.list[0], $.list[*].z, v[1 == 1])"
    (one,) = find_selections(text)
    assert (one.path, one.condition) == ("$.items", "marker = 'a]b'")
    assert replace_selections(text, lambda s: "P") == (
        "f(P.qty, '$.x[y = 1]', $.list[0], $.list[*].z, v[1 == 1])"
    )
    assert [s.path for s in find_selections("@2.rows[a = 1].b + @tot.c[d = 2].e")] == [
        "@2.rows",
        "@tot.c",
    ]


def test_a_source_with_a_condition_reads_the_first_matching_element_once() -> None:
    file = mapping(
        [
            field("Qty", "items[marker = 'TOTALS'].qty"),
            field(
                "Both",
                expression="$.items[marker = 'TOTALS'].qty + '/' + $.items[marker = 'TOTALS'].cur",
            ),
        ]
    )
    text = transpile_file_model(file)
    # one function picks the element, however many rules read it
    assert text.count("def pick_items(") == 1
    assert "qty_items_pick = pick_items(root)" in text
    assert "return qty_items_pick.qty" in text
    both = text.split("def bot(")[1].split("\nout.")[0]
    assert both.count("pick_items(root)") == 1  # read twice, found once
    compile_source(text, "t")


def test_an_alias_names_the_selection() -> None:
    file = mapping(
        [field("Qty", "@totals.qty"), field("Cur", expression="@totals.cur")],
        paths={"aliases": {"totals": "$.items[@.marker = 'TOTALS']"}},
    )
    text = transpile_file_model(file)
    assert text.count("def pick_items(") == 1
    assert "qty_totals" not in text and "return qty_items_pick.qty" in text
    assert "cur_items_pick = pick_items(root)" in text
    compile_source(text, "t")


def test_a_condition_can_read_the_loop_around_the_rule() -> None:
    file = mapping(
        [
            {
                "kind": "loop",
                "source": "$.lines[*]",
                "output": "Lines[*]",
                "rules": [
                    field("Price", expression="$.prices[sku = @2.sku].price"),
                ],
            }
        ]
    )
    # inside the loop `@` is the candidate price and `@2` the line
    text = transpile_file_model(file)
    assert "def pick_prices(root: Any, src: Any)" in text
    assert "pick_prices_src.sku == src.sku" in text
    compile_source(text, "t")


def test_a_guard_can_read_a_selection() -> None:
    file = mapping(
        [
            {
                "kind": "object",
                "output": "Totals",
                "guard": "$.items[marker = 'TOTALS'].qty > 0",
                "rules": [field("Qty", "$.items[marker = 'TOTALS'].qty")],
            }
        ]
    )
    text = transpile_file_model(file)
    assert text.count("def pick_items(") == 1
    compile_source(text, "t")


def test_a_selection_in_a_filter_or_inside_a_condition_is_refused() -> None:
    loop = {
        "kind": "loop",
        "source": "$.lines[*]",
        "output": "Lines[*]",
        "filter": "$.items[marker = 'X'].ok",
        "rules": [field("A", "@.a")],
    }
    with pytest.raises(FnYamlError, match="filter cannot hold a selection"):
        transpile_file_model(mapping([loop]))
    nested = field("A", "$.items[k = $.other[m = 1].v].a")
    with pytest.raises(FnYamlError, match="another selection"):
        transpile_file_model(mapping([nested]))


SCHEMA_IN = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "marker": {"type": "string"},
                    "qty": {"type": "number"},
                    "cur": {"type": "string"},
                },
            },
        }
    },
}


def errors(file) -> list[str]:
    from transpiler.check import check_functional

    return [i.message for i in check_functional(file, SCHEMA_IN, None) if i.severity == "error"]


def test_the_check_follows_the_path_and_reads_the_condition_against_the_schema() -> None:
    good = mapping(
        [
            field("Qty", "items[marker = 'T'].cur"),
            field("Cur", expression="$.items[marker = 'T' and qty > 1].cur"),
            field("Via", "@totals.cur"),
        ],
        paths={"aliases": {"totals": "$.items[marker = 'T']"}},
    )
    assert errors(good) == []
    bad_field = mapping([field("A", "items[marker = 'T'].nope")])
    assert any("nope" in m for m in errors(bad_field))
    bad_condition = mapping([field("A", expression="$.items[nope = 'T'].cur")])
    assert any("nope" in m for m in errors(bad_condition))
    bad_list = mapping([field("A", "nolist[a = 1].cur")])
    assert any("nolist" in m for m in errors(bad_list))
    bad_alias = mapping([field("A", "@t.cur")], paths={"aliases": {"t": "$.items[nope = 1]"}})
    assert any("nope" in m for m in errors(bad_alias))
    assert any("filter cannot hold a selection" in m for m in errors(_loop_with_selection_filter()))


def _loop_with_selection_filter():
    return mapping(
        [
            {
                "kind": "loop",
                "source": "$.items[*]",
                "output": "Lines[*]",
                "filter": "$.items[marker = 'X'].qty",
                "rules": [field("A", "@.cur")],
            }
        ]
    )


def test_the_transpiled_mapping_gives_what_the_golden_cases_expect(tmp_path) -> None:
    """The yaml of the golden mapping `pick`, transpiled and run on the Python backend."""
    import json
    from pathlib import Path

    from tests.track1.python_backend.test_python_backend import _load

    file = mapping(
        [
            field("Total", "items[marker = 'TOTALS'].qty", type="number"),
            field("Currency", "@totals.cur"),
            field("Missing", "items[marker = 'NOPE'].cur", required=False),
            {
                "kind": "loop",
                "source": "$.lines[*]",
                "output": "Lines[*]",
                "rules": [
                    field("Sku", "@.sku"),
                    field("Price", expression="$.prices[sku = @2.sku].price", type="number"),
                ],
            },
        ],
        paths={"aliases": {"totals": "$.items[marker = 'TOTALS']"}},
    )
    module = _load(tmp_path, transpile_file_model(file).replace("__id__ = 't'", ""), "pick")
    golden = Path(__file__).resolve().parents[2] / "golden/pick"
    for case in ("found", "none"):
        out, errors = module.map_pick_safe(json.loads((golden / f"{case}.input.json").read_text()))
        assert errors == []
        expected = json.loads((golden / f"{case}.expected.json").read_text())
        assert out == expected
