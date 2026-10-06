"""The Python backend: the golden cases run on it, and the run-time rules one by one."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from compiler.backends.integration import IntegrationContext, discover_cases
from compiler.backends.python.backend import PythonBackend
from compiler.pipeline import compile_unit

ROOT = Path(__file__).resolve().parents[3]
# every mapping with golden cases: the shared contract the PL/SQL backend runs in track 2 (Oracle)
GOLDEN_MAPPINGS = sorted(
    d.name
    for d in (ROOT / "tests/golden").iterdir()
    if (ROOT / "mappings" / f"{d.name}.map.py").exists()
)


def _compile(source: str, mapping_id: str = "m") -> tuple[PythonBackend, Any]:
    backend = PythonBackend({})
    return backend, compile_unit(source, mapping_id, backend)


def _load(tmp_path: Path, source: str, mapping_id: str = "m") -> Any:
    """The compiled mapping as an imported module."""
    backend, unit = _compile(source, mapping_id)
    for name, text in backend.assemble([unit]).items():
        (tmp_path / name).write_text(text)
    for stale in [m for m in sys.modules if m == "j2jme_runtime" or m.startswith("map_")]:
        del sys.modules[stale]
    sys.path.insert(0, str(tmp_path))
    try:
        spec = importlib.util.spec_from_file_location(
            f"map_{mapping_id}", tmp_path / f"map_{mapping_id}.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(tmp_path))


def test_every_golden_case_passes_on_the_python_backend() -> None:
    backend = PythonBackend({})
    units = [
        compile_unit((ROOT / "mappings" / f"{name}.map.py").read_text(), name, backend)
        for name in GOLDEN_MAPPINGS
    ]
    context = IntegrationContext(
        cases=discover_cases(ROOT / "tests/golden"),
        files=backend.assemble(units),
        mapping_ids={name: name for name in GOLDEN_MAPPINGS},
        log=lambda _m: None,
    )
    results = backend.run_integration(context)
    assert len(results) == len(discover_cases(ROOT / "tests/golden")) >= 11
    assert "builtins_text" in GOLDEN_MAPPINGS
    failed = [
        f"{r.case.mapping}/{r.case.name}: {r.message}\n{r.diff}"
        for r in results
        if r.passed is not True
    ]
    assert not failed, "\n".join(failed)


def test_a_failing_rule_is_reported_once_and_the_rest_goes_on(tmp_path: Path) -> None:
    module = _load(
        tmp_path,
        "from __mapping__ import *\n"
        "def a(root: Any) -> int:\n    return root.x / root.y\n"
        "def b(root: Any) -> str:\n    return root.name\n"
        "out.A = a(root)\nout.B = b(root)\n"
        "for item in root.items:\n    out.C = a(item)\n",
    )
    out, errors = module.map_m_safe(
        {"x": 1, "y": 0, "name": "n", "items": [{"x": 1, "y": 0}, {"x": 2, "y": 0}]}
    )
    assert out == {"B": "n"}
    assert [e["rule"] for e in errors] == ["a"] and "ZeroDivisionError" in errors[0]["cause"]
    with pytest.raises(module.MappingError) as raised:
        module.map_m({"x": 1, "y": 0, "name": "n", "items": []})
    assert json.loads(str(raised.value))["total_errors"] == 1


def test_missing_values_are_null_and_arithmetic_and_ordering_propagate_it(tmp_path: Path) -> None:
    module = _load(
        tmp_path,
        "from __mapping__ import *\n"
        "def a(root: Any) -> int | None:\n    return root.a.b.c\n"
        "def b(root: Any) -> int | None:\n    return root.n + 1\n"
        "def c(root: Any) -> str:\n    return if_else(root.n > 3, 'big', 'small')\n"
        "out.A = a(root)\nout.B = b(root)\nout.C = c(root)\n",
    )
    out, errors = module.map_m_safe({})
    assert out == {"A": None, "B": None, "C": "small"} and errors == []


def test_bare_return_omits_and_return_null_puts_a_null(tmp_path: Path) -> None:
    module = _load(
        tmp_path,
        "from __mapping__ import *\n"
        "def omitted(root: Any) -> str | None:\n    return\n"
        "def nulled(root: Any) -> str | Null:\n    return Null\n"
        "out.Omitted = omitted(root)\nout.Nulled = nulled(root)\n",
    )
    assert module.map_m_safe({})[0] == {"Nulled": None}


def test_whole_numbers_are_written_as_integers(tmp_path: Path) -> None:
    module = _load(
        tmp_path,
        "from __mapping__ import *\n"
        "def half(root: Any) -> number:\n    return root.n / 2\n"
        "out.Half = half(root)\n",
    )
    out = module.map_m_safe({"n": 10})[0]
    assert json.dumps(out) == '{"Half": 5}'
    assert module.map_m_safe({"n": 5})[0] == {"Half": 2.5}


def test_the_artifacts_are_the_runtime_and_a_module_per_mapping() -> None:
    backend = PythonBackend({})
    _, unit = _compile("from __mapping__ import *\nout.A = 1\n", "x")
    files = backend.assemble([unit])
    assert list(files) == ["j2jme_runtime.py", "map_x.py"]
    assert backend.deploy_order(["map_x.py", "j2jme_runtime.py"])[0] == "j2jme_runtime.py"
    assert "import" not in files["map_x.py"].replace(
        "from j2jme_runtime import *", ""
    )  # nothing of the engine
    runtime = files["j2jme_runtime.py"]
    assert "import compiler" not in runtime and "from compiler" not in runtime


def test_the_builtins_run_with_their_reference_semantics(tmp_path: Path) -> None:
    module = _load(
        tmp_path,
        "from __mapping__ import *\n"
        "def d(root: Any) -> str:\n    return parse_date(root.d, 'DD/MM/YYYY')\n"
        "def total(root: Any) -> number:\n    return sum(root.rows, 'v')\n"
        "def top(root: Any) -> number:\n    return max(root.rows, 'v')\n"
        "def n(root: Any) -> int:\n    return count(root.rows)\n"
        "def r(root: Any) -> number:\n    return round(root.x, 1)\n"
        "def c(root: Any) -> str:\n    return concat(root.a, '-', root.missing)\n"
        "def k(root: Any) -> str:\n    return coalesce(root.missing, root.a)\n"
        "out.D = d(root)\nout.Total = total(root)\nout.Top = top(root)\nout.N = n(root)\n"
        "out.R = r(root)\nout.C = c(root)\nout.K = k(root)\n",
    )
    out, errors = module.map_m_safe(
        {"d": "03/10/2026", "rows": [{"v": 2}, {"v": 5}], "x": 2.25, "a": "A"}
    )
    assert errors == []
    assert out == {"D": "2026-10-03", "Total": 7, "Top": 5, "N": 2, "R": 2.3, "C": "A-", "K": "A"}


def test_the_text_and_timestamp_builtins_run_in_a_generated_module(tmp_path: Path) -> None:
    module = _load(
        tmp_path,
        "from __mapping__ import *\n"
        "def a(root: Any) -> str:\n    return replace(root.s, '-', '')\n"
        "def b(root: Any) -> str:\n    return regexp_replace(root.s, '[0-9]+', '#')\n"
        "def c(root: Any) -> str | None:\n    return regexp_group(root.s, '([a-z]+)-([0-9]+)', 2)\n"
        "def d(root: Any) -> str:\n    return remove_prefix(root.s, 'ab')\n"
        "def e(root: Any) -> str:\n    return format_decimal(root.n, 2)\n"
        "def f(root: Any) -> number | None:\n    return to_number(root.t)\n"
        "def g(root: Any) -> str:\n    return to_string(root.n)\n"
        "def h(root: Any) -> str:\n    return to_utc(root.ts)\n"
        "def i(root: Any) -> str:\n    return rfc3339_normalize(root.ts)\n"
        "def j(root: Any) -> str | None:\n    return replace(root.missing, 'x')\n"
        "out.A = a(root)\nout.B = b(root)\nout.C = c(root)\nout.D = d(root)\nout.E = e(root)\n"
        "out.F = f(root)\nout.G = g(root)\nout.H = h(root)\nout.I = i(root)\nout.J = j(root)\n",
    )
    out, errors = module.map_m_safe(
        {"s": "ab-12", "n": 2.5, "t": "7", "ts": "2026-10-03T09:30:00+02:00"}
    )
    assert errors == []
    assert out == {
        "A": "ab12",
        "B": "ab-#",
        "C": "12",
        "D": "-12",
        "E": "2.50",
        "F": 7,
        "G": "2.5",
        "H": "2026-10-03T07:30:00Z",
        "I": "2026-10-03T09:30:00+02:00",
        "J": None,
    }
    # a text that is not a number is that rule's failure, the others are not touched
    out, errors = module.map_m_safe({"s": "x", "t": "abc", "n": 1, "ts": "2026-10-03T09:30:00Z"})
    assert [e["rule"] for e in errors] == ["f"] and out["A"] == "x" and "F" not in out


@pytest.mark.parametrize("name", GOLDEN_MAPPINGS)
def test_every_golden_mapping_also_compiles_to_plsql(name: str) -> None:
    """What track 1 can say about the PL/SQL side of a golden mapping: it compiles (that it gives the
    same results is for track 2, on an Oracle database)."""
    from compiler.backends.plsql.backend import PlsqlBackend

    backend = PlsqlBackend({"schema": "S", "error_code": -20000, "mapping_package_prefix": "M_"})
    unit = compile_unit((ROOT / "mappings" / f"{name}.map.py").read_text(), name, backend)
    assert backend.assemble([unit])


_PARALLEL = """
@dataclass
class Item:
    n: int
    skip: bool


