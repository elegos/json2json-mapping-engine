"""The Python backend: every mapping is a module `map_<id>.py` with `map_<id>(source)` (raises
`MappingError` when rules failed) and `map_<id>_safe(source)` (gives `(output, rule errors)`),
next to the shared `j2jme_runtime.py`. `source` is the JSON text or the parsed document."""

from __future__ import annotations

import ast
import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any, ClassVar

from compiler.backends.base import Backend, CodeGenError, CompiledUnit, Option
from compiler.backends.integration import CaseResult, IntegrationContext, judge
from compiler.backends.python import codegen, runtime
from compiler.function_registry import project_functions
from compiler.scope_resolver import ScopeResolution

RUNTIME_FILE = "j2jme_runtime.py"
DEFAULT_MAX_PARALLEL = 4
MIN_PYTHON = runtime.MIN_PYTHON  # the first Python that runs what the backend generates

# the Oracle date format tokens `parse_date` is written with, as `strptime` has them
_STRPTIME = {"YYYY": "%Y", "MM": "%m", "DD": "%d", "HH24": "%H", "MI": "%M", "SS": "%S"}

_PARSE_DATE = f'''
def parse_date(s, fmt):
    """The date written in `s` with format `fmt` (YYYY, MM, DD, HH24, MI, SS), as text."""
    from datetime import datetime

    for token, directive in {_STRPTIME!r}.items():
        fmt = fmt.replace(token, directive)
    return datetime.strptime(s, fmt).date().isoformat()
'''


def runtime_text(max_parallel: int = DEFAULT_MAX_PARALLEL) -> str:
    """The support module: the run-time rules, then the built-in functions (their reference
    implementations, `compiler/builtins.py`), with `parse_date` given the format dialect and the
    most workers loops may use in all (`max_parallel`)."""
    core = (
        Path(runtime.__file__)
        .read_text()
        .replace("MAX_PARALLEL = 4\n", f"MAX_PARALLEL = {int(max_parallel)}\n", 1)
    )
    builtins_source = (Path(runtime.__file__).parents[2] / "builtins.py").read_text()
    tree = ast.parse(builtins_source)
    kept = [
        n
        for n in tree.body
        if not (
            isinstance(n, ast.ImportFrom)
            and n.module in ("__future__", "compiler.function_registry")
        )
    ]
    for node in kept:  # `@special` only labels a function for the engine
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = [
                d
                for d in node.decorator_list
                if not (isinstance(d, ast.Name) and d.id == "special")
            ]
    builtins_text = ast.unparse(ast.Module(body=kept, type_ignores=[]))
    return (
        core
        + "\n\n# -- the built-in functions "
        + "-" * 40
        + "\n"
        + builtins_text
        + "\n"
        + _PARSE_DATE
        + "\n\n__all__ = [n for n in dir() if not n.startswith('__') and n != 'annotations']\n"
    )


