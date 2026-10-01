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


@dataclass
class CaseResult:
    case: TestCase
    passed: bool | None  # None = no expected file, output shown for inspection
    output: Any = None
    rule_errors: list[dict[str, Any]] = field(default_factory=list)
    diff: str = ""
    message: str = ""
    warnings: list[str] = field(default_factory=list)  # `allowed` violations


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
        for inp in sorted(mdir.glob("*.input.json")):
            name = inp.name.removesuffix(".input.json")
            expected = mdir / f"{name}.expected.json"
            errors = mdir / f"{name}.expected_errors.json"
            cases.append(
                TestCase(
                    mdir.name,
                    name,
                    inp,
                    expected if expected.is_file() else None,
                    json.loads(errors.read_text()) if errors.is_file() else None,
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
    case: TestCase, actual: Any, rule_errors: list[dict[str, Any]], twin: str = ""
) -> CaseResult:
    """The verdict on one case: the output against the expected file, the rule errors reported
    against the expected ones. `twin` is a problem the backend found elsewhere (the raising
    entry point disagreeing with the safe one): it fails the case whatever else holds."""
    warnings: list[str] = []
    if case.expected_path is None:
        if twin:
            return CaseResult(case, False, actual, rule_errors, message=twin, warnings=warnings)
        return CaseResult(case, None, actual, rule_errors, warnings=warnings)
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
    return CaseResult(case, ok, actual, rule_errors, diff, msg, warnings)
