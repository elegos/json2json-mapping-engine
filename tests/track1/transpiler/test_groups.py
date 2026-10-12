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
    },
}
POST = {
    "type": "object",
    "required": ["operation", "id", "name"],
    "properties": {
        "operation": {"const": "POST"}, "id": {"type": "string"}, "name": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
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
