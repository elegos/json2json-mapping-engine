"""The Python backend: the golden cases run on it, and the run-time rules one by one."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from compiler.backends.integration import IntegrationContext, discover_cases
from compiler.backends.python.backend import MIN_PYTHON, PythonBackend
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


@pytest.mark.parametrize("options", [{}, {"parallel": "process"}, {"parallel": "none"}])
def test_every_golden_case_passes_on_the_python_backend(options: dict[str, Any]) -> None:
    backend = PythonBackend(options)
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


_FUSED = """\
from __mapping__ import *

@dataclass
class Doc:
    items: list

@dataclass
class A:
    N: int

@dataclass
class B:
    M: int


def tenth(n: int) -> int:
    return 10 // n


@parallel(degree=3)
def a(root: Doc, src: Any) -> A:
    return A(N=tenth(src.n))


def b(root: Doc, src: Any) -> B:
    return B(M=100 // (src.n - 3))


for src in root.items:
    if src.skip:
        continue
    out.As.append(a(root, src))
for src in root.items:
    out.Bs.append(b(root, src))
"""


def _run_fused(tmp_path: Path, mode: str, items: list[dict[str, Any]]) -> tuple[Any, Any]:
    backend = PythonBackend({"parallel": mode})
    unit = compile_unit(_FUSED, "m", backend)
    tmp_path.mkdir()
    for name, text in backend.assemble([unit]).items():
        (tmp_path / name).write_text(text)
    return unit, _load_files(tmp_path).map_m_safe({"items": items})


@pytest.mark.parametrize("mode", ["thread", "process"])
def test_a_fused_parallel_loop_gives_what_the_sequential_one_does(
    tmp_path: Path, mode: str
) -> None:
    # `a` fails at the elements with 0, `b` at the ones with 3 (and the first of `b` comes first)
    items = [{"n": n, "skip": n == 4} for n in (3, 1, 0, 2, 4, 0, 5, 3, 10)]
    unit, got = _run_fused(tmp_path / "f", mode, items)
    plain_unit, plain = _run_fused(tmp_path / "p", "none", items)
    assert "_pmap_fused(" in unit.source and "_pmap_fused(" not in plain_unit.source
    assert got == plain
    output, errors = got
    assert [e["rule"] for e in errors] == ["b", "tenth"]  # in the order a sequential run meets them
    assert len(output["As"]) == 8 and len(output["Bs"]) == 7


def test_an_exception_outside_a_rule_stops_a_fused_loop_at_its_element(tmp_path: Path) -> None:
    """As in the sequential run: what the earlier elements appended is kept, the later ones are not."""
    _run_fused(tmp_path / "f", "thread", [{"n": 1}])
    runtime = sys.modules["j2jme_runtime"]

    def body(acc: list, root: Any, element: int) -> None:
        runtime._emit(acc, 0, element)
        if element == 3:
            raise ValueError("boom")

    target: list[Any] = []
    with pytest.raises(ValueError, match="boom"):
        runtime._pmap_fused([target], "_body", body, 3, [(None, n) for n in range(6)], "thread")
    assert target == [0, 1, 2, 3]


_NESTED = """\
from __mapping__ import *

@dataclass
class Doc:
    orders: list

@dataclass
class Sub:
    V: int

@dataclass
class Order:
    Id: int
    Subs: list[Sub]


def tenth(n: int) -> int:
    return 10 // n


@parallel(degree=2)
def sub(root: Doc, src1: Any, src: Any) -> Sub:
    return Sub(V=tenth(src.n))


@parallel(degree=3)
def order(root: Doc, src: Any) -> Order:
    order_sub_list = []
    for order_sub_src in src.subs:
        order_sub_list.append(sub(root, src, order_sub_src))
    return Order(Id=src.id, Subs=order_sub_list)


for src in root.orders:
    out.Orders.append(order(root, src))
"""


def _run_nested(tmp_path: Path, options: dict[str, Any], doc: dict[str, Any]) -> tuple[Any, Any]:
    backend = PythonBackend(options)
    unit = compile_unit(_NESTED, "m", backend)
    tmp_path.mkdir()
    for name, text in backend.assemble([unit]).items():
        (tmp_path / name).write_text(text)
    return unit, _load_files(tmp_path).map_m_safe(doc)


@pytest.mark.parametrize(
    "options", [{"parallel": "thread"}, {"parallel": "process"}, {"max_parallel": 2}]
)
def test_nested_parallel_loops_give_what_the_sequential_run_does(
    tmp_path: Path, options: dict[str, Any]
) -> None:
    doc = {
        "orders": [
            {"id": i, "subs": [{"n": n} for n in (1, 2, 0, 5, 0)[: i % 5 + 1]]} for i in range(7)
        ]
    }
    unit, got = _run_nested(tmp_path / "n", options, doc)
    _, plain = _run_nested(tmp_path / "p", {"parallel": "none"}, doc)
    assert unit.source.count("_pmap(") == 2
    assert got == plain
    assert [e["rule"] for e in got[1]] == ["tenth"]


def test_the_workers_in_all_never_pass_the_maximum(tmp_path: Path) -> None:
    """Loops inside loops take what is free of the total, and give it back."""
    import threading
    import time

    _run_fused(tmp_path / "f", "thread", [{"n": 1}])
    runtime = sys.modules["j2jme_runtime"]
    runtime._budget = runtime._Budget(4)
    lock = threading.Lock()
    busy = peak = 0

    def work(acc: list, root: Any, element: int) -> None:
        nonlocal busy, peak
        with lock:
            busy += 1
            peak = busy if busy > peak else peak
        time.sleep(0.02)
        with lock:
            busy -= 1

    def outer(acc: list, root: Any, element: int) -> None:  # an element whose body has a loop
        runtime._pmap_fused([[]], "work", work, 3, [(None, n) for n in range(6)], "thread")

    runtime._pmap_fused([[]], "outer", outer, 3, [(None, n) for n in range(5)], "thread")
    assert 2 <= peak <= 4
    assert runtime._budget.take(4) == 4  # all of it was given back


def test_the_budget_gives_two_workers_or_none() -> None:
    from compiler.backends.python import runtime

    budget = runtime._Budget(3)
    assert budget.take(5) == 3 and budget.take(2) == 0
    budget.give(3)
    assert budget.take(2) == 2 and budget.take(2) == 0  # one is left: not enough to go parallel
    assert runtime._Budget(1).take(4) == 0  # a maximum of 1 is no parallelism


def test_max_parallel_is_one_or_more_and_one_turns_parallelism_off() -> None:
    from compiler.backends.base import check_options

    assert check_options(PythonBackend.options, {"max_parallel": 4}) == []
    for bad in (0, -3):
        assert check_options(PythonBackend.options, {"max_parallel": bad})
    one = PythonBackend({"max_parallel": 1})
    assert "_pmap" not in compile_unit(_NESTED, "m", one).source
    assert "MAX_PARALLEL = 1\n" in one.assemble([])["j2jme_runtime.py"]


def test_the_target_python_is_not_a_key_any_more() -> None:
    assert "python" not in {o.key for o in PythonBackend.options}
    assert "python" not in PythonBackend.defaults


def test_what_is_generated_parses_for_the_first_supported_python(tmp_path: Path) -> None:
    """The modules are Python 3.10+: nothing in them needs a newer syntax (the golden cases are run
    on the old Python itself by `dev_scripts/python_floor.sh`)."""
    backend = PythonBackend({"parallel": "process"})
    units = [
        compile_unit((ROOT / "mappings" / f"{name}.map.py").read_text(), name, backend)
        for name in GOLDEN_MAPPINGS
    ] + [
        compile_unit(source, name, backend)
        for name, source in (("par", _PARALLEL), ("fused", _FUSED), ("nested", _NESTED))
    ]
    for text in backend.assemble(units).values():
        ast.parse(text, feature_version=MIN_PYTHON)


def test_the_runtime_refuses_an_older_python(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "j2jme_runtime.py").write_text(PythonBackend({}).assemble([])["j2jme_runtime.py"])
    monkeypatch.setattr(sys, "version_info", (3, 9, 0, "final", 0))
    sys.modules.pop("j2jme_runtime", None)
    sys.path.insert(0, str(tmp_path))
    try:
        with pytest.raises(ImportError, match=r"Python 3\.10 or later"):
            importlib.import_module("j2jme_runtime")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("j2jme_runtime", None)


def test_every_golden_case_states_its_expected_output() -> None:
    """The golden cases are the contract every backend is held to: a case with no expected output
    would pass on any backend, whatever it gave (and the backends could disagree unseen)."""
    without = [f"{c.mapping}/{c.name}" for c in discover_cases() if c.expected_path is None]
    assert not without, f"golden cases with no .expected.json: {without}"
