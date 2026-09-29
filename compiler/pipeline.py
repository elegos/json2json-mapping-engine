"""Compiler pipeline (docs/ARCHITECTURE.md, §Compiler pipeline, Phase 2).

Wires: Validator -> Loop Fusion Optimizer -> Scope Resolver -> Type Checker
-> Function Linker -> Code Generator. Loop Fusion runs before scope
resolution/type-checking, not after: it only restructures the statement
shape (merging sibling same-source loops, normalizing `continue`-based
filters into `IF` guards) without changing what's read or written, so
resolving scopes/types once, on the *final* (already-fused) tree, avoids
ever computing a `ScopeResolution` that fusion's tree mutation would make
stale.

`input_schema` / `output_schema` are explicit optional parameters rather
than resolved by a file-naming convention — the architecture doc does not
specify how a `.map.py` file declares which schema pair it targets (that is
a Build CLI concern, M3); the Type Checker itself just needs the resolved
`SchemaTypes`, or `None` for the documented unchecked/`Any` behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path

from compiler.backends.plsql.codegen import PlsqlCodeGenerator, PlsqlUnit
from compiler.backends.plsql.package import assemble_package
from compiler.function_linker import FunctionLinker
from compiler.loop_fusion import fuse_loops
from compiler.schema_generator import SchemaTypes
from compiler.scope_resolver import resolve_scopes
from compiler.type_checker import check_module
from compiler.validator import Validator


def extract_mapping_id(tree: ast.Module, default: str) -> str:
    """The reserved `__id__ = '<literal>'` directive, else `default`."""
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "__id__"
        ):
            value = stmt.value
            assert isinstance(value, ast.Constant) and isinstance(value.value, str)
            return value.value
    return default


def compile_unit(
    source: str,
    default_mapping_id: str,
    error_code: int = -20000,
    input_schema: SchemaTypes | None = None,
    output_schema: SchemaTypes | None = None,
    loop_fusion: bool = True,
    parallel_conflict: str = "exception",
) -> PlsqlUnit:
    tree = ast.parse(source)
    Validator().validate(tree)  # security gate — must run first

    mapping_id = extract_mapping_id(tree, default_mapping_id)

    rule_defs = {stmt.name: stmt for stmt in tree.body if isinstance(stmt, ast.FunctionDef)}
    tree.body = fuse_loops(
        tree.body, rule_defs, parallel_conflict=parallel_conflict, fusion_enabled=loop_fusion
    )
    ast.fix_missing_locations(tree)

    scope_resolution = resolve_scopes(tree)
    check_module(tree, scope_resolution, input_schema, output_schema)

    linker = FunctionLinker()
    backend = PlsqlCodeGenerator(function_linker=linker, error_code=error_code)
    return backend.compile_module(tree, mapping_id, scope_resolution)


def compile_source(
    source: str,
    default_mapping_id: str,
    package: str = "MAPPING_RULES",
    export_rule_functions: bool = False,
    **kwargs,
) -> str:
    """Single-mapping convenience: compile and wrap in its own package."""
    unit = compile_unit(source, default_mapping_id, **kwargs)
    return assemble_package([unit], package, export_rule_functions)


def compile_file(
    path: Path,
    error_code: int = -20000,
    input_schema: SchemaTypes | None = None,
    output_schema: SchemaTypes | None = None,
    loop_fusion: bool = True,
    parallel_conflict: str = "exception",
) -> str:
    return compile_source(
        path.read_text(),
        default_mapping_id=path.stem,
        error_code=error_code,
        input_schema=input_schema,
        output_schema=output_schema,
        loop_fusion=loop_fusion,
        parallel_conflict=parallel_conflict,
    )
