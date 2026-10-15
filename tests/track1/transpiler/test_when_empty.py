"""`when_empty` on a loop: a list with no element is left out or written empty. Unset, it is left
out when the output schema does not require the list, and written empty when it does."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cli import import_plan
from tests.track1.transpiler.test_aggregate_by import plan

TEXT = {"type": "string"}
ITEMS = {"type": "array", "items": {"type": "object", "properties": {"n": TEXT}}}
INPUT = {
    "type": "object",
    "properties": {"rows": ITEMS, "box": {"type": "object", "properties": {"rows": ITEMS}}},
}


def out_schema(required: list[str], box_required: list[str]) -> dict[str, Any]:
    row = {"type": "array", "items": {"type": "object", "properties": {"N": TEXT}}}
    box = {"type": "object", "properties": {"Rows": row}, "required": box_required}
    return {"type": "object", "properties": {"Rows": row, "Box": box}, "required": required}


def start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    top: str | None = None,
    inner: str | None = None,
    required: tuple[bool, bool] = (False, False),
) -> None:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(INPUT))
    schema = out_schema(["Rows"] if required[0] else [], ["Rows"] if required[1] else [])
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(schema))
    (tmp_path / "import" / "m").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    flag = {"when_empty": top} if top else {}
    inside = {"when_empty": inner} if inner else {}
    rules = [
        {"id": "rows", "kind": "loop", "label": "r", "source": "$.rows[*]", "output": "Rows[*]", **flag},
        {"id": "n", "kind": "field", "field": "N", "type": "str", "source": {"path": "@.n"}},
        {"id": "box", "kind": "object", "output": "Box"},
        {"id": "inner", "kind": "loop", "label": "i", "source": "$.box.rows[*]", "output": "Rows[*]", **inside},
        {"id": "m", "kind": "field", "field": "N", "type": "str", "source": {"path": "@.n"}},
    ]  # fmt: skip
    body = plan(*rules)
    for rule, parent in zip(body["rules"], (None, "rows", None, "box", "inner"), strict=True):
        if parent:
            rule["proposal"]["parent_rule"] = parent
    body["tests"] = [
        {"id": "some", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"rows": [{"n": "a"}], "box": {"rows": [{"n": "b"}]}},
         "expected": {"Rows": [{"N": "a"}], "Box": {"Rows": [{"N": "b"}]}}},
        {"id": "none", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"rows": [], "box": {"rows": []}},
         "expected": {"Box": {}}},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))


def result_of(tmp_path: Path, name: str = "none") -> dict[str, Any]:
    result = import_plan.run_cases(tmp_path, "m")
    assert result.get("compile_error") is None, result
    saved = json.loads((tmp_path / "import" / "m" / "ir.json").read_text())
    case = next(t for t in saved["tests"] if t["id"] == name)
    return {"result": case["result"], "detail": case.get("detail", "")}


def test_an_optional_list_with_nothing_to_list_is_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start(tmp_path, monkeypatch)
    assert result_of(tmp_path)["result"] == "pass"


def test_a_required_list_is_written_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    start(tmp_path, monkeypatch, required=(True, True))
    got = result_of(tmp_path)
    assert got["result"] == "fail"
    assert '"Rows": []' in got["detail"] and '"Box": {"Rows": []}' in got["detail"]


@pytest.mark.parametrize("where", ["top", "inner"])
def test_when_empty_list_writes_it_even_if_optional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    start(
        tmp_path,
        monkeypatch,
        top="list" if where == "top" else None,
        inner="list" if where == "inner" else None,
    )
    got = result_of(tmp_path)
    assert got["result"] == "fail"
    assert (
        ('"Rows": []' in got["detail"])
        if where == "top"
        else ('"Box": {"Rows": []}' in got["detail"])
    )


def test_the_list_is_there_when_an_element_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start(tmp_path, monkeypatch)
    assert result_of(tmp_path, "some")["result"] == "pass"


def test_leaving_out_a_required_list_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start(tmp_path, monkeypatch, top="omit", required=(True, False))
    built = import_plan.assemble(tmp_path, "m")
    assert built["ok"] is False
    assert any("cannot be left out" in d["message"] for d in built["diagnostics"])
