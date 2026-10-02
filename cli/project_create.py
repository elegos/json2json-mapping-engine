"""Creating a project from the desktop tool's start wizard (op `project_create` of `mapper serve`):
a `mapper.toml` for the chosen backend and the folders a project keeps its files in."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cli import project_config
from cli.config import CONFIG_FILENAME, MapperConfigError
from compiler.backends.registry import backends

FOLDERS = ("schemas", "mappings/functional", "fn")


def create_project(project: Path, target: str, options: dict[str, Any] | None = None) -> None:
    """Makes `project` (the folder is created when missing) a mapper project for `target`.
    `options` are the values of the backend's `[target.<target>]` section that have no default
    (`schema` for plsql); the defaults and the suggestions the backend declares are written too, so
    the file shows what can be set and loads at once. Nothing is written when the folder already holds a `mapper.toml`, the
    backend is unknown, or the configuration is refused."""
    known = backends()
    if target not in known:
        raise MapperConfigError(
            f"unknown target {target!r} (available: {', '.join(sorted(known))})"
        )
    if (project / CONFIG_FILENAME).exists():
        raise MapperConfigError(f"{project} already has a {CONFIG_FILENAME}")
    section = {o.key: o.default for o in known[target].options if o.default is not None}
    # what the backend proposes for the keys it cannot default (a package prefix, an error code)
    section.update({o.key: o.suggest for o in known[target].options if o.suggest is not None})
    section.update(options or {})
    values: dict[str, Any] = {
        "project": {"mode": "driven", "target": target},
        "target": {target: section},
    }
    issues = project_config.check(values)
    if issues:
        first = issues[0]
        where = f"{first['path']}: " if first["path"] else ""
        raise MapperConfigError(f"{where}{first['message']}")
    project.mkdir(parents=True, exist_ok=True)
    project_config.write(project, values)
    for folder in FOLDERS:
        (project / folder).mkdir(parents=True, exist_ok=True)
