"""Validation of the input and the output (compiler/validation.py): the extra checks and the JSON
Schema check, a `reject` that gives no output, a `warn` that only reports, and what the two entry
points do about them. The golden mapping `validation` holds the cases every backend runs."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from compiler.backends.base import CodeGenError
from compiler.backends.integration import TestCase, judge
from compiler.backends.python.backend import PythonBackend
from compiler.backends.python.codegen import PythonUnit
from compiler.pipeline import compile_unit
from compiler.validation import ValidationError, parse

SCHEMA = json.dumps(
    {
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "string"}, "n": {"type": "integer"}},
    }
)


def _directive(**sides: Any) -> str:
    return f"__validation__ = {json.dumps(json.dumps(sides))}\n"


def _source(directive: str, extra: str = "") -> str:
    return (
        "from __mapping__ import *\n"
        + directive
        + "def ok_n(root: Any) -> bool:\n    return root.n > 0\n"
        + "def has_id(root: Any) -> bool:\n    return root.id\n"
        + extra
        + "def the_id(root: Any) -> str:\n    return root.id\n"
        + "out.id = the_id(root)\n"
    )


def _load(tmp_path: Path, source: str, **kwargs: Any) -> Any:
    backend = PythonBackend({})
    unit = compile_unit(source, "m", backend, **kwargs)
    for name, text in backend.assemble([unit]).items():
        (tmp_path / name).write_text(text)
    for stale in [m for m in sys.modules if m == "j2jme_runtime" or m.startswith("map_")]:
        del sys.modules[stale]
    sys.path.insert(0, str(tmp_path))
    try:
        spec = importlib.util.spec_from_file_location("map_m", tmp_path / "map_m.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(tmp_path))


CHECKS = _directive(
    input={
        "schema": True,
        "checks": [{"fn": "ok_n", "code": "N_POSITIVE", "message": "n > 0", "action": "reject"}],
    },
    output={
        "checks": [{"fn": "has_id", "code": "NO_ID", "message": "id", "action": "warn"}],
    },
)


def test_a_mapping_without_validation_keeps_its_two_part_result(tmp_path: Path) -> None:
    module = _load(tmp_path, _source(""))
    assert module.map_m_safe({"id": "a", "n": -1}) == ({"id": "a"}, [])


def test_a_mapping_that_validates_reports_the_failed_checks_as_a_third_part(
    tmp_path: Path,
) -> None:
    module = _load(tmp_path, _source(CHECKS), schema_texts={"input": SCHEMA})
    assert module.map_m_safe({"id": "a", "n": 3}) == ({"id": "a"}, [], [])
    output, errors, report = module.map_m_safe({"id": "a", "n": -3})
    assert (output, errors) == (None, [])
    assert report == [
        {"side": "input", "code": "N_POSITIVE", "message": "n > 0", "action": "reject"}
    ]


def test_a_rejected_input_runs_no_rule_and_the_raising_entry_point_says_why(
    tmp_path: Path,
) -> None:
    module = _load(tmp_path, _source(CHECKS), schema_texts={"input": SCHEMA})
    with pytest.raises(Exception, match="rejected") as raised:
        module.map_m({"id": "a", "n": 0})
    assert type(raised.value).__name__ == "MappingRejected"
    report = raised.value.report  # pyright: ignore[reportAttributeAccessIssue]
    assert [c["code"] for c in report] == ["N_POSITIVE"]
    assert module.map_m({"id": "a", "n": 1}) == {"id": "a"}


def test_the_json_schema_check_rejects_and_the_checks_that_cannot_run_are_not_reported(
    tmp_path: Path,
) -> None:
    module = _load(tmp_path, _source(CHECKS), schema_texts={"input": SCHEMA})
    _, _, report = module.map_m_safe({"n": "many"})
    assert [i["code"] for i in report] == ["SCHEMA_INPUT"]  # `n > 0` on a text: not evaluable
    assert report[0]["message"].startswith("does not match the JSON Schema")
    assert "'many' is not of type 'integer'" in report[0]["message"]


def test_a_check_that_cannot_run_on_a_document_the_schema_accepts_fails(tmp_path: Path) -> None:
    source = _source(
        _directive(input={"checks": [{"fn": "ok_n", "code": "N", "action": "reject"}]})
    )
    module = _load(tmp_path, source)
    _, _, report = module.map_m_safe({"id": "a", "n": "many"})
    assert [i["code"] for i in report] == ["N"]
    assert "could not be evaluated" in report[0]["message"]


def test_only_a_true_condition_passes_a_check(tmp_path: Path) -> None:
    """A comparison with a missing value is not true, so the condition says what a missing value
    means (`not $.n or $.n > 0`): the same on every backend."""
    module = _load(tmp_path, _source(CHECKS), schema_texts={"input": SCHEMA})
    assert [i["code"] for i in module.map_m_safe({"id": "a"})[2]] == ["N_POSITIVE"]
    source = _source(
        _directive(input={"checks": [{"fn": "optional_n", "code": "N", "action": "reject"}]}),
        "def optional_n(root: Any) -> bool:\n    return not root.n or root.n > 0\n",
    )
    assert _load(tmp_path, source).map_m_safe({"id": "a"}) == ({"id": "a"}, [], [])


def test_a_warning_does_not_stop_the_mapping(tmp_path: Path) -> None:
    source = _source(_directive(input={"checks": [{"fn": "ok_n", "code": "N", "action": "warn"}]}))
    module = _load(tmp_path, source)
    output, _, report = module.map_m_safe({"id": "a", "n": -1})
    assert output == {"id": "a"} and report[0]["action"] == "warn"
    assert module.map_m({"id": "a", "n": -1}) == {"id": "a"}


def test_an_output_check_that_rejects_gives_no_output(tmp_path: Path) -> None:
    source = _source(
        _directive(output={"checks": [{"fn": "ok_n", "code": "OUT_N", "action": "reject"}]}),
        "def the_n(root: Any) -> int:\n    return root.n\nout.n = the_n(root)\n",
    )
    module = _load(tmp_path, source)
    assert module.map_m_safe({"id": "a", "n": 1}) == ({"id": "a", "n": 1}, [], [])
    output, _, report = module.map_m_safe({"id": "a", "n": -1})
    assert output is None and [(i["side"], i["code"]) for i in report] == [("output", "OUT_N")]
    with pytest.raises(Exception, match="rejected"):
        module.map_m({"id": "a", "n": -1})


def test_the_json_schema_check_needs_the_schema() -> None:
    with pytest.raises(CodeGenError, match="no input schema"):
        compile_unit(_source(CHECKS), "m", PythonBackend({}))


def test_the_schema_is_embedded_in_canonical_form(tmp_path: Path) -> None:
    source = _source(CHECKS)
    backend = PythonBackend({})
    unit = compile_unit(source, "m", backend, schema_texts={"input": SCHEMA})
    assert isinstance(unit, PythonUnit)
    assert json.dumps(json.loads(SCHEMA), sort_keys=True, separators=(",", ":")) in unit.source


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[]", "must be an object"),
        ('{"middle": {}}', "must be an object"),
        ('{"input": {"checks": [{"fn": "f"}]}}', "needs a code"),
        ('{"input": {"checks": [{"fn": "f", "code": "A", "action": "stop"}]}}', "reject' or 'warn"),
        (
            '{"input": {"checks": [{"fn": "f", "code": "A"}, {"fn": "g", "code": "A"}]}}',
            "used twice",
        ),
    ],
)
def test_a_malformed_directive_is_refused(text: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse(text)


def test_a_check_must_name_a_function_of_the_module() -> None:
    source = (
        "from __mapping__ import *\n"
        + _directive(input={"checks": [{"fn": "ghost", "code": "A"}]})
        + "def the_id(root: Any) -> str:\n    return root.id\nout.id = the_id(root)\n"
    )
    with pytest.raises(CodeGenError, match="no function 'ghost'"):
        compile_unit(source, "m", PythonBackend({}))


def _case(**more: Any) -> TestCase:
    return TestCase("m", "c", Path("i.json"), None, **more)


def test_a_case_expects_the_codes_that_reject_it() -> None:
    report = [
        {"side": "input", "code": "B", "message": "", "action": "reject"},
        {"side": "input", "code": "A", "message": "", "action": "reject"},
        {"side": "input", "code": "W", "message": "", "action": "warn"},
    ]
    assert judge(_case(expected_rejected=["A", "B"]), None, [], "", report).passed is True
    wrong = judge(_case(expected_rejected=["A"]), None, [], "", report)
    assert wrong.passed is False and "rejected by ['A', 'B'], expected ['A']" in wrong.message
    unexpected = judge(_case(), None, [], "", report)
    assert unexpected.passed is None  # no expectation: shown for inspection
    assert judge(
        _case(expected_rejected=["A", "B"], expected_warnings=["W"]), None, [], "", report
    ).passed
    assert not judge(
        _case(expected_rejected=["A", "B"], expected_warnings=[]), None, [], "", report
    ).passed


def test_is_digits_is_true_for_digits_only_and_null_for_nothing(tmp_path: Path) -> None:
    source = (
        "from __mapping__ import *\n"
        "def d(root: Any) -> bool | None:\n    return is_digits(root.v)\n"
        "out.d = d(root)\n"
    )
    module = _load(tmp_path, source)
    assert module.map_m_safe({"v": "01234567890"})[0] == {"d": True}
    assert module.map_m_safe({"v": "0123a"})[0] == {"d": False}
    assert module.map_m_safe({"v": "12 3"})[0] == {"d": False}
    assert module.map_m_safe({"v": "١٢٣"})[0] == {"d": False}  # Arabic-Indic digits are not 0-9
    assert module.map_m_safe({"v": ""})[0] == {}  # an empty text is null
    assert module.map_m_safe({})[0] == {}


def _plsql(source: str, **kwargs: Any) -> str:
    from compiler.backends.plsql.backend import PlsqlBackend

    backend = PlsqlBackend({"schema": "S", "error_code": -20000, "mapping_package_prefix": "M_"})
    unit = compile_unit(source, "m", backend, **kwargs)
    return "\n".join(backend.assemble([unit]).values())


def test_the_plsql_entry_points_carry_the_report_only_when_the_mapping_validates() -> None:
    plain = _plsql(_source(""))
    assert "p_report" not in plain and "DBMS_JSON_SCHEMA" not in plain
    text = _plsql(_source(CHECKS), schema_texts={"input": SCHEMA})
    assert "p_err OUT CLOB,\n        p_report OUT CLOB" in text
    assert "DBMS_JSON_SCHEMA.IS_VALID(JSON(v_doc), JSON(v_schema))" in text
    assert "FUNCTION fn_m_validation_schema_input RETURN CLOB" in text
    assert "FUNCTION fn_m_validation_schema_output" not in text  # only the sides that ask
    assert "add_failed('input', 'N_POSITIVE', 'n > 0', 'reject')" in text
    assert "add_failed('output', 'NO_ID', 'id', 'warn')" in text
    assert "v_payload.put('rejected', TRUE)" in text
    safe = text[text.index("PROCEDURE map_m_safe (", text.index("PROCEDURE map_m_safe (") + 1) :]
    assert safe.index("IF NOT v_rejected THEN") < safe.index("fn_m_the_id(v_srcroot")
    raising = text[text.index("PROCEDURE map_m (", text.index("PROCEDURE map_m (") + 1) :]
    assert raising.index("IF v_rejected THEN") < raising.index("fn_m_the_id(v_srcroot")


def test_a_long_schema_is_embedded_in_pieces_a_literal_can_hold() -> None:
    big = json.dumps(
        {"type": "object", "properties": {f"f{i}": {"type": "string"} for i in range(400)}}
    )
    text = _plsql(_source(CHECKS), schema_texts={"input": big})
    function = text[text.index("FUNCTION fn_m_validation_schema_input RETURN CLOB IS") :]
    function = function[: function.index("END fn_m_validation_schema_input")]
    assert function.count("TO_CLOB('") > 1 and all(
        len(line) < 1600 for line in function.splitlines()
    )
