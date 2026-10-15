"""`any` and `all`, aggregates inside aggregates, and aggregates in the condition of a selection:
they run as written on the Python backend and the working copy builds for PL/SQL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cli import import_plan
from tests.track1.transpiler.test_aggregate_by import plan

TEXT = {"type": "string"}
INPUT = {
    "type": "object",
    "properties": {
        "samples": {
            "type": "array",
            "items": {"type": "object", "properties": {"value": {"type": "number"}, "q": TEXT}},
        },
        "lines": {"type": "array", "items": {"type": "object", "properties": {"ref": TEXT}}},
        "packages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": TEXT,
                    "vol": {"type": "number"},
                    "items": {
                        "type": "array",
                        "items": {"type": "object", "properties": {"ref": TEXT}},
                    },
                },
            },
        },
    },
}
OUTPUT = {
    "type": "object",
    "properties": {
        "AnyBig": TEXT,
        "AllPositive": TEXT,
        "Orphans": {"type": "integer"},
        "AboveAverage": {"type": "integer"},
        "Lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"Ref": TEXT, "Vol": {"type": "number"}, "Pack": TEXT, "All": TEXT},
            },
        },
    },
}


def field(name: str, expression: str, type_: str = "str") -> dict[str, Any]:
    return {"id": name, "kind": "field", "field": name, "type": type_, "required": False,
            "transform": {"expression": expression}}  # fmt: skip


RULES = [
    field("AnyBig", "if_else(any(s.value > 10 for s in $.samples), 'yes', 'no')"),
    field(
        "AllPositive", "if_else(all(s.value > 0 for s in $.samples if s.q == 'ok'), 'yes', 'no')"
    ),
    field(
        "Orphans",
        "count(l for l in $.lines if not any(any(i.ref == l.ref for i in p.items) for p in $.packages))",
        "int",
    ),
    field(
        "AboveAverage",
        "count(s for s in $.samples if s.value > avg(x.value for x in $.samples))",
        "int",
    ),
]
LOOP = {"id": "lines", "kind": "loop", "label": "line", "source": "$.lines[*]", "output": "Lines[*]",
        "when_empty": "list"}  # fmt: skip
LINE_FIELDS = [
    {"id": "all", "kind": "field", "field": "All", "type": "str", "required": False,
     "transform": {"expression": "join((p.id for p in $.packages if p.vol > 1), ',')"}},
    {"id": "ref", "kind": "field", "field": "Ref", "type": "str", "source": {"path": "@.ref"}},
    {"id": "vol", "kind": "field", "field": "Vol", "type": "number", "required": False,
     "source": {"path": "$.packages[any(i.ref == @2.ref for i in items)].vol"}},
    {"id": "pack", "kind": "field", "field": "Pack", "type": "str", "required": False,
     "source": {"path": "$.packages[any(i.ref == @2.ref for i in items) order by vol desc].id"}},
]  # fmt: skip

DOCUMENT = {
    "samples": [{"value": 4, "q": "ok"}, {"value": 12, "q": "ok"}, {"value": 2, "q": "bad"}],
    "lines": [{"ref": "L1"}, {"ref": "L2"}, {"ref": "L3"}],
    "packages": [
        {"id": "P1", "vol": 5, "items": [{"ref": "L1"}]},
        {"id": "P2", "vol": 9, "items": [{"ref": "L1"}, {"ref": "L2"}]},
    ],
}
EXPECTED = {
    "AnyBig": "yes",
    "AllPositive": "yes",
    "Orphans": 1,  # L3 is in no package
    "AboveAverage": 1,  # average 6: only 12
    "Lines": [
        {
            "Ref": "L1",
            "Vol": 5,
            "Pack": "P2",
        },  # the first package that holds it; the best by volume
        {"Ref": "L2", "Vol": 9, "Pack": "P2", "All": "P1,P2"},
        {"Ref": "L3", "All": "P1,P2"},
    ],
}


def start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rules: list[dict[str, Any]]
) -> dict[str, Any]:
    (tmp_path / "schemas").mkdir(exist_ok=True)
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(INPUT))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(OUTPUT))
    (tmp_path / "import" / "m").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    body = plan(*rules)
    parents = {"ref": "lines", "vol": "lines", "pack": "lines", "all": "lines"}
    for rule in body["rules"]:
        if rule["id"] in parents:
            rule["proposal"]["parent_rule"] = parents[rule["id"]]
    return body


def test_any_all_and_nested_aggregates_run_as_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = start(tmp_path, monkeypatch, [*RULES, LOOP, *LINE_FIELDS])
    body["tests"] = [
        {"id": "full", "origin": {"sheet": "S"}, "trust": "invented", "input": DOCUMENT,
         "expected": EXPECTED},
        {"id": "empty", "origin": {"sheet": "S"}, "trust": "invented", "input": {},
         "expected": {"AnyBig": "no", "AllPositive": "yes", "Orphans": 0, "AboveAverage": 0,
                      "Lines": []}},
        {"id": "missing", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"samples": [{"q": "ok"}, {"value": 3, "q": "ok"}]},
         "expected": {"AnyBig": "no", "AllPositive": "no", "Orphans": 0, "AboveAverage": 0,
                      "Lines": []}},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    result = import_plan.run_cases(tmp_path, "m")
    saved = json.loads((tmp_path / "import" / "m" / "ir.json").read_text())
    details = {t["id"]: (t["result"], t.get("detail", "")) for t in saved["tests"]}
    assert result.get("compile_error") is None, result
    assert all(r == "pass" for r, _ in details.values()), details


def test_the_working_copy_builds_for_plsql(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = start(tmp_path, monkeypatch, [*RULES, LOOP, *LINE_FIELDS])
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    config = (Path(__file__).parents[3] / "desktop/fixtures/tour-project/mapper.toml").read_text()
    (tmp_path / "mapper.toml").write_text(config)  # target = plsql
    built = import_plan.assemble(tmp_path, "m")
    assert built["target_errors"] == [] and built["ok"] is True, (
        built["diagnostics"],
        built["target_errors"],
        json.loads((tmp_path / "import/m/ir.json").read_text())["rules"],
    )
