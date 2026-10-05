"""Running the golden cases of a mapping from the desktop tool (ops `golden_run` and
`golden_record` of `mapper serve`). The cases run on the Python backend whatever the project's
target is: it needs no database, and the results are backend-independent by design (the cases
are the contract every backend runs). The mapping is compiled afresh, so what is run is what is
in the file now."""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path
from typing import Any

from cli.build import (
    BuildError,
    _compile_fresh,
    find_source,
    is_functional,
    mapping_id_of,
)
from cli.config import load_config
from cli.golden import _folder
from compiler.backends.base import CodeGenError
from compiler.backends.integration import (
    ERRORS_SUFFIX,
    EXPECTED_SUFFIX,
    GOLDEN_DIR,
    CaseResult,
    IntegrationContext,
    TestCase,
    discover_cases,
)
from compiler.backends.registry import create_backend
from transpiler.ids import walk
from transpiler.model import FnYamlError, load_functional_file
from transpiler.review import paths_by_id
from transpiler.serialize import rule_to_raw

_REGEX_CALL = re.compile(r"\bregexp_(replace|group)\s*\(")
# `re.error` is named `PatternError` from Python 3.13: the pattern does not compile
_PATTERN_ERROR = re.compile(r"^(error|PatternError):")


def rule_index(path: Path) -> dict[str, dict[str, Any]]:
    """For a `.fn.yaml`: the name a rule's function has in the generated code (its fully-qualified
    id with `.` as `_`, and `<name>_first` for a selection) -> where the rule is in the grid and
    whether it, or a rule inside it, uses a regular expression. Empty for a `.map.py`."""
    if not is_functional(path):
        return {}
    file = load_functional_file(path)
    paths = paths_by_id(file)
    rules = dict(walk(file.rules))
    index: dict[str, dict[str, Any]] = {}
    for fq, rule_path in paths.items():
        uses_regex = bool(_REGEX_CALL.search(json.dumps(rule_to_raw(rules[fq]), default=str)))
        entry = {"path": rule_path, "regex": uses_regex}
        ident = fq.replace(".", "_")
        index[ident] = index[f"{ident}_first"] = entry
    return index


def _result_json(
    result: CaseResult,
    index: dict[str, dict[str, Any]],
    target: str,
    unavailable: dict[str, list[str]],
) -> dict[str, Any]:
    case = result.case
    expected_errors = case.expected_errors or []
    errors = [
        {
            **e,
            # project functions this rule calls that have no code for Python: it did not run
            "unavailable": unavailable.get(e["rule"], []),
            "path": index.get(e["rule"], {}).get("path"),
            # a pattern is in the dialect of the project's backend, and the cases run on Python's:
            # one that Python cannot compile says nothing about the mapping
            "regex": index.get(e["rule"], {}).get("regex", False)
            and bool(_PATTERN_ERROR.match(e["cause"])),
            "expected": e["rule"] in expected_errors,
        }
        for e in result.rule_errors
    ]
    return {
        "name": case.name,
        # None: the case has no expected output, the output is only shown
        "passed": result.passed,
        "output": result.output,
        "errors": errors,
        "expected_errors": case.expected_errors,
        "target": target,
        # some rule could not run on Python: the verdict says nothing about the mapping
        "inconclusive": any(e["unavailable"] for e in errors),
        "diff": result.diff,
        "message": result.message,
    }


def _run(
    project: Path, mapping: str, names: list[str] | None
) -> tuple[list[CaseResult], dict[str, dict[str, Any]], str, dict[str, list[str]]]:
    """Compiles the mapping and runs the named cases (all of them without names)."""
    project = project.resolve()
    with contextlib.chdir(project):
        try:
            config = load_config()
            path = find_source(mapping, config)
            if path is None:
                raise FnYamlError(f"no mapping called {mapping!r} in the project")
            backend = create_backend("python", {})
            unit = _compile_fresh(path, config, [], backend)
            mapping_id = mapping_id_of(path)
            files = backend.assemble([unit])
            index = rule_index(path)
            target = config.project.target
            unavailable = getattr(unit, "unavailable", {})
        except (BuildError, CodeGenError) as exc:
            raise FnYamlError(str(exc)) from exc
        cases = [c for c in discover_cases(GOLDEN_DIR, mapping) if names is None or c.name in names]
        missing = sorted(set(names or []) - {c.name for c in cases})
        if missing:
            raise FnYamlError(f"the mapping has no case called {missing[0]!r}")
        context = IntegrationContext(
            cases=[
                TestCase(
                    c.mapping,
                    c.name,
                    project / c.input_path,
                    project / c.expected_path if c.expected_path else None,
                    c.expected_errors,
                )
                for c in cases
            ],
            files=files,
            mapping_ids={mapping: mapping_id},
            log=lambda _m: None,
        )
        return backend.run_integration(context), index, target, unavailable


def run_cases(project: Path, mapping: str, names: list[str] | None = None) -> list[dict[str, Any]]:
    """The results of the cases: pass / fail, the output, the rule errors and the diff."""
    results, index, target, unavailable = _run(project, mapping, names)
    return [_result_json(r, index, target, unavailable) for r in results]


def record_case(project: Path, mapping: str, name: str) -> dict[str, Any]:
    """Makes what the mapping gives now the expected result of the case: the output as
    `<case>.expected.json`, and the rules that failed as `<case>.expected_errors.json` (the file
    goes when none failed). The caller shows the output first; this overwrites."""
    project = project.resolve()
    (result,), _index, _target, unavailable = _run(project, mapping, [name])
    skipped = sorted({f for e in result.rule_errors for f in unavailable.get(e["rule"], [])})
    if skipped:
        raise FnYamlError(
            f"not recorded: rules did not run on Python (no Python code for {', '.join(skipped)}), "
            "so what they would give is missing from the output"
        )
    folder = _folder(project, mapping)
    (folder / f"{name}{EXPECTED_SUFFIX}").write_text(
        json.dumps(result.output, indent=2, ensure_ascii=False) + "\n"
    )
    errors_file = folder / f"{name}{ERRORS_SUFFIX}"
    failed = sorted(e["rule"] for e in result.rule_errors)
    if failed:
        errors_file.write_text(json.dumps(failed, indent=2) + "\n")
    else:
        errors_file.unlink(missing_ok=True)
    return {"output": result.output, "errors": failed}
