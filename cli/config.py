"""Typed loader for `mapper.toml` (see docs/ARCHITECTURE.md, §Project configuration).

Each target language declares its own required/optional keys under
`[target.<name>]`. A key required by the target but absent from `mapper.toml`
is a build error — this is validated eagerly at load time, not lazily when
the code generator first needs the key.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

CONFIG_FILENAME = "mapper.toml"

# Registry of required keys per compilation target. Extending to a new target
# means adding an entry here; the loader enforces it uniformly.
TARGET_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "plsql": ("schema", "package", "fn_package", "error_code"),
}

TARGET_DEFAULTS: dict[str, dict[str, Any]] = {
    "plsql": {
        "fn_prefix": "",
        "fn_suffix": "",
        # true = also list every fn_<rule_id> in the package spec (not just
        # map_<id>/map_<id>_safe) — §Generated artifact, "Rule-function visibility".
        "export_rule_functions": False,
    },
}


class MapperConfigError(Exception):
    """Raised for any structurally or semantically invalid `mapper.toml`."""


@dataclass(frozen=True)
class ProjectConfig:
    mode: Literal["driven", "bootstrap"] = "driven"
    target: str = "plsql"


@dataclass(frozen=True)
class OptimizerConfig:
    loop_fusion: bool = True
    parallel_conflict: Literal["exception", "max", "min"] = "exception"


@dataclass(frozen=True)
class CompilerConfig:
    decimal_mode: Literal["round", "truncate"] = "round"


@dataclass(frozen=True)
class TestConfig:
    container_image: str | None = None
    container_tag: str | None = None


@dataclass(frozen=True)
class MapperConfig:
    project: ProjectConfig
    optimizer: OptimizerConfig
    compiler: CompilerConfig
    test: TestConfig
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Full parsed TOML, verbatim. §Build folder and incremental compilation:
    # the build cache key is source hash + the hash of this *entire* raw dict,
    # so any config change anywhere invalidates every cached hash project-wide.
    raw: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    def target_config(self, target: str | None = None) -> dict[str, Any]:
        t = target or self.project.target
        try:
            return self.targets[t]
        except KeyError as exc:
            raise MapperConfigError(
                f"no [target.{t}] section in mapper.toml for active target {t!r}"
            ) from exc


def _validate_parallel_conflict(value: Any) -> Literal["exception", "max", "min"]:
    if value not in ("exception", "max", "min"):
        raise MapperConfigError(
            f"[optimizer] parallel_conflict must be one of 'exception', 'max', 'min' — got {value!r}"
        )
    return value


def _validate_decimal_mode(value: Any) -> Literal["round", "truncate"]:
    if value not in ("round", "truncate"):
        raise MapperConfigError(
            f"[compiler] decimal_mode must be 'round' or 'truncate' — got {value!r}"
        )
    return value


def _validate_mode(value: Any) -> Literal["driven", "bootstrap"]:
    if value not in ("driven", "bootstrap"):
        raise MapperConfigError(f"[project] mode must be 'driven' or 'bootstrap' — got {value!r}")
    return value


def _validate_target_section(target: str, section: dict[str, Any]) -> dict[str, Any]:
    required = TARGET_REQUIRED_KEYS.get(target, ())
    missing = [key for key in required if key not in section]
    if missing:
        raise MapperConfigError(
            f"[target.{target}] is missing required key(s): {', '.join(missing)}"
        )
    merged = {**TARGET_DEFAULTS.get(target, {}), **section}
    return merged


def parse_config(raw: dict[str, Any]) -> MapperConfig:
    project_raw = raw.get("project", {})
    project = ProjectConfig(
        mode=_validate_mode(project_raw.get("mode", "driven")),
        target=project_raw.get("target", "plsql"),
    )

    optimizer_raw = raw.get("optimizer", {})
    optimizer = OptimizerConfig(
        loop_fusion=bool(optimizer_raw.get("loop_fusion", True)),
        parallel_conflict=_validate_parallel_conflict(
            optimizer_raw.get("parallel_conflict", "exception")
        ),
    )

    compiler_raw = raw.get("compiler", {})
    compiler = CompilerConfig(
        decimal_mode=_validate_decimal_mode(compiler_raw.get("decimal_mode", "round")),
    )

    test_raw = raw.get("test", {})
    test = TestConfig(
        container_image=test_raw.get("container_image"),
        container_tag=test_raw.get("container_tag"),
    )

    target_section = raw.get("target", {})
    targets = {
        name: _validate_target_section(name, section) for name, section in target_section.items()
    }

    # The active target must have a validated section, even if the project
    # only declares other targets' tables.
    if project.target not in targets:
        raise MapperConfigError(
            f"[project] target = {project.target!r} but no [target.{project.target}] "
            f"section is present in mapper.toml"
        )

    return MapperConfig(
        project=project,
        optimizer=optimizer,
        compiler=compiler,
        test=test,
        targets=targets,
        raw=raw,
    )


def load_config(path: str | Path = CONFIG_FILENAME) -> MapperConfig:
    path = Path(path)
    if not path.is_file():
        raise MapperConfigError(f"no {CONFIG_FILENAME} found at {path}")
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    config = parse_config(raw)
    return MapperConfig(**{**config.__dict__, "path": path})
