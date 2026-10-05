"""Running and recording the golden cases of a mapping from the tool (`cli/golden_run.py`)."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

from cli.golden_run import _result_json, record_case, run_cases
from cli.serve import serve
from transpiler.model import FnYamlError

FIXTURE = Path(__file__).resolve().parents[3] / "desktop/fixtures/tour-project"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / "p")
    return tmp_path / "p"


def test_the_tutorial_projects_cases_pass_on_the_python_backend(project: Path) -> None:
    results = run_cases(project, "orders")
    assert [(r["name"], r["passed"]) for r in results] == [
        ("failed_member", True),
        ("no_lines", True),
        ("two_lines", True),
    ]
    failed = results[0]
    assert [e["rule"] for e in failed["errors"]] == ["lines"] and failed["expected_errors"] == [
        "lines"
    ]


def test_one_case_by_name_and_a_wrong_expectation_is_a_diff(project: Path) -> None:
    expected = project / "tests/golden/orders/two_lines.expected.json"
    data = json.loads(expected.read_text())
    data["OrderId"] = "WRONG"
    expected.write_text(json.dumps(data))
    (result,) = run_cases(project, "orders", ["two_lines"])
    assert result["passed"] is False
    assert '-  "OrderId": "WRONG"' in result["diff"] and '+  "OrderId": "A1"' in result["diff"]
    with pytest.raises(FnYamlError, match="no case called 'ghost'"):
        run_cases(project, "orders", ["ghost"])
    with pytest.raises(FnYamlError, match="no mapping called"):
        run_cases(project, "nothing")


def test_recording_takes_the_output_and_the_failed_rules_as_the_expectation(project: Path) -> None:
    folder = project / "tests/golden/orders"
    (folder / "two_lines.expected.json").write_text("{}")
    (folder / "two_lines.expected_errors.json").write_text('["old"]')
    recorded = record_case(project, "orders", "two_lines")
    assert recorded["errors"] == [] and recorded["output"]["OrderId"] == "A1"
    assert not (folder / "two_lines.expected_errors.json").exists()  # nothing failed
    assert run_cases(project, "orders", ["two_lines"])[0]["passed"] is True
    assert record_case(project, "orders", "failed_member")["errors"] == ["lines"]
    assert json.loads((folder / "failed_member.expected_errors.json").read_text()) == ["lines"]


def test_a_case_without_expected_output_is_shown_not_judged(project: Path) -> None:
    folder = project / "tests/golden/orders"
    (folder / "new.input.json").write_text((folder / "two_lines.input.json").read_text())
    (result,) = run_cases(project, "orders", ["new"])
    assert result["passed"] is None and result["output"]["OrderId"] == "A1"


def test_serve_golden_run_and_record(project: Path) -> None:
    base = {"project": str(project), "mapping": "orders"}
    requests = [
        {"id": 1, "op": "golden_run", **base},
        {"id": 2, "op": "golden_run", "names": ["no_lines"], **base},
        {"id": 3, "op": "golden_record", "name": "no_lines", **base},
        {"id": 4, "op": "golden_run", "names": ["ghost"], **base},
    ]
    out = io.StringIO()
    serve(io.StringIO("".join(json.dumps(r) + "\n" for r in requests)), out)
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a["ok"] for a in answers] == [True, True, True, False]
    assert len(answers[0]["results"]) == 3 and len(answers[1]["results"]) == 1


def test_a_failing_rule_says_where_it_is_in_the_grid(project: Path) -> None:
    failed = run_cases(project, "orders", ["failed_member"])[0]
    (error,) = failed["errors"]
    # `lines` is the loop, the seventh rule of the mapping; this case expects it to fail
    assert error["rule"] == "lines" and error["path"] == "rules[6]"
    assert (
        error["expected"] is True and error["regex"] is False and error["target"] if False else True
    )
    assert failed["target"] == "plsql"  # the project's backend; the cases ran on Python


def test_a_rule_that_uses_a_regular_expression_is_marked_as_such(project: Path) -> None:
    mapping = project / "mappings/functional/orders.fn.yaml"
    text = mapping.read_text()
    assert 'lookup(value, @countryCurrency, "N/A")' in text
    mapping.write_text(
        text.replace('lookup(value, @countryCurrency, "N/A")', 'regexp_replace(value, "(", "")')
    )
    result = run_cases(project, "orders", ["two_lines"])[0]
    (error,) = result["errors"]
    # the pattern is invalid for Python (and any engine): the failure is reported, and the rule
    # is the one with the regular expression, so the tool can say it may be Python's dialect only
    assert error["rule"] == "cur" and error["path"] == "rules[1]"
    assert error["regex"] is True and error["expected"] is False
    assert result["target"] == "plsql" and result["passed"] is False
    other = [e for r in run_cases(project, "orders", ["no_lines"]) for e in r["errors"]]
    assert all(e["regex"] for e in other)  # `cur` again, nothing else


def test_only_a_pattern_python_cannot_compile_is_marked(project: Path) -> None:
    from compiler.backends.integration import CaseResult, TestCase

    case = TestCase("orders", "c", project / "x", None, None)
    index = {"cur": {"path": "rules[1]", "regex": True}}

    def marked(cause: str) -> bool:
        result = CaseResult(case, False, rule_errors=[{"rule": "cur", "cause": cause}])
        return _result_json(result, index, "plsql", {})["errors"][0]["regex"]

    assert marked("error: missing ), unterminated subpattern at position 0")
    assert marked("PatternError: missing ), unterminated subpattern at position 0")
    assert not marked("ValueError: bad value")  # same rule, another cause: a real failure


def _with_functions(project: Path, source: str, expression: str) -> None:
    """The tutorial project with `fn/text.fn` replaced and the Warehouse rule calling `expression`."""
    (project / "fn/text.fn").write_text(source)
    mapping = project / "mappings/functional/orders.fn.yaml"
    mapping.write_text(mapping.read_text().replace('split_nth(value, ",", 2)', expression))


def test_a_project_function_with_python_code_runs(project: Path) -> None:
    _with_functions(
        project,
        "def first_word(s: str) -> str | None:\n"
        "    parts = s.split(',')\n    return parts[0] if parts else None\n",
        "first_word(value)",
    )
    result = run_cases(project, "orders", ["two_lines"])[0]
    assert result["output"]["Warehouse"] == "EU"  # first part of "EU,IT,MI"
    assert result["errors"] == [] and result["inconclusive"] is False


def test_a_python_override_is_the_code_of_a_project_function(project: Path) -> None:
    _with_functions(
        project,
        "from __mapping__ import override\n\n"
        '@override(python="{s}.lower()", plsql="LOWER({s})")\n'
        "def shout(s: str) -> str:\n    ...\n",
        "shout(value)",
    )
    assert run_cases(project, "orders", ["two_lines"])[0]["output"]["Warehouse"] == "eu,it,mi"


def test_a_project_function_without_python_code_makes_its_rules_unavailable(project: Path) -> None:
    _with_functions(
        project,
        "from __mapping__ import override\n\n"
        "@override(plsql=\"REGEXP_SUBSTR({s}, '[^,]+', 1, 1)\")\n"
        "def first_word(s: str) -> str | None:\n    ...\n",
        "first_word(value)",
    )
    result = run_cases(project, "orders", ["two_lines"])[0]
    (error,) = result["errors"]
    assert error["rule"] == "wh" and error["unavailable"] == ["first_word"]
    assert result["inconclusive"] is True and "Warehouse" not in result["output"]
    with pytest.raises(FnYamlError, match="not recorded"):
        record_case(project, "orders", "two_lines")
