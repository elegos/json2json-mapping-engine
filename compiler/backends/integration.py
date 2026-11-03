"""What every backend's integration tests (track 2) share: the golden cases, their results, and
the context a backend is handed to run them (docs/ARCHITECTURE.md, §Testing).

How a case is *run* is the backend's business (an Oracle container for PL/SQL, the interpreter
itself for Python); how it is found and judged is not.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# the files of a case, by name: `<case>.input.json` (the case exists when it is there),
# `<case>.expected.json`, `<case>.expected_errors.json` (the rules that fail), and for a mapping that
# validates `<case>.expected_rejected.json` (the codes of the checks that reject; the case then has
# no output) and `<case>.expected_warnings.json` (the codes of the checks that only warn)
INPUT_SUFFIX = ".input.json"
EXPECTED_SUFFIX = ".expected.json"
ERRORS_SUFFIX = ".expected_errors.json"
REJECTED_SUFFIX = ".expected_rejected.json"
WARNINGS_SUFFIX = ".expected_warnings.json"
GOLDEN_DIR = Path("tests/golden")


class IntegrationError(Exception):
    """The integration tests cannot run, or the environment failed (not a test failure)."""


@dataclass
class TestCase:
    __test__ = False  # not a pytest test class

    mapping: str
    name: str
    input_path: Path
    expected_path: Path | None
    expected_errors: list[str] | None = None
    expected_rejected: list[str] | None = None
    expected_warnings: list[str] | None = None


@dataclass
class CaseResult:
    case: TestCase
    passed: bool | None  # None = no expected file, output shown for inspection
    output: Any = None
    rule_errors: list[dict[str, Any]] = field(default_factory=list)
    diff: str = ""
    message: str = ""
    warnings: list[str] = field(default_factory=list)  # `allowed` violations
    # the failed checks of a mapping that validates: [{"side", "code", "message", "action"}]; None
    # for a mapping that does not
    report: list[dict[str, Any]] | None = None


@dataclass
class IntegrationContext:
    """What a backend needs to run the cases of a project."""

    cases: list[TestCase]
    files: dict[str, str]  # the compiled artifact files, in the order the target needs them
    mapping_ids: dict[str, str]  # case.mapping (the file stem) -> the mapping's id
    log: Callable[[str], None] = print


def discover_cases(golden_dir: Path = GOLDEN_DIR, mapping: str | None = None) -> list[TestCase]:
    if not golden_dir.is_dir():
        return []
    cases: list[TestCase] = []
    for mdir in sorted(p for p in golden_dir.iterdir() if p.is_dir()):
        if mapping is not None and mdir.name != mapping:
            continue
        for inp in sorted(mdir.glob(f"*{INPUT_SUFFIX}")):
            name = inp.name.removesuffix(INPUT_SUFFIX)
            expected = mdir / f"{name}{EXPECTED_SUFFIX}"
            errors = mdir / f"{name}{ERRORS_SUFFIX}"
            rejected = mdir / f"{name}{REJECTED_SUFFIX}"
            warned = mdir / f"{name}{WARNINGS_SUFFIX}"
            cases.append(
                TestCase(
                    mdir.name,
                    name,
                    inp,
                    expected if expected.is_file() else None,
                    json.loads(errors.read_text()) if errors.is_file() else None,
                    json.loads(rejected.read_text()) if rejected.is_file() else None,
                    json.loads(warned.read_text()) if warned.is_file() else None,
                )
            )
    return cases


def json_diff(expected: Any, actual: Any) -> str:
    """Unified diff of canonical (key-sorted) JSON; empty string = equal."""

    def dump(v: Any) -> list[str]:
        return json.dumps(v, indent=2, sort_keys=True, ensure_ascii=False).splitlines()

    return "\n".join(
        difflib.unified_diff(dump(expected), dump(actual), "expected", "actual", lineterm="")
    )


def judge(
    case: TestCase,
    actual: Any,
    rule_errors: list[dict[str, Any]],
    twin: str = "",
    report: list[dict[str, Any]] | None = None,
) -> CaseResult:
    """The verdict on one case: the output against the expected file, the rule errors reported
    against the expected ones, and for a mapping that validates the checks that rejected or warned
    against the expected codes. `twin` is a problem the backend found elsewhere (the raising
    entry point disagreeing with the safe one): it fails the case whatever else holds."""
    warnings: list[str] = []
    rejected = sorted(i["code"] for i in report or [] if i["action"] == "reject")
    warned = sorted(i["code"] for i in report or [] if i["action"] == "warn")

    def result(passed: bool | None, diff: str = "", message: str = "") -> CaseResult:
        return CaseResult(case, passed, actual, rule_errors, diff, message, warnings, report)

    if case.expected_rejected is not None or rejected:
        # the verdict is about the checks: a rejected case has no output to compare
        want = sorted(case.expected_rejected or [])
        if rejected != want:
            if case.expected_path is None and case.expected_rejected is None:
                return result(None, message=twin or f"rejected by {rejected}")
            return result(False, message=twin or f"rejected by {rejected}, expected {want}")
        if case.expected_warnings is not None and warned != sorted(case.expected_warnings):
            return result(
                False, message=f"warnings {warned}, expected {sorted(case.expected_warnings)}"
            )
        if twin:
            return result(False, message=twin)
        return result(True)
    if case.expected_warnings is not None and warned != sorted(case.expected_warnings):
        return result(
            False,
            message=twin or f"warnings {warned}, expected {sorted(case.expected_warnings)}",
        )
    if case.expected_path is None:
        return result(False if twin else None, message=twin)
    expected = json.loads(case.expected_path.read_text())
    diff = json_diff(expected, actual)
    if case.expected_errors is None:
        errors_ok, errors_msg = not rule_errors, "rule errors reported"
    else:
        reported = sorted(e["rule"] for e in rule_errors)
        errors_ok = reported == sorted(case.expected_errors)
        errors_msg = f"rule errors {reported}, expected {sorted(case.expected_errors)}"
    ok = not diff and errors_ok and not twin
    msg = twin or (errors_msg if not errors_ok and not diff else "")
    return result(ok, diff, msg)
