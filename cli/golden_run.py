"""Running the golden cases of a mapping from the desktop tool (ops `golden_run` and
`golden_record` of `mapper serve`). The cases run on the Python backend whatever the project's
target is: it needs no database, and the results are backend-independent by design (the cases
are the contract every backend runs). The mapping is compiled afresh, so what is run is what is
in the file now."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from cli.build import (
    BuildError,
    _compile_fresh,
    find_source,
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
from transpiler.model import FnYamlError


def _result_json(result: CaseResult) -> dict[str, Any]:
    case = result.case
    return {
        "name": case.name,
        # None: the case has no expected output, the output is only shown
        "passed": result.passed,
        "output": result.output,
        "errors": result.rule_errors,
        "expected_errors": case.expected_errors,
        "diff": result.diff,
        "message": result.message,
    }


def _run(project: Path, mapping: str, names: list[str] | None) -> list[CaseResult]:
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
        return backend.run_integration(context)


def run_cases(project: Path, mapping: str, names: list[str] | None = None) -> list[dict[str, Any]]:
    """The results of the cases: pass / fail, the output, the rule errors and the diff."""
    return [_result_json(r) for r in _run(project, mapping, names)]


def record_case(project: Path, mapping: str, name: str) -> dict[str, Any]:
    """Makes what the mapping gives now the expected result of the case: the output as
    `<case>.expected.json`, and the rules that failed as `<case>.expected_errors.json` (the file
    goes when none failed). The caller shows the output first; this overwrites."""
    project = project.resolve()
    (result,) = _run(project, mapping, [name])
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
