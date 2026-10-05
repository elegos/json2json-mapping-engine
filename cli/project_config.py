"""Reading, checking and writing `mapper.toml` for the desktop tool's project-properties form.

The form is drawn from descriptors, not from code of its own: the engine's sections are
listed here, and each backend lists the keys of its own `[target.<name>]` section
(`Backend.options`). Values travel as the plain dict `tomllib` reads. Writing goes through
`tomlkit`, so comments and key order of the file survive; only what changed is touched.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cli.config import CONFIG_FILENAME, MapperConfigError, parse_config
from compiler.backends.base import Option, check_options, check_target_options
from compiler.backends.registry import backends


@dataclass(frozen=True)
class Section:
    path: tuple[str, ...]
    title: str
    options: tuple[Option, ...]


_ROUNDING = ("round", "truncate")

ENGINE_SECTIONS: tuple[Section, ...] = (
    Section(
        ("project",),
        "Project",
        (
            Option(
                "mode",
                "choice",
                "driven: .fn.yaml files are the source; bootstrap: .map.py written by hand",
                default="driven",
                choices=("driven", "bootstrap"),
            ),
            # `choices` is filled with the available backends when the form is described
            Option("target", "choice", "Compilation target", default="plsql"),
        ),
    ),
    Section(
        ("optimizer",),
        "Optimizer",
        (
            Option(
                "loop_fusion",
                "bool",
                "Fuse loops over the same source; disable if side-effects are suspected",
                default=True,
            ),
            Option(
                "parallel_conflict",
                "choice",
                "Fused loops that declare different @parallel degrees: error, or take the max / min",
                default="exception",
                choices=("exception", "max", "min"),
            ),
        ),
    ),
    Section(
        ("compiler", "default_choices"),
        "Default choices",
        (
            Option("format", "choice", "Decimals of `format`", default="round", choices=_ROUNDING),
            Option(
                "multipleOf",
                "choice",
                "Snapping of `allowed.multipleOf`",
                default="round",
                choices=_ROUNDING,
            ),
        ),
    ),
    Section(
        ("publish",),
        "Publish",
        (
            Option(
                "dir",
                "string",
                "Folder `mapper publish` puts the generated files in: relative to the project, "
                "or absolute. Empty: build/compiled",
            ),
        ),
    ),
)


def _engine_sections() -> list[Section]:
    targets = tuple(sorted(backends()))
    sections = []
    for section in ENGINE_SECTIONS:
        options = tuple(
            Option(**{**asdict(o), "choices": targets})
            if o.key == "target" and section.path == ("project",)
            else o
            for o in section.options
        )
        sections.append(Section(section.path, section.title, options))
    return sections


def _option_json(option: Option) -> dict[str, Any]:
    return {**asdict(option), "choices": list(option.choices)}


def describe() -> dict[str, Any]:
    """What the form is drawn from: the engine's sections and every backend's options."""
    return {
        "engine": [
            {
                "path": list(s.path),
                "title": s.title,
                "options": [_option_json(o) for o in s.options],
            }
            for s in _engine_sections()
        ],
        "targets": {
            name: [_option_json(o) for o in cls.options]
            for name, cls in sorted(backends().items())
            if cls.options
        },
        # what a backend's integration tests need: `[target.<name>.test]`
        "target_tests": {
            name: [_option_json(o) for o in cls.test_options]
            for name, cls in sorted(backends().items())
            if cls.test_options
        },
    }


def read(project: Path) -> dict[str, Any]:
    path = project / CONFIG_FILENAME
    try:
        values = tomllib.loads(path.read_text())
    except OSError as exc:
        raise MapperConfigError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise MapperConfigError(f"{path} is not valid TOML: {exc}") from exc
    return {"schema": describe(), "values": values}


def _at(values: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    node: Any = values
    for part in path:
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, dict) else {}


def check(values: dict[str, Any]) -> list[dict[str, str]]:
    """Problems of `values` as `{path, message}`; `path` is dotted (`target.plsql.schema`),
    empty for a problem of the file as a whole."""
    issues: list[dict[str, str]] = []
    for section in _engine_sections():
        given = _at(values, section.path)
        if section.path == ("project",):  # not a form field: the version is `mapper upgrade`'s
            given = {k: v for k, v in given.items() if k != "engine"}
        for key, message in check_options(section.options, given, missing=False):
            issues.append({"path": ".".join((*section.path, key)), "message": message})
    for name, cls in backends().items():
        if (cls.options or cls.test_options) and name in _at(values, ("target",)):
            for key, message in check_target_options(cls, _at(values, ("target", name))):
                issues.append({"path": f"target.{name}.{key}", "message": message})
    if not issues:
        try:
            parse_config(values)
        except MapperConfigError as exc:
            issues.append({"path": "", "message": str(exc)})
    return issues


def _merge(table: Any, values: dict[str, Any]) -> None:
    import tomlkit

    for key in [k for k in table if k not in values]:
        del table[key]
    for key, value in values.items():
        if isinstance(value, dict):
            if key not in table:
                table[key] = tomlkit.table()
            _merge(table[key], value)
        elif key not in table or table[key] != value:
            table[key] = value


def write(project: Path, values: dict[str, Any]) -> None:
    """Writes `values` into the project's `mapper.toml`, keeping its comments. Refuses a
    configuration that `check` reports on."""
    import tomlkit

    issues = check(values)
    if issues:
        first = issues[0]
        where = f"{first['path']}: " if first["path"] else ""
        raise MapperConfigError(f"{where}{first['message']}")
    path = project / CONFIG_FILENAME
    document = tomlkit.parse(path.read_text()) if path.is_file() else tomlkit.document()
    # the engine version is not the form's to change (`mapper upgrade` moves it, forward only)
    kept = document.get("project", {}).get("engine")
    if kept is not None:
        values = {**values, "project": {**values.get("project", {}), "engine": kept}}
    _merge(document, values)
    text = tomlkit.dumps(document)
    if tomllib.loads(text) != values:  # what we are about to write must read back as asked
        raise MapperConfigError("internal error: mapper.toml would not read back as edited")
    path.write_text(text)
