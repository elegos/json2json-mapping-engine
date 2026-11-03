"""The function registry (`compiler/builtins.py`, project `fn/*.fn`) and what is derived from it."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler.backends.plsql.backend import PlsqlBackend  # noqa: F401  (the backend under test)
from compiler.function_registry import (
    all_functions,
    builtin_functions,
    project_functions,
    read_functions,
)
from compiler.pipeline import compile_source
from transpiler.exprtypes import HANDLED, SIGNATURES

REGISTRY = builtin_functions()


def test_the_registry_reads_names_types_and_docs() -> None:
    split = REGISTRY["split_first"]
    assert split.signature() == "split_first(s, sep)"
    assert [(p.name, p.annotation) for p in split.params] == [("s", "str"), ("sep", "str")]
    assert split.returns == "str" and "before the first" in split.doc
    assert REGISTRY["lookup"].signature() == "lookup(key, table, default?)"
    assert REGISTRY["concat"].signature() == "concat(*parts)"
    assert REGISTRY["concat"].params[0].variadic


def test_the_typer_tables_come_from_the_registry() -> None:
    assert set(SIGNATURES) | HANDLED == set(REGISTRY)
    assert {n for n, f in REGISTRY.items() if f.special} == HANDLED
    assert "split_first" in SIGNATURES and "lookup" in HANDLED


def _argument(annotation: str) -> str:
    base = annotation.split("|")[0].strip()
    return {
        "str": "root.a",
        "int": "1",
        "float": "root.n",
        "Mapping[str, Any]": '{"k": "v"}',
    }.get(base, "root.xs" if base.startswith("list") else "root.a")


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_the_plsql_backend_implements_every_registered_function(name: str) -> None:
    info = REGISTRY[name]
    args = [_argument(p.annotation) for p in info.params if p.default is None or name in ("max",)]
    if info.params[-1].variadic:
        args.append(args[-1])
    if name in ("max", "min", "sum", "avg"):
        args = ["root.xs", '"v"']
    if name == "matches":
        args = ["root.a", '"[a-z]+"']
    if name in ("any", "all"):
        args = ["x.a for x in root.xs"]
    call = f"{name}({', '.join(args)})"
    source = f"""from __mapping__ import *

@dataclass
class Out:
    A: str | None

def a(root: Any) -> str | None:
    return {call}

out.A = a(root)
"""
    compile_source(source, "m")  # raises when the backend has no implementation


def test_project_functions_replace_builtins_and_carry_their_origin(tmp_path: Path) -> None:
    folder = tmp_path / "fn"
    folder.mkdir()
    (folder / "text.fn").write_text(
        "from __mapping__ import override\n\n"
        "@override(plsql=\"REGEXP_SUBSTR({s}, '[^ ]+', 1, {n})\")\n"
        "def split_part(s: str, n: int) -> str | None:\n"
        '    """The n-th word."""\n'
        "    return None\n\n"
        "def split_first(s: str) -> str:\n"
        "    return s\n"
        "def _helper() -> None: ...\n"
    )
    (folder / "broken.fn").write_text("def (:\n")
    found = project_functions(tmp_path)
    assert set(found) == {"split_part", "split_first"}
    part = found["split_part"]
    assert part.origin == "fn/text.fn" and part.doc == "The n-th word."
    assert part.overrides == {"plsql": "REGEXP_SUBSTR({s}, '[^ ]+', 1, {n})"}
    merged = all_functions(tmp_path)
    assert merged["split_first"].origin == "fn/text.fn"  # replaced
    assert merged["round"].origin == "built-in"
    assert all_functions(None) == REGISTRY and project_functions(None) == {}


def test_read_functions_ignores_helpers_and_non_functions() -> None:
    found = read_functions("X = 1\ndef _h(): ...\ndef f(a, *rest, b: int = 2) -> int: ...\n")
    assert list(found) == ["f"]
    assert found["f"].signature() == "f(a, *rest)"


def test_the_ide_stub_declares_the_registered_functions() -> None:
    import ast

    from cli.stubs import _MAPPING_STUB_TEXT, function_stubs

    text = _MAPPING_STUB_TEXT + "\n" + function_stubs(REGISTRY)
    tree = ast.parse(text)  # a valid stub
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert set(REGISTRY) <= defined and {"override", "parallel"} <= defined
    assert "def lookup(key: str, table: Mapping[str, Any], default: Any = ...) -> Any:" in text
    assert "def concat(*parts: Any) -> str:" in text
