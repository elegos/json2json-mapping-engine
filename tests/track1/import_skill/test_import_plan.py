"""`mapper import assemble | test | apply`: the plan's rules become a checked `.fn.yaml`, the plan's
cases run against it, and the file is written to the project."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cli import import_plan
from cli.main import app

INPUT = {
    "type": "object",
    "properties": {
        "ref": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"code": {"type": "string"}, "qty": {"type": "number"}},
            },
        },
    },
}
OUTPUT = {
    "type": "object",
    "properties": {
        "note": {
            "type": "object",
            "properties": {
                "no": {"type": "string"},
                "lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer"},
                            "sku": {"type": "string"},
                            "qty": {"type": "number"},
                        },
                    },
                },
            },
        }
    },
}


def rule(rid: str, fn_rule: dict[str, Any] | None, **more: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": rid,
        "evidence": {"locations": [{"sheet": "S"}], "text": rid, "sha256": "0"},
        "target": {"path": "$." + rid},
        "intent": "copy",
        "interpretation": rid,
        "confidence": {"level": "high"},
        "review": {"state": "pending"},
        "proposal": {"fn_rule": fn_rule} if fn_rule else {"functions_missing": [{"needed": "x"}]},
    }
    out.update(more)
    return out


def plan() -> dict[str, Any]:
    def field(fid: str, name: str, path: str, expr: str | None = None, type_: str = "str") -> dict:
        fn: dict[str, Any] = {"id": fid, "kind": "field", "field": name, "type": type_}
        fn["source"] = {"path": path}
        if expr:
            fn["transform"] = {"expression": expr}
        return fn

    def nested(rid: str, fn: dict[str, Any], parent: str) -> dict[str, Any]:
        r = rule(rid, fn)
        r["proposal"]["parent_rule"] = parent
        return r

    return {
        "ir_version": 1,
        "mapping": {"id": "m", "name": "M"},
        "document": {"file": "d.xlsx", "sha256": "0", "version": {"resolved": "1.0", "origin": "assumed_default"}},
        "schemas": {"input": {"origin": "provided"}, "output": {"origin": "provided"}},
        "lookups": [{"name": "REASONS", "status": "in_document", "entries": {"D": "Damaged"}}],
        "rules": [
            rule("note", {"id": "note", "kind": "object", "output": "note"}),
            nested("no", field("no", "no", "$.ref", 'concat("CN-", trim(value))'), "note"),
            nested(
                "lines",
                {"id": "lines", "kind": "loop", "label": "line", "index_start": 1,
                 "source": "$.items[*]", "output": "lines[*]"},
                "note",
            ),
            nested("row", field("row", "row", "@index", type_="int"), "lines"),
            nested("sku", field("sku", "sku", "@.code", "upper(value)"), "lines"),
            nested("qty", field("qty", "qty", "@.qty", "abs(value)", "number"), "lines"),
            rule("gap", None),
            rule("dropped", field("dropped", "no", "$.ref"), review={"state": "rejected"}),
        ],
        "questions": [],
        "discrepancies": [],
        "tests": [
            {
                "id": "t1", "origin": {"sheet": "S"}, "trust": "paired_in_document",
                "input": {"ref": " 7 ", "items": [{"code": "ab", "qty": -2}, {"code": "c", "qty": 3}]},
                "expected": {"note": {"no": "CN-7", "lines": [
                    {"row": 1, "sku": "AB", "qty": 2}, {"row": 2, "sku": "C", "qty": 3}]}},
            },
            {
                "id": "t2", "origin": {"sheet": "S"}, "trust": "single_value",
                "input": {"ref": "8", "items": []},
                "expected": {"note": {"no": "CN-9", "lines": []}},
            },
        ],
    }  # fmt: skip


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "m_input.schema.json").write_text(json.dumps(INPUT))
    (tmp_path / "schemas" / "m_output.schema.json").write_text(json.dumps(OUTPUT))
    (tmp_path / "import" / "m").mkdir(parents=True)
    (tmp_path / "import" / "m" / "ir.json").write_text(json.dumps(plan()))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_assemble_nests_the_rules_and_records_each_check(project: Path) -> None:
    result = import_plan.assemble(project, "m")
    assert result["ok"] is True, result["diagnostics"]
    text = (project / result["file"]).read_text()
    assert text.index("kind: lookup") < text.index("kind: object") < text.index("kind: loop")
    assert text.index("kind: loop") < text.index("field: sku")
    reasons = {s["rule"]: s["reason"] for s in result["skipped"]}
    assert reasons == {"gap": "function_gap", "dropped": "rejected"}
    saved = json.loads((project / "import/m/ir.json").read_text())
    checked = {r["id"]: r["proposal"].get("check") for r in saved["rules"]}
    assert checked["sku"] == {"ran": True, "ok": True, "errors": []}
    assert checked["gap"] is None


def test_a_rule_that_does_not_check_is_reported_on_that_rule(project: Path) -> None:
    broken = plan()
    broken["rules"][4]["proposal"]["fn_rule"]["transform"]["expression"] = "shout(value)"
    (project / "import/m/ir.json").write_text(json.dumps(broken))
    result = import_plan.assemble(project, "m")
    assert result["ok"] is False
    saved = json.loads((project / "import/m/ir.json").read_text())
    sku = next(r for r in saved["rules"] if r["id"] == "sku")
    assert sku["proposal"]["check"]["ok"] is False
    assert "shout" in sku["proposal"]["check"]["errors"][0]


def test_a_parent_that_is_not_in_the_plan_is_left_out_with_the_reason(project: Path) -> None:
    orphan = plan()
    orphan["rules"][4]["proposal"]["parent_rule"] = "nowhere"
    (project / "import/m/ir.json").write_text(json.dumps(orphan))
    reasons = {s["rule"]: s["reason"] for s in import_plan.assemble(project, "m")["skipped"]}
    assert "nowhere" in reasons["sku"]


def test_cases_are_run_and_a_failing_one_becomes_a_discrepancy(project: Path) -> None:
    result = import_plan.run_cases(project, "m")
    assert (result["pass"], result["fail"], result["error"]) == (1, 1, 0)
    saved = json.loads((project / "import/m/ir.json").read_text())
    results = {t["id"]: t["result"] for t in saved["tests"]}
    assert results == {"t1": "pass", "t2": "fail"}
    (found,) = [d for d in saved["discrepancies"] if d["kind"] == "sample_contradicts_rule"]
    assert "t2" in found["detail"] and "CN-8" in found["detail"]


def test_apply_writes_the_file_once_and_marks_the_rules(project: Path) -> None:
    result = import_plan.apply(project, "m")
    destination = project / result["file"]
    assert destination.is_file() and result["file"] == "mappings/functional/m.fn.yaml"
    saved = json.loads((project / "import/m/ir.json").read_text())
    states = {r["id"]: r["review"]["state"] for r in saved["rules"]}
    assert (
        states["sku"] == "applied"
        and states["gap"] == "pending"
        and states["dropped"] == "rejected"
    )
    with pytest.raises(import_plan.PlanError, match="exists"):
        import_plan.apply(project, "m")
    assert import_plan.apply(project, "m", force=True)["ok"] is True


def test_apply_refuses_a_working_copy_that_does_not_check(project: Path) -> None:
    broken = plan()
    broken["rules"][4]["proposal"]["fn_rule"]["transform"]["expression"] = "shout(value)"
    (project / "import/m/ir.json").write_text(json.dumps(broken))
    with pytest.raises(import_plan.PlanError, match="does not check"):
        import_plan.apply(project, "m")
    assert not (project / "mappings/functional/m.fn.yaml").exists()


def test_the_commands_print_json_and_fail_on_a_missing_plan(project: Path) -> None:
    runner = CliRunner()
    ok = runner.invoke(app, ["import", "assemble", "m"])
    assert ok.exit_code == 0 and json.loads(ok.output)["ok"] is True
    ran = runner.invoke(app, ["import", "test", "m"])
    assert ran.exit_code == 0 and json.loads(ran.output)["fail"] == 1
    missing = runner.invoke(app, ["import", "assemble", "nope"])
    assert missing.exit_code == 1 and json.loads(missing.output)["ok"] is False


def test_a_required_field_nobody_writes_yet_is_a_gap_and_the_cases_still_run(
    project: Path,
) -> None:
    output = json.loads((project / "schemas/m_output.schema.json").read_text())
    note = output["properties"]["note"]
    note["properties"]["total"] = {"type": "number"}  # no rule: its function is missing
    note["required"] = ["total"]
    (project / "schemas/m_output.schema.json").write_text(json.dumps(output))
    with_gap = plan()
    with_gap["tests"] = [
        {
            "id": "t1", "origin": {"sheet": "S"}, "trust": "paired_in_document", "partial": True,
            "input": {"ref": " 7 ", "items": [{"code": "ab", "qty": -2}]},
            "expected": {"note": {"no": "CN-7", "lines": [{"row": 1, "sku": "AB", "qty": 2}]}},
        }
    ]  # fmt: skip
    (project / "import/m/ir.json").write_text(json.dumps(with_gap))
    built = import_plan.assemble(project, "m")
    assert built["ok"] is True and "total" in built["gaps"][0]
    ran = import_plan.run_cases(project, "m")
    assert (ran["pass"], ran["fail"]) == (1, 0), ran
    with pytest.raises(import_plan.PlanError, match="no rule yet"):
        import_plan.apply(project, "m")


def test_a_partial_expected_output_only_has_to_be_contained() -> None:
    contains = import_plan._contains  # pyright: ignore[reportPrivateUsage]
    assert contains({"a": 1, "b": {"c": 2, "d": 3}}, {"b": {"c": 2}})
    assert not contains({"a": 1}, {"a": 2}) and not contains({"a": 1}, {"z": 1})
    assert contains([{"x": 1, "y": 2}], [{"x": 1}]) and not contains([{"x": 1}], [])


def test_review_state_is_not_written_on_an_object_or_a_loop_and_an_empty_plan_runs_nothing(
    project: Path,
) -> None:
    flagged = plan()
    for r in flagged["rules"]:
        fn = (r["proposal"] or {}).get("fn_rule")
        if fn and fn["kind"] in ("object", "loop"):
            fn["validation"] = {"needs_review": True}
            fn["required"] = False
    (project / "import/m/ir.json").write_text(json.dumps(flagged))
    assert import_plan.assemble(project, "m")["ok"] is True
    empty = plan()
    empty["rules"] = []
    (project / "import/m/ir.json").write_text(json.dumps(empty))
    ran = import_plan.run_cases(project, "m")
    assert ran["cases"] == 2 and ran["not_run"] == 2 and "compile_error" not in ran


def test_a_lookup_the_document_does_not_give_is_written_empty_and_the_rule_runs(
    project: Path,
) -> None:
    with_table = plan()
    with_table["lookups"].append({"name": "UOM", "status": "missing", "entries": {}})
    unit = {
        "id": "unit", "kind": "field", "field": "sku", "type": "str",
        "transform": {"expression": 'lookup(lower(@.code), @UOM, "n/a")'},
    }  # fmt: skip
    sku = next(r for r in with_table["rules"] if r["id"] == "sku")
    sku["proposal"]["fn_rule"] = {**unit, "id": "sku"}
    (project / "import/m/ir.json").write_text(json.dumps(with_table))
    built = import_plan.assemble(project, "m")
    assert built["ok"] is True, built["diagnostics"]
    assert "lut_uom" in (project / built["file"]).read_text()
    ran = import_plan.run_cases(project, "m")
    saved = json.loads((project / "import/m/ir.json").read_text())
    assert saved["tests"][0]["result"] == "fail"  # the empty table finds nothing: "n/a", not "AB"
    assert '"sku": "n/a"' in saved["tests"][0]["detail"] and ran["error"] == 0


def _validated_plan() -> dict[str, Any]:
    """The plan with a check that rejects a reference that is not digits, one that warns, and the
    cases that expect them."""
    base = plan()

    def check(cid: str, side: str, expect: str, action: str) -> dict[str, Any]:
        return {
            "id": cid,
            "side": side,
            "expect": expect,
            "code": cid.upper(),
            "message": f"{cid} failed",
            "action": action,
            "evidence": {"locations": [{"sheet": "S"}], "text": cid, "sha256": "0"},
            "interpretation": f"The check {cid}.",
            "confidence": {"level": "high"},
            "review": {"state": "pending"},
        }

    base["validations"] = [
        check("ref_digits", "input", "not $.ref or is_digits($.ref)", "reject"),
        check("few_lines", "input", "count($.items) <= 1", "warn"),
        check("has_note", "output", "$.note.no", "reject"),
    ]
    base["tests"] = [
        {
            "id": "ok", "origin": {"sheet": "S"}, "trust": "paired_in_document",
            "input": {"ref": "7", "items": [{"code": "ab", "qty": 1}]},
            "expected": {"note": {"no": "CN-7", "lines": [{"row": 1, "sku": "AB", "qty": 1}]}},
            "expected_warnings": [],
        },
        {
            "id": "bad_ref", "origin": {"sheet": "S"}, "trust": "single_value",
            "input": {"ref": "x7", "items": []},
            "expected_rejected": ["REF_DIGITS"],
        },
        {
            "id": "warned", "origin": {"sheet": "S"}, "trust": "single_value",
            "input": {"ref": "7", "items": [{"code": "a", "qty": 1}, {"code": "b", "qty": 1}]},
            "expected": {"note": {"no": "CN-7"}}, "partial": True,
            "expected_warnings": ["FEW_LINES"],
        },
        {
            "id": "wrong", "origin": {"sheet": "S"}, "trust": "single_value",
            "input": {"ref": "x7", "items": []},
            "expected": {"note": {"no": "CN-x7"}},
        },
    ]  # fmt: skip
    return base


def test_checks_of_the_plan_become_the_validations_of_the_file(project: Path) -> None:
    (project / "import/m/ir.json").write_text(json.dumps(_validated_plan()))
    result = import_plan.assemble(project, "m")
    assert result["ok"] is True, result["diagnostics"]
    text = (project / result["file"]).read_text()
    assert "validations:" in text and "code: REF_DIGITS" in text and "action: warn" in text
    saved = json.loads((project / "import/m/ir.json").read_text())
    assert [v["check"]["ok"] for v in saved["validations"]] == [True, True, True]


def test_a_check_that_does_not_check_is_reported_on_that_check(project: Path) -> None:
    broken = _validated_plan()
    broken["validations"][0]["expect"] = "$.nothing_here == 1"
    (project / "import/m/ir.json").write_text(json.dumps(broken))
    assert import_plan.assemble(project, "m")["ok"] is False
    saved = json.loads((project / "import/m/ir.json").read_text())
    assert saved["validations"][0]["check"]["ok"] is False
    assert "nothing_here" in saved["validations"][0]["check"]["errors"][0]
    assert saved["validations"][1]["check"]["ok"] is True


def test_a_rejected_check_stays_out_of_the_file(project: Path) -> None:
    dropped = _validated_plan()
    dropped["validations"][0]["review"]["state"] = "rejected"
    (project / "import/m/ir.json").write_text(json.dumps(dropped))
    result = import_plan.assemble(project, "m")
    assert "REF_DIGITS" not in (project / result["file"]).read_text()
    assert {"rule": "ref_digits", "reason": "rejected"} in result["skipped"]


def test_cases_expect_an_output_or_the_codes_that_reject(project: Path) -> None:
    (project / "import/m/ir.json").write_text(json.dumps(_validated_plan()))
    result = import_plan.run_cases(project, "m")
    saved = json.loads((project / "import/m/ir.json").read_text())
    results = {t["id"]: (t["result"], t["detail"]) for t in saved["tests"]}
    assert results["ok"] == ("pass", "")
    assert results["bad_ref"] == ("pass", "")
    assert results["warned"] == ("pass", "")
    assert results["wrong"] == ("fail", "rejected by ['REF_DIGITS']")
    assert (result["pass"], result["fail"]) == (3, 1)


def test_the_schema_validation_flags_turn_the_json_schema_check_on(project: Path) -> None:
    flagged = _validated_plan()
    flagged["schema_validation"] = {"input": True}
    flagged["tests"] = [
        {
            "id": "wrong_type", "origin": {"sheet": "S"}, "trust": "single_value",
            "input": {"ref": 5, "items": []},
            "expected_rejected": ["SCHEMA_INPUT"],
        }
    ]  # fmt: skip
    (project / "import/m/ir.json").write_text(json.dumps(flagged))
    result = import_plan.run_cases(project, "m")
    assert (result["pass"], result["fail"], result["error"]) == (1, 0, 0), result


def test_what_the_target_cannot_build_is_an_error_of_the_rule(project: Path) -> None:
    """The check is the same for every backend; the backends are not: a project function with an
    implementation for Python only (no `@override(plsql=...)`) builds for one and not the other. The plan must not look fine for a project that builds
    for Oracle."""
    config = (Path(__file__).parents[3] / "desktop/fixtures/tour-project/mapper.toml").read_text()
    (project / "mapper.toml").write_text(config)
    (project / "fn").mkdir()
    (project / "fn" / "shout.fn").write_text(
        'def shout(s: str) -> str:\n    """The text in capitals."""\n    return s.upper()\n'
    )
    body = json.loads((project / "import/m/ir.json").read_text())
    for r in body["rules"]:
        if r["id"] == "sku":
            r["proposal"]["fn_rule"]["transform"] = {"expression": "shout(@.code)"}
    (project / "import/m/ir.json").write_text(json.dumps(body))
    result = import_plan.assemble(project, "m")
    assert result["ok"] is False
    saved = json.loads((project / "import/m/ir.json").read_text())
    sku = next(r for r in saved["rules"] if r["id"] == "sku")["proposal"]["check"]
    assert sku["ok"] is False and "does not build for plsql" in sku["errors"][0]
    others = [
        r["proposal"]["check"]["ok"]
        for r in saved["rules"]
        if r["id"] in ("no", "qty") and r["proposal"].get("check")
    ]
    assert all(others)  # only the rule that cannot be built is blamed
    # the same rule builds for Python
    (project / "mapper.toml").write_text(
        config.replace('target = "plsql"', 'target = "python"') + "\n[target.python]\n"
    )
    assert import_plan.assemble(project, "m")["ok"] is True
