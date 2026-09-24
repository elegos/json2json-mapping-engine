"""Compiler pipeline (docs/ARCHITECTURE.md, §Compiler pipeline, Phase 2).

M2a wires: Validator -> Scope Resolver -> Function Linker -> Code Generator.
The Type Checker and Loop Fusion Optimizer are not wired in yet (M2b).
"""

from __future__ import annotations

import ast
from pathlib import Path

from compiler.backends.plsql.codegen import PlsqlCodeGenerator
from compiler.function_linker import FunctionLinker
from compiler.scope_resolver import resolve_scopes
from compiler.validator import Validator


def compile_source(source: str, default_mapping_id: str, error_code: int = -20000) -> str:
    tree = ast.parse(source)
    Validator().validate(tree)  # security gate — must run first

    mapping_id = default_mapping_id
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "__id__"
        ):
            value = stmt.value
            assert isinstance(value, ast.Constant) and isinstance(value.value, str)
            mapping_id = value.value

    scope_resolution = resolve_scopes(tree)
    linker = FunctionLinker()
    backend = PlsqlCodeGenerator(function_linker=linker, error_code=error_code)
    return backend.compile_module(tree, mapping_id, scope_resolution)


def compile_file(path: Path, error_code: int = -20000) -> str:
    return compile_source(path.read_text(), default_mapping_id=path.stem, error_code=error_code)
