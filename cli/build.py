"""Build orchestration for the `mapper` CLI (docs/ARCHITECTURE.md, §Build CLI,
§Build folder and incremental compilation).

Two modes (`mapper.toml` `[project] mode`):

- `bootstrap` — sources are the hand-written `mappings/*.map.py`;
- `driven` — sources are `mappings/functional/*.fn.yaml`; each is transpiled
  (M5) to `build/transpiled/<name>.map.py`, which is then compiled like a
  hand-written one. The transpiled file is an ephemeral artifact, kept for
  inspection.

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
from dataclasses import dataclass, field
from pathlib import Path

from cli.config import MapperConfig
from compiler.backends.plsql.codegen import CodeGenError, PlsqlUnit
from compiler.backends.plsql.package import assemble_package
from compiler.pipeline import compile_unit, extract_mapping_id
from compiler.schema_generator import SchemaTypes, resolve_schema_types
from transpiler.model import FnYamlError, load_functional_file
from transpiler.stages import STAGES, run_stages
from transpiler.transpile import TranspileOptions, transpile_file

MAPPINGS_DIR = Path("mappings")
FUNCTIONAL_DIR = Path("mappings/functional")
BUILD_TRANSPILED_DIR = Path("build/transpiled")
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


def is_functional(path: Path) -> bool:
    return path.name.endswith(".fn.yaml")


def source_stem(path: Path) -> str:
    return path.name.removesuffix(".fn.yaml").removesuffix(".map.py")


def discover_mappings(config: MapperConfig | None = None) -> list[Path]:
    """The mapping sources for the project's mode (bootstrap unless told otherwise)."""
    if config is not None and config.project.mode == "driven":
        return sorted(FUNCTIONAL_DIR.glob("*.fn.yaml")) if FUNCTIONAL_DIR.is_dir() else []
    if not MAPPINGS_DIR.is_dir():
        return []
    return sorted(MAPPINGS_DIR.glob("*.map.py"))


def resolve_schema_for(mapping_stem: str, schema_dir: Path) -> SchemaTypes | None:
    schema_path = schema_dir / f"{mapping_stem}.json"
    if not schema_path.is_file():
        return None
    schema = json.loads(schema_path.read_text())
    return resolve_schema_types(schema, _pascal_case(mapping_stem))


def compute_hash(source: bytes, config_raw: dict, extra: list[bytes] | None = None) -> str:
    h = hashlib.sha256()
    h.update(source)
    h.update(json.dumps(config_raw, sort_keys=True).encode())
    for blob in extra or []:
        h.update(blob)
    return h.hexdigest()


def _schema_bytes(stem: str) -> list[bytes]:
    """Schemas a mapping is checked/typed against — part of its cache key."""
    return [
        p.read_bytes()
        for p in (SCHEMAS_INPUT_DIR / f"{stem}.json", SCHEMAS_OUTPUT_DIR / f"{stem}.json")
        if p.is_file()
    ]


def transpile_options(config: MapperConfig) -> TranspileOptions:
    return TranspileOptions(
        loop_fusion=config.optimizer.loop_fusion,
        parallel_conflict=config.optimizer.parallel_conflict,
        format_choice=config.compiler.default_choices.format,
        multiple_of_choice=config.compiler.default_choices.multiple_of,
    )


def stages_dir(path: Path) -> Path:
    return BUILD_TRANSPILED_DIR / "stages" / source_stem(path)


