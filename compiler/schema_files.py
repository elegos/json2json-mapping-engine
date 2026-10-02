"""Where a mapping's JSON Schemas live: `schemas/<name>_input.schema.json` and
`schemas/<name>_output.schema.json`, flat, next to `mappings/functional/<name>.fn.yaml`."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Literal

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


def _read_schema(path: Path) -> dict[str, Any]:
    """The JSON object in `path`; raises ValueError with the reason when it is not one."""
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        raise ValueError(f"{path.name}: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise ValueError(f"{path.name} is not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a JSON Schema: the top level is not an object")
    return data


def schema_status(
    project: Path, stem: str, kind: Kind, override: str | None = None
) -> dict[str, Any]:
    """What the tool shows for one schema of a mapping: `state` is `ok` (found and readable),
    `missing` or `invalid` (with the `reason`), and the `path` it looks at, from the project."""
    path = resolve_schema_path(project, stem, kind, override)
    shown = str(path.relative_to(project)) if path.is_relative_to(project) else str(path)
    if not path.is_file():
        return {"state": "missing", "path": shown, "reason": "no such file"}
    try:
        _read_schema(path)
    except ValueError as exc:
        return {"state": "invalid", "path": shown, "reason": str(exc)}
    return {"state": "ok", "path": shown, "reason": None}


def import_schema(project: Path, stem: str, kind: Kind, source: Path) -> Path:
    """Copies the schema in `source` into the project under the mapping's name
    (`schemas/<stem>_<kind>.schema.json`), replacing the one there. A file that is not JSON
    object is refused (ValueError) before anything is written."""
    _read_schema(source)
    dest = schema_path(project / SCHEMAS_DIR, stem, kind)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (dest.exists() and dest.samefile(source)):
        shutil.copyfile(source, dest)
    return dest
