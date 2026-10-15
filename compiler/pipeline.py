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

from compiler.backends.base import Backend, CodeGenError, CompiledUnit
from compiler.backends.registry import DEFAULT_TARGET, create_backend
from compiler.loop_fusion import fuse_loops
from compiler.out_arrays import open_output_arrays
from compiler.portable_regex import portable_regex_error
from compiler.schema_generator import SchemaTypes
from compiler.scope_resolver import resolve_scopes
from compiler.type_checker import check_module
from compiler.validation import ValidationError, canonical_schema, extract
from compiler.validator import Validator


def check_matches_patterns(tree: ast.Module) -> None:
    """The pattern of `matches(text, pattern)` is a literal text in the portable subset: both
    backends then read it the same way."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "matches"
        ):
            pattern = node.args[1] if len(node.args) > 1 else None
            if not (isinstance(pattern, ast.Constant) and isinstance(pattern.value, str)):
                raise CodeGenError("matches(text, pattern): the pattern must be a literal text")
            problem = portable_regex_error(pattern.value)
            if problem:
                raise CodeGenError(f"matches(text, {pattern.value!r}): {problem}")


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
    backend: Backend,
    input_schema: SchemaTypes | None = None,
    output_schema: SchemaTypes | None = None,
    loop_fusion: bool = True,
    parallel_conflict: str = "exception",
    schema_texts: dict[str, str] | None = None,
) -> CompiledUnit:
    """`schema_texts`: the JSON Schema files of the mapping by side (`input` / `output`), which the
    unit embeds for the sides that ask to validate against their schema."""
    tree = ast.parse(source)
    Validator().validate(tree)  # security gate — must run first
    check_matches_patterns(tree)

    mapping_id = extract_mapping_id(tree, default_mapping_id)
    try:
        validation = extract(tree)
    except ValidationError as exc:
        raise CodeGenError(str(exc)) from exc
    if validation is not None:
        for side in ("input", "output"):
            if validation.side(side).schema:
                text = (schema_texts or {}).get(side)
                if text is None:
                    raise CodeGenError(
                        f"the {side} validation asks for the JSON Schema check, but the mapping "
                        f"has no {side} schema"
                    )
                validation.schemas[side] = canonical_schema(text)

    rule_defs = {stmt.name: stmt for stmt in tree.body if isinstance(stmt, ast.FunctionDef)}
    tree.body = fuse_loops(
        tree.body, rule_defs, parallel_conflict=parallel_conflict, fusion_enabled=loop_fusion
    )
    ast.fix_missing_locations(tree)

    scope_resolution = resolve_scopes(tree)
    check_module(tree, scope_resolution, input_schema, output_schema)
    open_output_arrays(tree)

    return backend.compile_module(
        tree, mapping_id, scope_resolution, validation if validation and validation.active else None
    )


def compile_source(
    source: str,
    default_mapping_id: str,
    backend: Backend | None = None,
    **kwargs,
) -> str:
    """Single-mapping convenience: compile and assemble one unit into its
    artifact text. Without `backend`, the default target with its defaults."""
    backend = backend or create_backend(DEFAULT_TARGET)
    unit = compile_unit(source, default_mapping_id, backend, **kwargs)
    return "\n".join(backend.assemble([unit]).values())


def compile_file(path: Path, backend: Backend | None = None, **kwargs) -> str:
    return compile_source(path.read_text(), default_mapping_id=path.stem, backend=backend, **kwargs)