def transpile_functional(
    path: Path,
    config: MapperConfig,
    write: bool = True,
    warnings: list[str] | None = None,
    stage: int | None = None,
    dump_stages: bool = False,
    cached: bool = False,
    log: list[str] | None = None,
) -> str:
    """`.fn.yaml` -> `.map.py` source text (driven mode). With `write`, also
    saved to `build/transpiled/<stem>.map.py`.

    `stage` (1-4) stops after that stage and writes the stage artifacts to
    `build/transpiled/stages/<stem>/` (removing later ones); `dump_stages`
    writes all four; `cached` (needs `stage`) resumes from the previous
    stage's artifact. The final `.map.py` is only written when the run
    reaches the last stage."""
    stem = source_stem(path)
    options = transpile_options(config)
    schema = resolve_schema_for(stem, SCHEMAS_INPUT_DIR)
    try:
        if stage is None and not dump_stages:
            text = transpile_file(path, options, input_schema=schema, warnings=warnings)
            last = len(STAGES)
        else:
            last = stage or len(STAGES)
            text = run_stages(
                path,
                options,
                last,
                stages_dir(path),
                input_schema=schema,
                cached=cached,
                warnings=warnings,
                log=log,
            )
    except FnYamlError as exc:
        raise BuildError(f"{path}: {exc}") from exc
    if write and last == len(STAGES):
        BUILD_TRANSPILED_DIR.mkdir(parents=True, exist_ok=True)
        (BUILD_TRANSPILED_DIR / f"{stem}.map.py").write_text(text)
    return text


def compile_fresh(path: Path, config: MapperConfig) -> PlsqlUnit:
    """Compile `path` unconditionally — no cache lookup. Used by both the
    caching path (on a cache miss) and `mapper check` (which must never
    trust the cache, since the cache only tracks *source* hashes, not
    whether the committed output still matches)."""
    return _compile_fresh(path, config, [])


def _compile_fresh(path: Path, config: MapperConfig, warnings: list[str]) -> PlsqlUnit:
    stem = source_stem(path)
    if is_functional(path):
        if config.project.mode != "driven":
            raise BuildError(f"{path}: .fn.yaml files are only built in mode = 'driven'")
        source = transpile_functional(path, config, warnings=warnings)
    else:
        source = path.read_text()
    target_config = config.target_config()
    input_schema = resolve_schema_for(stem, SCHEMAS_INPUT_DIR)
    output_schema = resolve_schema_for(stem, SCHEMAS_OUTPUT_DIR)
    return compile_unit(
        source,
        default_mapping_id=stem,
        error_code=target_config["error_code"],
        input_schema=input_schema,
        output_schema=output_schema,
        loop_fusion=config.optimizer.loop_fusion,
        parallel_conflict=config.optimizer.parallel_conflict,
    )


def mapping_id_of(path: Path) -> str:
    stem = source_stem(path)
    if is_functional(path):
        return load_functional_file(path).id
    return extract_mapping_id(ast.parse(path.read_text()), stem)


def find_source(stem: str, config: MapperConfig) -> Path | None:
    for p in discover_mappings(config):
        if source_stem(p) == stem:
            return p
    return None


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
    warnings: list[str] = field(default_factory=list)  # transpiler findings, cached with the unit


def compile_mapping(path: Path, config: MapperConfig, force: bool = False) -> CompileResult:
    """Compile one mapping to its `PlsqlUnit`, cached in `build/cache/` keyed on
    source hash + full `mapper.toml`. Units are assembled into the project's
    single package by `write_package`."""
    source = path.read_bytes()
    digest = compute_hash(source, config.raw, _schema_bytes(source_stem(path)))
    cache_file = BUILD_CACHE_DIR / f"{path.name}.unit.json"

    if not force and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text())
            if cached["hash"] == digest:
                return CompileResult(
                    path, True, PlsqlUnit.from_json(cached["unit"]), cached.get("warnings", [])
                )
        except (ValueError, KeyError, TypeError):
            pass  # corrupt cache entry — recompile

    warnings: list[str] = []
    unit = _compile_fresh(path, config, warnings)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"hash": digest, "unit": unit.to_json(), "warnings": warnings}, indent=1)
    )
    return CompileResult(path, False, unit, warnings)


def write_package(units: list[PlsqlUnit], config: MapperConfig) -> Path:
    out = package_path(config)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(assemble(units, config))
    return out
