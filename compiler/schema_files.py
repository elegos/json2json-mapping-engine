"""Where a mapping's JSON Schemas live: `schemas/<name>_input.schema.json` and
`schemas/<name>_output.schema.json`, flat, next to `mappings/functional/<name>.fn.yaml`."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

SCHEMAS_DIR = Path("schemas")

Kind = Literal["input", "output"]


def suffix(kind: Kind) -> str:
    return f"_{kind}.schema.json"


def schema_path(schemas_dir: Path, stem: str, kind: Kind) -> Path:
    return schemas_dir / f"{stem}{suffix(kind)}"


def resolve_schema_path(project: Path, stem: str, kind: Kind, override: str | None = None) -> Path:
    """The schema file of a mapping: its `schemas:` override (from the project root) when it
    has one, else the convention."""
    if override:
        return project / override
    return schema_path(project / SCHEMAS_DIR, stem, kind)


def schema_stems(schemas_dir: Path, kind: Kind) -> list[str]:
    """The mapping names that have a schema of `kind` in `schemas_dir`, sorted."""
    ending = suffix(kind)
    return sorted(p.name.removesuffix(ending) for p in schemas_dir.glob(f"*{ending}"))
