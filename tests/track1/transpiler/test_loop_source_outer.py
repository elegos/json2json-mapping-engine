"""A loop's `source` can start from a loop outside the one it is written in (`@2`, `@label`), as a
`filter` always could: the inner list is read from the line, not from the element in between."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli import import_plan
from tests.track1.transpiler.test_aggregate_by import plan

TEXT = {"type": "string"}
INPUT = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": TEXT,
                    "subs": {
                        "type": "array",
                        "items": {"type": "object", "properties": {"n": TEXT}},
                    },
                    "refs": {
                        "type": "array",
                        "items": {"type": "object", "properties": {"text": TEXT}},
                    },
                },
            },
        }
    },
}
REFS = {"type": "array", "items": {"type": "object", "properties": {"text": TEXT}}}
OUTPUT = {
    "type": "object",
    "properties": {
        "Lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "Id": TEXT,
                    "Subs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"N": TEXT, "Refs": REFS},
                        },
                    },
                },
            },
        }
    },
}


def start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str) -> dict:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(INPUT))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(OUTPUT))
    (tmp_path / "import" / "m").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    def rule(fid: str, **more: object) -> dict:
        return {"id": fid, **more}

    lines = rule("lines", kind="loop", label="line", source="$.lines[*]", output="Lines[*]")
    sid = rule("sid", kind="field", field="Id", type="str", source={"path": "@.id"})
    subs = rule("subs", kind="loop", label="sub", source="@.subs[*]", output="@.Subs[*]")
    sn = rule("sn", kind="field", field="N", type="str", source={"path": "@.n"})
    refs = rule("refs", kind="loop", label="ref", source=source, output="@.Refs[*]")
    text = rule("text", kind="field", field="text", type="str", source={"path": "@.text"})
    body = plan(lines, sid, subs, sn, refs, text)
    for child, parent in (("sid", "lines"), ("subs", "lines"), ("sn", "subs"),
                          ("refs", "subs"), ("text", "refs")):  # fmt: skip
        next(r for r in body["rules"] if r["id"] == child)["proposal"]["parent_rule"] = parent
    body["tests"] = [
        {"id": "t", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"lines": [{"id": "L1", "subs": [{"n": "a"}, {"n": "b"}],
                              "refs": [{"text": "x"}, {"text": "y"}]}]},
         "expected": {"Lines": [{"Id": "L1", "Subs": [
             {"N": "a", "Refs": [{"text": "x"}, {"text": "y"}]},
             {"N": "b", "Refs": [{"text": "x"}, {"text": "y"}]}]}]}},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    return body


@pytest.mark.parametrize("source", ["@2.refs[*]", "@line.refs[*]"])
def test_an_inner_loop_reads_a_list_of_the_loop_outside_its_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    start(tmp_path, monkeypatch, source)
    result = import_plan.run_cases(tmp_path, "m")
    assert result["ok"] is True, result["diagnostics"]
    assert (result["pass"], result["fail"], result["error"]) == (1, 0, 0), result


def test_a_loop_that_does_not_enclose_is_refused_with_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start(tmp_path, monkeypatch, "@3.refs[*]")
    result = import_plan.assemble(tmp_path, "m")
    assert result["ok"] is False
    assert any("does not enclose" in d["message"] for d in result["diagnostics"])