@dataclass
class Doc:
    items: list[Item]


@dataclass
class Line:
    N: int
    Half: int


def half(n: int) -> int:
    return 10 // n


@parallel(degree=3)
def line(root: Doc, src: Item) -> Line:
    return Line(N=src.n, Half=half(src.n))


for src in root.items:
    if src.skip:
        continue
    out.Lines.append(line(root, src))
"""


def _run(tmp_path: Path, options: dict[str, Any], items: list[dict[str, Any]]) -> tuple[Any, Any]:
    backend = PythonBackend(options)
    unit = compile_unit(_PARALLEL, "m", backend)
    tmp_path.mkdir()
    for name, text in backend.assemble([unit]).items():
        (tmp_path / name).write_text(text)
    module = _load_files(tmp_path)
    return unit, module.map_m_safe({"items": items})


def _load_files(folder: Path) -> Any:
    for stale in [m for m in sys.modules if m == "j2jme_runtime" or m.startswith("map_")]:
        del sys.modules[stale]
    sys.path.insert(0, str(folder))
    try:
        spec = importlib.util.spec_from_file_location("map_m", folder / "map_m.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(folder))


def test_a_parallel_loop_gives_what_the_sequential_one_does(tmp_path: Path) -> None:
    # 0 fails twice (division by zero, at elements 2 and 5); 4 is filtered out
    items = [{"n": n, "skip": n == 4} for n in (1, 2, 0, 3, 4, 0, 5, 10)]
    threaded_unit, threaded = _run(tmp_path / "t", {"parallel": "thread"}, items)
    plain_unit, plain = _run(tmp_path / "p", {"parallel": "none"}, items)
    assert "_pmap(" in threaded_unit.source and "_pmap(" not in plain_unit.source
    assert threaded == plain
    output, errors = threaded
    assert [line["N"] for line in output["Lines"]] == [1, 2, 0, 3, 0, 5, 10]  # in element order
    assert [e["rule"] for e in errors] == ["half"]  # reported once, for the first failing element


def test_a_process_parallel_loop_gives_what_the_sequential_one_does(tmp_path: Path) -> None:
    items = [{"n": n, "skip": n == 4} for n in (1, 2, 0, 3, 4, 0, 5, 10)]
    unit, processed = _run(tmp_path / "x", {"parallel": "process"}, items)
    _, plain = _run(tmp_path / "p", {"parallel": "none"}, items)
    assert "_pmap(" in unit.source and "'process'" in unit.source
    assert processed == plain
    assert [e["rule"] for e in processed[1]] == ["half"]


def test_a_process_parallel_loop_really_runs_in_other_processes(tmp_path: Path) -> None:
    backend = PythonBackend({"parallel": "process"})
    unit = compile_unit(_PARALLEL, "m", backend)
    tmp_path.mkdir(exist_ok=True)
    for name, text in backend.assemble([unit]).items():
        (tmp_path / name).write_text(text)
    module = _load_files(tmp_path)
    runtime = sys.modules["j2jme_runtime"]
    got = runtime._in_processes("line", module.line, 2, [({}, {"n": n}) for n in (1, 2, 5)])
    assert got is not None  # it did not fall back on running them here
    assert [value for value, _ in got] == [
        {"N": 1, "Half": 10},
        {"N": 2, "Half": 5},
        {"N": 5, "Half": 2},
    ]
    assert runtime._pools  # the workers are kept for the next loop


def test_the_build_says_a_parallel_rule_is_not_faster_with_the_global_lock() -> None:
    gil = PythonBackend({"python": "3.14", "parallel": "thread"})
    unit = compile_unit(_PARALLEL, "m", gil)
    (warning,) = gil.unit_warnings(unit)
    assert "line" in warning and "3.14t" in warning
    for options in ({"python": "3.14t"}, {"python": "3.12", "parallel": "none"}):
        free = PythonBackend({"parallel": "thread", **options})
        assert free.unit_warnings(compile_unit(_PARALLEL, "m", free)) == []


def test_every_golden_case_states_its_expected_output() -> None:
    """The golden cases are the contract every backend is held to: a case with no expected output
    would pass on any backend, whatever it gave (and the backends could disagree unseen)."""
    without = [f"{c.mapping}/{c.name}" for c in discover_cases() if c.expected_path is None]
    assert not without, f"golden cases with no .expected.json: {without}"
