"""A loop over the document itself (`source: $`): the one element of an output list, built from
the whole message (docs/ARCHITECTURE.md, §Loops)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli import import_plan
from tests.track1.transpiler.test_aggregate_by import plan

INPUT = {
    "type": "object",
    "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "n": {"type": "integer"}},
}
OUTPUT = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "label": {"type": "string"}},
                "required": ["key"],
            },
        }
    },
}


def test_a_loop_over_the_document_writes_one_element(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(INPUT))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(OUTPUT))
    (tmp_path / "import" / "m").mkdir(parents=True)
    loop = {"id": "entries", "kind": "loop", "label": "doc", "source": "$", "output": "entries[*]"}
    key = {"id": "key", "kind": "field", "field": "key", "type": "str", "source": {"path": "@.id"}}
    label = {
        "id": "label", "kind": "field", "field": "label", "type": "str", "required": False,
        "transform": {"expression": "concat(@.id, \"/\", @.name)"},
    }  # fmt: skip
    body = plan(loop, key, label)
    body["rules"][1]["proposal"]["parent_rule"] = "entries"
    body["rules"][2]["proposal"]["parent_rule"] = "entries"
    body["tests"] = [
        {"id": "t", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"id": "A1", "name": "Ann"},
         "expected": {"entries": [{"key": "A1", "label": "A1/Ann"}]}},
        {"id": "u", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"id": "B2"}, "expected": {"entries": [{"key": "B2", "label": "B2/"}]}},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    monkeypatch.chdir(tmp_path)
    result = import_plan.run_cases(tmp_path, "m")
    assert result.get("compile_error") is None, result
    assert result["ok"] is True and (result["pass"], result["fail"], result["error"]) == (
        2,
        0,
        0,
    ), result


def test_a_loop_over_an_object_that_is_not_the_document_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inp = {
        "type": "object",
        "properties": {"sub": {"type": "object", "properties": {"id": {"type": "string"}}}},
    }
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(inp))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(OUTPUT))
    (tmp_path / "import" / "m").mkdir(parents=True)
    loop = {
        "id": "entries",
        "kind": "loop",
        "label": "doc",
        "source": "$.sub",
        "output": "entries[*]",
    }
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(plan(loop)))
    monkeypatch.chdir(tmp_path)
    result = import_plan.assemble(tmp_path, "m")
    assert any("is an object" in d["message"] for d in result["diagnostics"]), result["diagnostics"]


def test_several_loops_can_add_to_one_list_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inp = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "fines": {
                "type": "array",
                "items": {"type": "object", "properties": {"amount": {"type": "number"}}},
            },
        },
    }
    out = {
        "type": "object",
        "properties": {
            "notes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"seq": {"type": "integer"}, "text": {"type": "string"}},
                },
            }
        },
    }
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(inp))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(out))
    (tmp_path / "import" / "m").mkdir(parents=True)

    def loop(rid: str, source: str, flt: str | None = None) -> dict:
        found = {"id": rid, "kind": "loop", "label": rid, "source": source, "output": "notes[*]"}
        return {**found, "filter": flt} if flt else found

    def field(rid: str, name: str, type_: str, expr: str, parent: str) -> dict:
        return {
            "id": rid,
            "kind": "field",
            "field": name,
            "type": type_,
            "transform": {"expression": expr},
            "_parent": parent,
        }

    rules = [
        loop("first", "$", "@.id != None"),
        field("first_seq", "seq", "int", "1", "first"),
        field("first_text", "text", "str", "concat('ref ', @.id)", "first"),
        loop("fines", "$.fines[*]"),
        field("fines_seq", "seq", "int", "2", "fines"),
        field("fines_text", "text", "str", "to_string(@.amount)", "fines"),
    ]
    body = plan(*[{k: v for k, v in r.items() if k != "_parent"} for r in rules])
    for plan_rule, rule in zip(body["rules"], rules, strict=True):
        if "_parent" in rule:
            plan_rule["proposal"]["parent_rule"] = rule["_parent"]
    body["tests"] = [
        {"id": "t", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"id": "A", "fines": [{"amount": 1.5}, {"amount": 2}]},
         "expected": {"notes": [{"seq": 1, "text": "ref A"}, {"seq": 2, "text": "1.5"}, {"seq": 2, "text": "2"}]}},
        {"id": "u", "origin": {"sheet": "S"}, "trust": "invented", "input": {"fines": []}, "expected": {"notes": []}},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    monkeypatch.chdir(tmp_path)
    result = import_plan.run_cases(tmp_path, "m")
    assert result.get("compile_error") is None and result["ok"] is True, result
    saved = json.loads((tmp_path / "import" / "m" / "ir.json").read_text())
    details = [t["detail"] for t in saved["tests"]]
    assert (result["pass"], result["fail"], result["error"]) == (2, 0, 0), details


def test_loops_inside_an_object_can_add_to_one_list_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = {
        "type": "object",
        "properties": {"seq": {"type": "integer"}, "text": {"type": "string"}},
    }
    inp = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "fines": {
                "type": "array",
                "items": {"type": "object", "properties": {"amount": {"type": "number"}}},
            },
        },
    }
    out = {
        "type": "object",
        "properties": {
            "body": {
                "type": "object",
                "properties": {
                    "notes": {
                        "type": "object",
                        "properties": {"items": {"type": "array", "items": item}},
                    }
                },
            }
        },
    }
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(inp))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(out))
    (tmp_path / "import" / "m").mkdir(parents=True)

    def loop(rid: str, source: str) -> dict:
        return {"id": rid, "kind": "loop", "label": rid, "source": source, "output": "items[*]"}

    def field(rid: str, name: str, type_: str, expr: str) -> dict:
        return {
            "id": rid,
            "kind": "field",
            "field": name,
            "type": type_,
            "transform": {"expression": expr},
        }

    rules = [
        ({"id": "body", "kind": "object", "output": "body"}, None),
        ({"id": "notes", "kind": "object", "output": "notes"}, "body"),
        (loop("first", "$"), "notes"),
        (field("first_seq", "seq", "int", "1"), "first"),
        (field("first_text", "text", "str", "concat('ref ', @.id)"), "first"),
        (loop("fines", "$.fines[*]"), "notes"),
        (field("fines_seq", "seq", "int", "2"), "fines"),
        (field("fines_text", "text", "str", "to_string(@.amount)"), "fines"),
    ]
    body = plan(*[r for r, _ in rules])
    for plan_rule, (_, parent) in zip(body["rules"], rules, strict=True):
        if parent:
            plan_rule["proposal"]["parent_rule"] = parent
    case = {"id": "t", "origin": {"sheet": "S"}, "trust": "invented",
            "input": {"id": "A", "fines": [{"amount": 1.5}, {"amount": 2}]},
            "expected": {"body": {"notes": {"items": [
                {"seq": 1, "text": "ref A"}, {"seq": 2, "text": "1.5"}, {"seq": 2, "text": "2"}]}}}}  # fmt: skip
    body["tests"] = [case]
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    monkeypatch.chdir(tmp_path)
    result = import_plan.run_cases(tmp_path, "m")
    assert result.get("compile_error") is None and result["ok"] is True, result
    assert (result["pass"], result["fail"], result["error"]) == (1, 0, 0), result