class PythonBackend(Backend):
    target: ClassVar[str] = "python"
    artifact_suffix: ClassVar[str] = ".py"
    defaults: ClassVar[dict[str, Any]] = {
        "parallel": "thread",
        "max_parallel": DEFAULT_MAX_PARALLEL,
    }
    options: ClassVar[tuple[Option, ...]] = (
        Option(
            "parallel",
            "choice",
            "How a loop whose rule is `@parallel(degree=N)` runs: `thread` maps its elements in up "
            "to N threads (a speed-up only when the program runs on a free-threaded Python, such as "
            "3.14t; with the GIL it is correct but not faster), `process` maps them in up to N worker processes (a "
            "speed-up whatever the Python; the elements and what the rule gives travel between "
            "processes, so it pays off for heavy rules; the program that calls the mapping must "
            'guard its entry point with `if __name__ == "__main__":`), `none` runs it in order',
            default="thread",
            choices=("thread", "process", "none"),
        ),
        Option(
            "max_parallel",
            "int",
            "The most workers (threads or processes) the loops of a mapping may use at once, in all, "
            "however they nest: a loop takes what is free of the degree it declares, and a loop "
            "inside a worker process runs in order. 1 turns `@parallel` off; it must be 1 or more",
            default=DEFAULT_MAX_PARALLEL,
            minimum=1,
        ),
    )
    has_integration: ClassVar[bool] = True

    @property
    def max_parallel(self) -> int:
        return int(self.config.get("max_parallel", DEFAULT_MAX_PARALLEL))

    def compile_module(
        self, tree: ast.Module, mapping_id: str, scope_resolution: ScopeResolution | None = None
    ) -> codegen.PythonUnit:
        # the project is the working directory (a build and a golden run both start there)
        return codegen.compile_module(
            tree,
            mapping_id,
            project_functions(Path.cwd()),
            "none" if self.max_parallel < 2 else self.config.get("parallel", "thread"),
        )

    def unit_from_json(self, data: dict[str, Any]) -> codegen.PythonUnit:
        return codegen.PythonUnit.from_json(data)

    def assemble(self, units: list[CompiledUnit]) -> dict[str, str]:
        ids: set[str] = set()
        files: dict[str, str] = {RUNTIME_FILE: runtime_text(self.max_parallel)}
        for unit in units:
            if not isinstance(unit, codegen.PythonUnit):
                raise CodeGenError("the python backend can only assemble PythonUnit objects")
            if unit.mapping_id in ids:
                raise CodeGenError(f"two mappings have the id {unit.mapping_id!r}")
            ids.add(unit.mapping_id)
            files[f"map_{unit.mapping_id}.py"] = unit.source
        return files

    def deploy_order(self, file_names: list[str]) -> list[str]:
        return sorted(file_names, key=lambda n: (n != RUNTIME_FILE, n))

    # -- the golden cases: run in this interpreter, no container ------------------------
    def integration_unavailable(self) -> str | None:
        return None

    def run_integration(self, context: IntegrationContext) -> list[CaseResult]:
        import json

        results: list[CaseResult] = []
        with tempfile.TemporaryDirectory(prefix="j2jme-python-") as folder:
            for name, text in context.files.items():
                (Path(folder) / name).write_text(text)
            modules = _load_modules(Path(folder), set(context.mapping_ids.values()))
            for case in context.cases:
                mapping_id = context.mapping_ids.get(case.mapping)
                module = modules.get(mapping_id or "")
                if module is None:
                    results.append(
                        CaseResult(case, False, message=f"no compiled mapping for {case.mapping!r}")
                    )
                    continue
                source = json.loads(case.input_path.read_text())
                output, errors = getattr(module, f"map_{mapping_id}_safe")(source)
                twin = _twin_problem(module, mapping_id or "", source, output, errors)
                results.append(judge(case, output, errors, twin))
                context.log(
                    f"{case.mapping}/{case.name}: {'ok' if results[-1].passed else 'FAILED'}"
                )
        return results


def _load_modules(folder: Path, mapping_ids: set[str]) -> dict[str, Any]:
    """Imports the runtime and the mapping modules written in `folder`, apart from any other
    copy of them already in this process."""
    for stale in [m for m in sys.modules if m == "j2jme_runtime" or m.startswith("map_")]:
        del sys.modules[stale]
    sys.path.insert(0, str(folder))
    try:
        found: dict[str, Any] = {}
        for mapping_id in sorted(mapping_ids):
            path = folder / f"map_{mapping_id}.py"
            spec = importlib.util.spec_from_file_location(f"map_{mapping_id}", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            found[mapping_id] = module
        return found
    finally:
        sys.path.remove(str(folder))


def _twin_problem(module: Any, mapping_id: str, source: Any, output: Any, errors: list) -> str:
    """The raising entry point must agree with the safe one: raise exactly when there are errors,
    and give the same output when there are none."""
    raising = getattr(module, f"map_{mapping_id}")
    try:
        plain = raising(source)
    except Exception as exc:  # noqa: BLE001
        if errors and type(exc).__name__ == "MappingError":
            return ""
        return f"map_{mapping_id} raised {type(exc).__name__} but map_{mapping_id}_safe reported no error"
    if errors:
        return f"map_{mapping_id} did not raise although map_{mapping_id}_safe reported {len(errors)} error(s)"
    return (
        ""
        if plain == output
        else f"map_{mapping_id} and map_{mapping_id}_safe gave different outputs"
    )
