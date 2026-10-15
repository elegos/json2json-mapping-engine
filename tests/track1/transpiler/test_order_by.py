"""`order_by` on a loop: the list is ordered before it is walked, by keys that are expressions of the
element, with a direction and where the elements with no key go; the sort is stable."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cli import import_plan
from tests.track1.transpiler.test_aggregate_by import plan
from transpiler.model import FnYamlError, parse_functional
from transpiler.orderby import OrderKey, format_order_by, parse_order_by, split_selection_order
from transpiler.serialize import functional_to_raw

TEXT = {"type": "string"}
INPUT = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": TEXT, "code": TEXT, "rank": {"type": "number"}, "group": TEXT},
            },
        }
    },
}
OUTPUT = {
    "type": "object",
    "properties": {
        "Rows": {"type": "array", "items": {"type": "object", "properties": {"Id": TEXT}}}
    },
}


def test_the_clause_is_read_key_by_key() -> None:
    keys = parse_order_by("to_number(split_last(@.code, ',')) desc nulls first, @.id")
    assert keys == [
        OrderKey("to_number(split_last(@.code, ','))", desc=True, nulls_first=True),
        OrderKey("@.id"),
    ]
    assert format_order_by(keys) == "to_number(split_last(@.code, ',')) desc nulls first, @.id"
    assert parse_order_by("rank DESC")[0].desc and parse_order_by("rank nulls first")[0].nulls_first


def test_a_selection_condition_splits_at_order_by() -> None:
    assert split_selection_order("kind == 'K1' order by rank desc") == ("kind == 'K1'", "rank desc")
    assert split_selection_order("order by a") == ("", "a")
    assert split_selection_order("a == 'order by'") == ("a == 'order by'", None)


@pytest.mark.parametrize("text", ["", "desc", "a nulls sideways", "a, "])
def test_a_bad_clause_says_so(text: str) -> None:
    with pytest.raises(ValueError):
        parse_order_by(text)


def raw(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "m",
        "id": "m",
        "rules": [
            {"kind": "loop", "id": "rows", "source": "$.rows[*]", "output": "$.Rows[*]", **order,
             "rules": [{"kind": "field", "id": "i", "field": "Id", "type": "str", "source": {"path": "@.id"}}]}
        ],
    }  # fmt: skip


def test_the_earlier_sort_form_still_loads_and_is_written_as_order_by() -> None:
    file = parse_functional(raw({"sort": {"key": "@.rank", "reverse": True}}), "m")
    assert file.rules[0].order_by == "@.rank desc"  # type: ignore[union-attr]
    assert functional_to_raw(file)["rules"][0]["order_by"] == "@.rank desc"
    with pytest.raises(FnYamlError, match="say the same thing"):
        parse_functional(raw({"sort": {"key": "@.a"}, "order_by": "@.a"}), "m")
    with pytest.raises(FnYamlError, match="order_by"):
        parse_functional(raw({"order_by": "@.a nulls sideways"}), "m")


def run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    order_by: str,
    rows: list[dict[str, Any]],
    expected: list[str],
) -> dict[str, Any]:
    (tmp_path / "schemas").mkdir(exist_ok=True)
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(INPUT))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(OUTPUT))
    (tmp_path / "import" / "m").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    loop = {"id": "rows", "kind": "loop", "label": "r", "source": "$.rows[*]", "output": "Rows[*]",
            "order_by": order_by, "when_empty": "list"}  # fmt: skip
    field = {"id": "i", "kind": "field", "field": "Id", "type": "str", "source": {"path": "@.id"}}
    body = plan(loop, field)
    body["rules"][1]["proposal"]["parent_rule"] = "rows"
    body["tests"] = [
        {"id": "t", "origin": {"sheet": "S"}, "trust": "invented", "input": {"rows": rows},
         "expected": {"Rows": [{"Id": i} for i in expected]}},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    result = import_plan.run_cases(tmp_path, "m")
    assert result.get("compile_error") is None, result
    saved = json.loads((tmp_path / "import" / "m" / "ir.json").read_text())
    return {"result": saved["tests"][0]["result"], "detail": saved["tests"][0].get("detail", "")}


ROWS = [
    {"id": "a", "code": "X-10", "rank": 2, "group": "g1"},
    {"id": "b", "code": "X-9", "rank": 2, "group": "g2"},
    {"id": "c", "code": "X-100", "group": "g1"},
    {"id": "d", "code": "X-9", "rank": 1, "group": "g2"},
]


@pytest.mark.parametrize(
    ("order_by", "expected"),
    [
        ("@.rank", ["d", "a", "b", "c"]),  # ascending, the one with no rank last, ties in order
        ("@.rank desc", ["a", "b", "d", "c"]),  # the one with no rank still last
        ("@.rank desc nulls first", ["c", "a", "b", "d"]),
        ("@.rank nulls first", ["c", "d", "a", "b"]),
        ("to_number(split_last(@.code, '-'))", ["b", "d", "a", "c"]),  # numbers, not texts
        ("@.group, to_number(split_last(@.code, '-')) desc", ["c", "a", "b", "d"]),
        ("@.group desc, @.id desc", ["d", "b", "c", "a"]),
        ("upper(@.id) desc", ["d", "c", "b", "a"]),
    ],
)
def test_a_list_is_ordered_by_its_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, order_by: str, expected: list[str]
) -> None:
    got = run(tmp_path, monkeypatch, order_by, ROWS, expected)
    assert got["result"] == "pass", got["detail"]
    # and the document's own list is left as it was
    assert [r["id"] for r in ROWS] == ["a", "b", "c", "d"]


def test_an_order_key_of_an_unknown_type_is_refused_with_what_to_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(AssertionError, match="type of the order key .* to_number"):
        run(tmp_path, monkeypatch, "if_else(@.group == 'g1', @.rank, @.rank)", ROWS, [])


def test_the_check_reads_the_keys_against_the_input_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from transpiler.check import check_functional

    file = parse_functional(raw({"order_by": "to_number(@.nope) desc, @.rank"}), "m")
    problems = [i.message for i in check_functional(file, INPUT, OUTPUT) if i.severity == "error"]
    assert any("nope" in p and "not in the input schema" in p for p in problems)
    good = parse_functional(raw({"order_by": "to_number(@.rank) desc, @.id"}), "m")
    assert [i for i in check_functional(good, INPUT, OUTPUT) if i.severity == "error"] == []


SEL_OUTPUT = {
    "type": "object",
    "properties": {
        "Best": TEXT,
        "Last": TEXT,
        "Pick": {"type": "object", "properties": {"Id": TEXT}},
    },
}


def run_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rules: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    expected: dict[str, Any],
) -> dict[str, Any]:
    (tmp_path / "schemas").mkdir(exist_ok=True)
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(INPUT))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(SEL_OUTPUT))
    (tmp_path / "import" / "m").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    body = plan(*rules)
    for rule in body["rules"]:
        if rule["id"] == "pick_id":
            rule["proposal"]["parent_rule"] = "pick"
    body["tests"] = [
        {"id": "t", "origin": {"sheet": "S"}, "trust": "invented", "input": {"rows": rows},
         "expected": expected},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    result = import_plan.run_cases(tmp_path, "m")
    assert result.get("compile_error") is None, result
    saved = json.loads((tmp_path / "import" / "m" / "ir.json").read_text())
    return {"result": saved["tests"][0]["result"], "detail": saved["tests"][0].get("detail", "")}


def field(fid: str, name: str, path: str) -> dict[str, Any]:
    return {"id": fid, "kind": "field", "field": name, "type": "str", "required": False,
            "source": {"path": path}}  # fmt: skip


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("$.rows[order by rank].id", "d"),  # the lowest rank
        ("$.rows[order by rank desc].id", "a"),  # the highest; the first of two equal ones
        ("$.rows[group == 'g2' order by rank desc].id", "b"),
        (
            "$.rows[group = 'g1' order by rank nulls first].id",
            "c",
        ),  # the one with none, asked first
        ("$.rows[group == 'g1' order by rank desc].id", "a"),  # one with no rank is never best
        ("$.rows[order by to_number(split_last(code, '-')) desc].id", "c"),
        ("$.rows[group == 'nope' order by rank].id", None),
    ],
)
def test_a_selection_takes_the_first_element_by_its_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, expected: str | None
) -> None:
    got = run_selection(
        tmp_path,
        monkeypatch,
        [field("best", "Best", path)],
        ROWS,
        {"Best": expected} if expected else {},
    )
    assert got["result"] == "pass", got["detail"]


def test_an_object_selected_by_an_order_is_built_from_the_best_element(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pick = {
        "id": "pick",
        "kind": "object",
        "output": "Pick",
        "source": "$.rows[order by rank desc]",
    }
    inner = {
        "id": "pick_id",
        "kind": "field",
        "field": "Id",
        "type": "str",
        "source": {"path": "@.id"},
    }
    got = run_selection(tmp_path, monkeypatch, [pick, inner], ROWS, {"Pick": {"Id": "a"}})
    assert got["result"] == "pass", got["detail"]
