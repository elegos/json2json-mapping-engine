"""The engine version a project declares (`[project] engine` in `mapper.toml`) against the one
that is running (docs/ARCHITECTURE.md, §Project configuration).

A newer tool upgrades the project (writes its own version into `mapper.toml`) after warning; an
older tool refuses to open it unless the user accepts the risk, and **never** writes an older
version over a newer one: the file is only ever moved forward."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cli._version import ENGINE_VERSION
from cli.config import CONFIG_FILENAME, MapperConfigError

_SEMVER = re.compile(
    r"^(?P<core>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))(?:-(?P<pre>[0-9A-Za-z.-]+))?$"
)

Status = Literal["current", "upgrade", "older", "unversioned"]


def parse(version: str) -> tuple[tuple[int, int, int], tuple[tuple[int, int | str], ...] | None]:
    """`(major, minor, patch)` and the pre-release identifiers (None for a release), as semver
    orders them. Raises `ValueError` for anything that is not `X.Y.Z` or `X.Y.Z-suffix`."""
    found = _SEMVER.match(version)
    if found is None:
        raise ValueError(f"not a version: {version!r} (expected X.Y.Z or X.Y.Z-suffix)")
    major, minor, patch = (int(n) for n in found["core"].split("."))
    pre = found["pre"]
    ids = None
    if pre is not None:
        # a numeric identifier sorts before an alphanumeric one, and numerically among its own
        ids = tuple((0, int(i)) if i.isdigit() else (1, i) for i in pre.split("."))
    return (major, minor, patch), ids


def compare(a: str, b: str) -> int:
    """-1, 0 or 1 as `a` is older than, the same as, or newer than `b` (semver precedence)."""
    (core_a, pre_a), (core_b, pre_b) = parse(a), parse(b)
    if core_a != core_b:
        return -1 if core_a < core_b else 1
    if pre_a == pre_b:
        return 0
    if pre_a is None:  # a release is newer than its pre-releases
        return 1
    if pre_b is None:
        return -1
    return -1 if pre_a < pre_b else 1


@dataclass(frozen=True)
class EngineStatus:
    """`status`: `current` (same version), `upgrade` (the tool is newer: the project will be
    moved up), `older` (the tool is older than the project), `unversioned` (the project declares
    none: it is taken up like an upgrade)."""

    status: Status
    project: str | None
    tool: str

    def to_json(self) -> dict[str, str | None]:
        return {"status": self.status, "project": self.project, "tool": self.tool}


def declared(project: Path) -> str | None:
    """`[project] engine` of the project's `mapper.toml`; None when there is none."""
    path = project / CONFIG_FILENAME
    try:
        raw = tomllib.loads(path.read_text())
    except OSError as exc:
        raise MapperConfigError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise MapperConfigError(f"{path} is not valid TOML: {exc}") from exc
    value = raw.get("project", {}).get("engine")
    if value is None:
        return None
    if not isinstance(value, str):
        raise MapperConfigError("[project] engine must be a string (a version, X.Y.Z)")
    try:
        parse(value)
    except ValueError as exc:
        raise MapperConfigError(f"[project] engine: {exc}") from exc
    return value


def status(project: Path, tool: str = ENGINE_VERSION) -> EngineStatus:
    wanted = declared(project)
    if wanted is None:
        return EngineStatus("unversioned", None, tool)
    order = compare(tool, wanted)
    return EngineStatus(
        "current" if order == 0 else "upgrade" if order > 0 else "older", wanted, tool
    )


def upgrade(project: Path, tool: str = ENGINE_VERSION) -> EngineStatus:
    """Write the tool's version into the project's `mapper.toml` (comments kept) when it is newer
    than the declared one, or none is declared. Never lowers it: an older tool raises
    `MapperConfigError`. Returns the status from before."""
    import tomlkit

    before = status(project, tool)
    if before.status == "older":
        raise MapperConfigError(
            f"the project is at engine {before.project}, newer than this tool ({tool}): "
            "mapper.toml is never moved back"
        )
    if before.status != "current":
        path = project / CONFIG_FILENAME
        document = tomlkit.parse(path.read_text())
        if "project" not in document:
            document["project"] = tomlkit.table()
        document["project"]["engine"] = tool  # type: ignore[index]
        path.write_text(tomlkit.dumps(document))
    return before
