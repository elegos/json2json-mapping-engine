"""Integration tests (track 2) — target-environment tests (see docs/ARCHITECTURE.md, §Testing).

This is the part every target shares: it finds the golden cases, hands them with the compiled
artifact to the project's backend (`Backend.run_integration`: an Oracle container for PL/SQL,
see `compiler/backends/plsql/integration.py`), and adds the `allowed` warnings to the results.

Case layout (per mapping, by basename of `mappings/<name>.map.py`):

    tests/golden/<name>/<case>.input.json      required
    tests/golden/<name>/<case>.expected.json   optional — omitted = display only
    tests/golden/<name>/<case>.expected_errors.json
                                               optional — the rule ids `_safe` must report
                                               (a JSON list); without it any rule error fails
    tests/golden/<name>/<case>.expected_rejected.json
                                               optional — a mapping that validates: the codes of the
                                               checks that reject the case (it then has no output)
    tests/golden/<name>/<case>.expected_warnings.json
                                               optional — the codes of the checks that only warn
"""

from __future__ import annotations

from pathlib import Path

from cli.allowed import check_allowed, collect_constraints, unsupported_keywords
from cli.build import (
    BuildError,
    backend_for,
    compiled_files,
    find_source,
    is_functional,
    mapping_id_of,
)
from cli.config import MapperConfig
from compiler.backends.integration import (
    GOLDEN_DIR,
    CaseResult,
    IntegrationContext,
    IntegrationError,
    TestCase,
    discover_cases,
    json_diff,
)
from transpiler.model import load_functional_file

Track2Error = IntegrationError

__all__ = [
    "GOLDEN_DIR",
    "CaseResult",
    "Track2Error",
    "TestCase",
    "discover_cases",
    "integration_state",
    "json_diff",
    "run_track2",
]


def integration_state(config: MapperConfig) -> str | None:
    """None when the project's target can run its integration tests here; else why not (the
    target has none, or its environment is missing)."""
    try:
        backend = backend_for(config)
    except BuildError as exc:
        return str(exc)
    if not backend.has_integration:
        return f"the {config.project.target} target has no integration tests"
    return backend.integration_unavailable()


def run_track2(config: MapperConfig, mapping: str | None = None, log=print) -> list[CaseResult]:
    """Run all cases. Raises `IntegrationError` if the environment is unusable."""
    cases = discover_cases(mapping=mapping)
    if not cases:
        return []
    try:
        backend = backend_for(config)
        files = compiled_files(config)
    except BuildError as exc:
        raise IntegrationError(str(exc)) from exc
    if not backend.has_integration:
        raise IntegrationError(f"the {config.project.target} target has no integration tests")

    sources: dict[str, Path | None] = {c.mapping: find_source(c.mapping, config) for c in cases}
    ids = {m: mapping_id_of(p) if p else m for m, p in sources.items()}
    results = backend.run_integration(IntegrationContext(cases, files, ids, log))

    constraints = {
        m: collect_constraints(load_functional_file(p)) if p and is_functional(p) else None
        for m, p in sources.items()
    }
    for r in results:
        found = constraints.get(r.case.mapping)
        if found and r.output is not None:
            r.warnings = [*unsupported_keywords(found), *check_allowed(r.output, found)]
    return results
