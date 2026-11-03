"""A loop over the parts of a text: `source: "split_list(<text>, <separator>)"`, the element read as
`@` (a text)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cli import import_plan
from tests.track1.transpiler.test_aggregate_by import plan

TEXT = {"type": "string"}
INPUT = {"type": "object", "properties": {"csv": TEXT, "note": TEXT}}
OUTPUT = {
    "type": "object",
    "properties": {
        "Items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "Pos": {"type": "integer"},
                    "Amount": {"type": "number"},
                    "Currency": TEXT,
                },
            },
        }
    },
}


def start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, flt: str | None
) -> dict[str, Any]:
    (tmp_path / "schemas").mkdir(exist_ok=True)
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(INPUT))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(OUTPUT))
    (tmp_path / "import" / "m").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    loop = {"id": "items", "kind": "loop", "label": "part", "source": source, "output": "Items[*]",
            "index_start": 1, **({"filter": flt} if flt else {})}  # fmt: skip
    fields = [
        {"id": "pos", "kind": "field", "field": "Pos", "type": "int", "source": {"path": "@index"}},
        {"id": "amount", "kind": "field", "field": "Amount", "type": "number", "required": False,
         "transform": {"expression": "to_number(split_nth(@, ':', 1))"}},
        {"id": "currency", "kind": "field", "field": "Currency", "type": "str", "required": False,
         "transform": {"expression": "split_nth(@, ':', 2)"}},
    ]  # fmt: skip
    body = plan(loop, *fields)
    for rule in body["rules"][1:]:
        rule["proposal"]["parent_rule"] = "items"
    return body


def test_each_part_of_a_text_is_an_element(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = start(tmp_path, monkeypatch, "split_list($.csv, ',')", "not is_empty(@)")
    body["tests"] = [
        {"id": "some", "origin": {"sheet": "S"}, "trust": "invented",
         "input": {"csv": "10:EUR,5.5:USD,,3:GBP"},
         "expected": {"Items": [{"Pos": 1, "Amount": 10, "Currency": "EUR"},
                                {"Pos": 2, "Amount": 5.5, "Currency": "USD"},
                                {"Pos": 3, "Amount": 3, "Currency": "GBP"}]}},
        {"id": "one", "origin": {"sheet": "S"}, "trust": "invented", "input": {"csv": "7:CHF"},
         "expected": {"Items": [{"Pos": 1, "Amount": 7, "Currency": "CHF"}]}},
        {"id": "none", "origin": {"sheet": "S"}, "trust": "invented", "input": {}, "expected": {}},
        {"id": "empty", "origin": {"sheet": "S"}, "trust": "invented", "input": {"csv": ""},
         "expected": {}},
    ]  # fmt: skip
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    result = import_plan.run_cases(tmp_path, "m")
    saved = json.loads((tmp_path / "import" / "m" / "ir.json").read_text())
    details = {t["id"]: (t["result"], t.get("detail", "")) for t in saved["tests"]}
    assert result.get("compile_error") is None, result
    assert all(r == "pass" for r, _ in details.values()), details


@pytest.mark.parametrize(
    "source", ["split_list($.csv, ',')", "split_list(split_nth($.note, '|', 3), ';')"]
)
def test_the_working_copy_builds_for_plsql(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    body = start(tmp_path, monkeypatch, source, None)
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(body))
    config = (Path(__file__).parents[3] / "desktop/fixtures/tour-project/mapper.toml").read_text()
    (tmp_path / "mapper.toml").write_text(config)  # target = plsql
    built = import_plan.assemble(tmp_path, "m")
    assert built["ok"] is True, (built["diagnostics"], built["target_errors"])
    sql = ""
    # the loop reads its element as a text, from a function of the functions package
    import contextlib

    from cli.build import backend_for
    from cli.config import load_config

    with contextlib.chdir(tmp_path):
        from compiler.pipeline import compile_unit
        from transpiler.model import load_functional_file
        from transpiler.transpile import transpile_file_model

        tree = load_functional_file(tmp_path / "import/m/work/m.fn.yaml")
        text = transpile_file_model(tree)
        unit = compile_unit(text, "m", backend_for(load_config()))
        sql = "\n".join(backend_for(load_config()).assemble([unit]).values())
    assert "get_String(" in sql and "split_list(" in sql
    assert "RETURN JSON_ARRAY_T IS" in sql  # the library function
