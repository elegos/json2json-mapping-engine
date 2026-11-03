"""`sum(expression for x in list if condition)` and its kin in a functional: it checks, it runs, and
it says what is wrong with it (docs/ARCHITECTURE.md, §Aggregation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cli import import_plan

INPUT = {
    "type": "object",
    "properties": {
        "samples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"value": {"type": "number"}, "quality": {"type": "string"}},
            },
        },
    },
}
OUTPUT = {
    "type": "object",
    "properties": {
        "okCount": {"type": "integer"},
        "okTotal": {"type": "number"},
        "okMax": {"type": "number"},
        "absTotal": {"type": "number"},
    },
}


def field(name: str, expression: str, type_: str = "number") -> dict[str, Any]:
    return {
        "id": name,
        "kind": "field",
        "field": name,
        "type": type_,
        "transform": {"expression": expression},
    }


def plan(*rules: dict[str, Any], tests: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "ir_version": 1,
        "mapping": {"id": "m", "name": "M"},
        "document": {"file": "d.xlsx", "sha256": "0", "version": {"resolved": "1.0", "origin": "assumed_default"}},
        "schemas": {"input": {"origin": "provided"}, "output": {"origin": "provided"}},
        "rules": [
            {
                "id": r["id"],
                "evidence": {"locations": [{"sheet": "S"}], "text": r["id"], "sha256": "0"},
                "target": {"path": "$." + r["id"]},
                "intent": "aggregate",
                "interpretation": r["id"],
                "confidence": {"level": "high"},
                "review": {"state": "pending"},
                "proposal": {"fn_rule": r},
            }
            for r in rules
        ],
        "questions": [],
        "discrepancies": [],
        "tests": tests or [],
    }  # fmt: skip


def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]) -> Path:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(INPUT))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(OUTPUT))
    (tmp_path / "import" / "m").mkdir(parents=True)
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    monkeypatch.chdir(tmp_path)
    return tmp_path


SAMPLES = {
    "samples": [
        {"value": 5, "quality": "OK"},
        {"value": 30, "quality": "BAD"},
        {"value": -12.5, "quality": "OK"},
        {"quality": "OK"},
    ]
}


def test_aggregates_over_a_condition_check_and_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ok = "s.quality == 'OK'"
    body = plan(
        field("okCount", f"count(s for s in $.samples if {ok})", "int"),
        field("okTotal", f"sum(s.value for s in $.samples if {ok})"),
        field("okMax", f"max(s.value for s in $.samples if {ok})"),
        field("absTotal", "sum(abs(s.value) for s in $.samples)"),
        tests=[
            {
                "id": "t",
                "origin": {"sheet": "S"},
                "trust": "invented",
                "input": SAMPLES,
                "expected": {"okCount": 3, "okTotal": -7.5, "okMax": 5, "absTotal": 47.5},
            }
        ],
    )
    root = project(tmp_path, monkeypatch, body)
    result = import_plan.run_cases(root, "m")
    assert result["ok"] is True, result["diagnostics"]
    assert (result["pass"], result["fail"], result["error"]) == (1, 0, 0), result


def checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, expression: str) -> dict[str, Any]:
    root = project(tmp_path, monkeypatch, plan(field("okTotal", expression)))
    return import_plan.assemble(root, "m")


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("sum(q.value for s in $.samples)", "'q' is not defined"),
        ("sum(s.vaule for s in $.samples)", "did you mean 'value'"),
        ("sum(s.quality for s in $.samples)", "needs numbers"),
        ("sum(a.value for a in $.samples for b in $.samples)", "one `for`"),
        ("any(s.value for s in $.samples for b in $.samples)", "one `for`"),
        ("any($.samples)", "takes a comprehension"),
    ],
)  # fmt: skip
def test_a_wrong_aggregate_is_said_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, expression: str, message: str
) -> None:
    result = checked(tmp_path, monkeypatch, expression)
    assert result["ok"] is False
    assert any(message in d["message"] for d in result["diagnostics"]), result["diagnostics"]


def test_an_aggregate_can_be_part_of_a_larger_expression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = plan(
        field("okTotal", "round(sum(s.value for s in $.samples if s.quality == 'OK') / 5, 1) + 1"),
        tests=[
            {"id": "t", "origin": {"sheet": "S"}, "trust": "invented", "input": SAMPLES,
             "expected": {"okTotal": -0.5}}
        ],
    )  # fmt: skip
    root = project(tmp_path, monkeypatch, body)
    result = import_plan.run_cases(root, "m")
    assert result["ok"] is True and result["pass"] == 1, result


def test_a_field_named_like_a_python_keyword_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inp = {"type": "object", "properties": {"return": {"type": "object", "properties": {
        "number": {"type": "string"},
        "items": {"type": "array", "items": {"type": "object", "properties": {"from": {"type": "string"}}}},
    }}}}  # fmt: skip
    out = {"type": "object", "properties": {"n": {"type": "string"}, "a": {"type": "integer"}}}
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(inp))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(out))
    (tmp_path / "import" / "m").mkdir(parents=True)
    n = {
        "id": "n",
        "kind": "field",
        "field": "n",
        "type": "str",
        "source": {"path": "$.return.number"},
    }
    a = field("a", "count(i for i in $.return.items if i.from == 'A')", "int")
    case = {"return": {"number": "R1", "items": [{"from": "A"}, {"from": "B"}, {"from": "A"}]}}
    body = plan(n, a, tests=[{"id": "t", "origin": {"sheet": "S"}, "trust": "invented",
                              "input": case, "expected": {"n": "R1", "a": 2}}])  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    monkeypatch.chdir(tmp_path)
    result = import_plan.run_cases(tmp_path, "m")
    assert result["ok"] is True and result["pass"] == 1, result
