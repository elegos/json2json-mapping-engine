"""Build orchestration for the `mapper` CLI (docs/ARCHITECTURE.md, §Build CLI,
§Build folder and incremental compilation).

Bootstrap mode only for now (M3) — `mapper.toml`'s `mode = "driven"` path
(re-transpile `.fn.yaml` before compiling) needs the M5 transpiler, not yet
built; `mapper build`/`compile` raise a clear error in that mode rather than
silently doing nothing.

**Schema-to-mapping convention** — not specified anywhere in the
architecture doc (a gap noted when the Type Checker was built: "the
architecture doc does not specify how a `.map.py` file declares which
schema pair it targets"). Resolved here, simply: `mappings/<name>.map.py`
picks up `schemas/input/<name>.json` and `schemas/output/<name>.json` if
they exist, independently (either, both, or neither) — convention over
configuration, easy to override later with an explicit mapping table in
`mapper.toml` if that ever proves insufficient.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cli.config import MapperConfig
from compiler.backends.plsql.codegen import CodeGenError, PlsqlUnit
from compiler.backends.plsql.package import assemble_package
from compiler.pipeline import compile_unit, extract_mapping_id
from compiler.schema_generator import SchemaTypes, resolve_schema_types

MAPPINGS_DIR = Path("mappings")
SCHEMAS_INPUT_DIR = Path("schemas/input")
SCHEMAS_OUTPUT_DIR = Path("schemas/output")
BUILD_CACHE_DIR = Path("build/cache")
BUILD_COMPILED_DIR = Path("build/compiled")


class BuildError(Exception):
    pass


def _pascal_case(name: str) -> str:
    import re

    parts = re.split(r"[^0-9a-zA-Z]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Anon"


def discover_mappings() -> list[Path]:
    if not MAPPINGS_DIR.is_dir():
        return []
    return sorted(MAPPINGS_DIR.glob("*.map.py"))


def resolve_schema_for(mapping_stem: str, schema_dir: Path) -> SchemaTypes | None:
    schema_path = schema_dir / f"{mapping_stem}.json"
    if not schema_path.is_file():
        return None
    schema = json.loads(schema_path.read_text())
    return resolve_schema_types(schema, _pascal_case(mapping_stem))


def compute_hash(source: bytes, config_raw: dict) -> str:
    h = hashlib.sha256()
    h.update(source)
    h.update(json.dumps(config_raw, sort_keys=True).encode())
    return h.hexdigest()


def compile_fresh(path: Path, config: MapperConfig) -> PlsqlUnit:
    """Compile `path` unconditionally — no cache lookup. Used by both the
    caching path (on a cache miss) and `mapper check` (which must never
    trust the cache, since the cache only tracks *source* hashes, not
    whether the committed output still matches)."""
    if config.project.mode != "bootstrap":
        raise BuildError(
            f"mode = {config.project.mode!r} — driven-mode transpilation isn't "
            "implemented yet (M5); only bootstrap .map.py compilation is available"
        )
    stem = path.stem.removesuffix(".map")
    target_config = config.target_config()
    input_schema = resolve_schema_for(stem, SCHEMAS_INPUT_DIR)
    output_schema = resolve_schema_for(stem, SCHEMAS_OUTPUT_DIR)
    return compile_unit(
        path.read_text(),
        default_mapping_id=stem,
        error_code=target_config["error_code"],
        input_schema=input_schema,
        output_schema=output_schema,
        loop_fusion=config.optimizer.loop_fusion,
        parallel_conflict=config.optimizer.parallel_conflict,
    )


def mapping_id_of(path: Path) -> str:
    stem = path.stem.removesuffix(".map")
    return extract_mapping_id(ast.parse(path.read_text()), stem)


def package_name(config: MapperConfig) -> str:
    return config.target_config()["package"]


def package_path(config: MapperConfig) -> Path:
    return BUILD_COMPILED_DIR / f"{package_name(config).lower()}.sql"


def assemble(units: list[PlsqlUnit], config: MapperConfig) -> str:
    try:
        return assemble_package(
            units, package_name(config), config.target_config()["export_rule_functions"]
        )
    except CodeGenError as exc:
        raise BuildError(str(exc)) from exc


@dataclass
class CompileResult:
    path: Path
    skipped: bool
    unit: PlsqlUnit


def compile_mapping(path: Path, config: MapperConfig, force: bool = False) -> CompileResult:
    """Compile one mapping to its `PlsqlUnit`, cached in `build/cache/` keyed on
    source hash + full `mapper.toml`. Units are assembled into the project's
    single package by `write_package`."""
    source = path.read_bytes()
    digest = compute_hash(source, config.raw)
    cache_file = BUILD_CACHE_DIR / f"{path.name}.unit.json"

    if not force and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text())
            if cached["hash"] == digest:
                return CompileResult(path, True, PlsqlUnit.from_json(cached["unit"]))
        except (ValueError, KeyError, TypeError):
            pass  # corrupt cache entry — recompile

    unit = compile_fresh(path, config)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"hash": digest, "unit": unit.to_json()}, indent=1))
    return CompileResult(path, False, unit)


def write_package(units: list[PlsqlUnit], config: MapperConfig) -> Path:
    out = package_path(config)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(assemble(units, config))
    return out
