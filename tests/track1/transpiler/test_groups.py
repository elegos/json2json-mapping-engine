"""A group (`kind: object`, `output: $`): rules that write into the root under a guard. The mapping
has no notion of alternative shapes (`oneOf`); whoever writes it guards the rules of each shape."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cli import import_plan
from tests.track1.transpiler.test_aggregate_by import plan

INPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string"},
        "id": {"type": "string"},
        "name": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "items": {
            "type": "array",
            "items": {"type": "object", "properties": {"n": {"type": "string"}}},
        },
    },
}
POST = {
    "type": "object",
    "required": ["operation", "id", "name"],
    "properties": {
        "operation": {"const": "POST"}, "id": {"type": "string"}, "name": {"type": "string"},
        "rows": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}}}},
    },
}  # fmt: skip
DELETE = {
    "type": "object",
    "required": ["operation", "id"],
    "properties": {"operation": {"const": "DELETE"}, "id": {"type": "string"}},
}
OUTPUT = {"oneOf": [POST, DELETE]}


def field(rid: str, name: str, expr: str, type_: str = "str") -> dict[str, Any]:
    return {
        "id": rid,
        "kind": "field",
        "field": name,
        "type": type_,
        "transform": {"expression": expr},
    }


def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(INPUT))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(OUTPUT))
    (tmp_path / "import" / "m").mkdir(parents=True)
    rules: list[tuple[dict[str, Any], str | None]] = [
        ({"id": "post", "kind": "object", "output": "$", "guard": "$.operation == 'POST'"}, None),
        (field("post_op", "operation", '"POST"'), "post"),
        (field("post_id", "id", "$.id"), "post"),
        (field("post_name", "name", "upper($.name)"), "post"),
        (
            {"id": "delete", "kind": "object", "output": "$", "guard": "$.operation == 'DELETE'"},
            None,
        ),
        (field("delete_op", "operation", '"DELETE"'), "delete"),
        (field("delete_id", "id", "$.id"), "delete"),
    ]
    body = plan(*[r for r, _ in rules])
    for plan_rule, (_, parent) in zip(body["rules"], rules, strict=True):
        if parent:
            plan_rule["proposal"]["parent_rule"] = parent
    body["tests"] = [
        {"id": "post", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"operation": "POST", "id": "A", "name": "ann"},
         "expected": {"operation": "POST", "id": "A", "name": "ANN"}},
        {"id": "delete", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"operation": "DELETE", "id": "A", "name": "ann"},
         "expected": {"operation": "DELETE", "id": "A"}},
        {"id": "neither", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"operation": "PUT", "id": "A"}, "expected": {}},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    monkeypatch.chdir(tmp_path)
    return body


def test_each_shape_is_written_only_when_its_guard_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(tmp_path, monkeypatch)
    result = import_plan.run_cases(tmp_path, "m")
    assert result.get("compile_error") is None and result["ok"] is True, result
    saved = json.loads((tmp_path / "import" / "m" / "ir.json").read_text())
    assert [t["result"] for t in saved["tests"]] == ["pass", "pass", "pass"], saved["tests"]


def test_a_field_one_shape_requires_is_not_required_of_the_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = build(tmp_path, monkeypatch)
    body["rules"] = [r for r in body["rules"] if r["id"] != "post_id"]  # `id`: both shapes need it
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    result = import_plan.assemble(tmp_path, "m")
    assert result["diagnostics"] == [] or all(
        d["severity"] != "error" or "name" not in d["message"] for d in result["diagnostics"]
    )  # `name` is only the POST shape's: nothing asks for it from the DELETE group


def test_a_loop_inside_a_group_leaves_no_empty_list_when_the_guard_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = build(tmp_path, monkeypatch)
    loop = plan(
        {"id": "post_tags", "kind": "loop", "source": "$.items", "output": "rows[*]"},
        field("tag", "label", "@.n", "str"),
    )["rules"]
    loop[0]["proposal"]["parent_rule"] = "post"
    loop[1]["proposal"]["parent_rule"] = "post_tags"
    body["rules"] += loop
    body["tests"] = [
        {"id": "post", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"operation": "POST", "id": "A", "name": "ann", "items": [{"n": "x"}]},
         "expected": {"operation": "POST", "id": "A", "name": "ANN", "rows": [{"label": "x"}]}},
        {"id": "delete", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"operation": "DELETE", "id": "A", "name": "ann", "items": [{"n": "x"}]},
         "expected": {"operation": "DELETE", "id": "A"}},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    result = import_plan.run_cases(tmp_path, "m")
    saved = json.loads((tmp_path / "import" / "m" / "ir.json").read_text())
    assert [t["result"] for t in saved["tests"]] == ["pass", "pass"], (result, saved["tests"])


def test_a_rule_that_is_its_own_parent_is_reported_not_silently_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cli.import_plan import build_tree

    body = plan(
        {"id": "loop", "kind": "loop", "source": "$.items", "output": "rows[*]"},
        field("tag", "label", "@.n"),
    )
    body["rules"][0]["proposal"]["parent_rule"] = "loop"
    body["rules"][1]["proposal"]["parent_rule"] = "loop"
    raw, skipped = build_tree(body, "m")
    assert raw["rules"] == []
    assert any("cycle" in s["reason"] for s in skipped)


def test_an_object_with_a_guard_leaves_out_the_list_it_holds_when_there_is_nothing_to_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = build(tmp_path, monkeypatch)
    schema_file = tmp_path / "schemas" / "m_output.schema.json"
    schema = json.loads(schema_file.read_text())
    schema["oneOf"][0]["properties"]["box"] = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {"type": "object", "properties": {"label": {"type": "string"}}},
            }
        },
    }
    schema_file.write_text(json.dumps(schema))
    rules = plan(
        {"id": "box", "kind": "object", "output": "box", "guard": "count(i for i in $.items) > 0"},
        {"id": "box_rows", "kind": "loop", "source": "$.items", "output": "rows[*]"},
        field("box_label", "label", "@.n"),
    )["rules"]
    rules[0]["proposal"]["parent_rule"] = "post"
    rules[1]["proposal"]["parent_rule"] = "box"
    rules[2]["proposal"]["parent_rule"] = "box_rows"
    body["rules"] += rules
    body["tests"] = [
        {"id": "some", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"operation": "POST", "id": "A", "name": "ann", "items": [{"n": "x"}]},
         "expected": {"operation": "POST", "id": "A", "name": "ANN",
                      "box": {"rows": [{"label": "x"}]}}},
        {"id": "none", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"operation": "POST", "id": "A", "name": "ann", "items": []},
         "expected": {"operation": "POST", "id": "A", "name": "ANN"}},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    result = import_plan.run_cases(tmp_path, "m")
    saved = json.loads((tmp_path / "import" / "m" / "ir.json").read_text())
    assert [t["result"] for t in saved["tests"]] == ["pass", "pass"], (result, saved["tests"])
