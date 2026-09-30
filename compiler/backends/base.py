"""Target-backend interface (docs/ARCHITECTURE.md, §Target backends).

The backend is the only target-specific part of the compiler; every phase
before it (Validator, Loop Fusion Optimizer, Scope Resolver, Type Checker,
Function Linker) is language-agnostic. The interface is deliberately coarse:
a backend receives the checked, annotated tree of one mapping and returns a
`CompiledUnit`; it later assembles the units of a whole project into the
deployable artifact. How it emits code inside a unit (per-rule call sites,
loops, entry points, ...) is its own business — targets differ too much for a
shared line-level contract to stay honest.

A backend declares its name in the `target` class attribute (`"plsql"` for
`PlsqlBackend`); `compiler.backends.registry` finds every `Backend` subclass
by importing the modules under `compiler.backends`, so adding a target means
adding a subpackage — nothing is registered by hand.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from compiler.scope_resolver import ScopeResolution


class CodeGenError(Exception):
    """A mapping cannot be compiled or assembled for the target."""


@dataclass(frozen=True)
class Option:
    """One key of a `[target.<name>]` section, as the backend understands it.

    This is what the project-properties form is drawn from, so a backend lists here
    every key it reads and the values it accepts. `kind` is `string`, `int`, `bool`,
    `choice` (one of `choices`) or `table` (string -> string). A backend cannot state
    a rule that spans keys ("this or that") here; that stays in `validate_config`,
    whose message the form shows as a whole."""

    key: str
    kind: Literal["string", "int", "bool", "choice", "table"]
    help: str = ""
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()


def check_options(
    options: tuple[Option, ...], section: dict[str, Any], *, missing: bool = True
) -> list[tuple[str, str]]:
    """(key, message) for every key of `section` that is not one of `options` or holds
    a value of the wrong kind, and (with `missing`) for every required option that is
    absent."""
    known = {o.key: o for o in options}
    problems: list[tuple[str, str]] = []
    for key, value in section.items():
        option = known.get(key)
        if option is None:
            problems.append((key, f"unknown key (allowed: {', '.join(sorted(known))})"))
            continue
        message = _wrong_kind(option, value)
        if message:
            problems.append((key, message))
    for option in options if missing else ():
        if option.required and option.key not in section:
            problems.append((option.key, "required"))
    return problems


def _wrong_kind(option: Option, value: Any) -> str | None:
    if option.kind == "bool":
        return None if isinstance(value, bool) else "must be true or false"
    if option.kind == "int":
        return (
            None if isinstance(value, int) and not isinstance(value, bool) else "must be an integer"
        )
    if option.kind == "string":
        return None if isinstance(value, str) else "must be a string"
    if option.kind == "choice":
        if value in option.choices:
            return None
        return f"must be one of {', '.join(option.choices)}"
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        return "must be a table of strings"
    return None


class CompiledUnit(ABC):
    """One compiled mapping, ready for assembly. Serializable: the build cache
    stores units between runs."""

    mapping_id: str

    @abstractmethod
    def to_json(self) -> dict[str, Any]: ...


class Backend(ABC):
    """One per target language. Built from its `[target.<name>]` section."""

    target: ClassVar[str]
    required_keys: ClassVar[tuple[str, ...]] = ()
    defaults: ClassVar[dict[str, Any]] = {}
    # Every key of `[target.<name>]` the backend reads. When set, `mapper.toml` is
    # checked against it (unknown keys, value kinds) and the desktop tool draws its
    # form from it. A backend that leaves it empty is not checked, and has no form.
    options: ClassVar[tuple[Option, ...]] = ()

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def compile_module(
        self, tree: ast.Module, mapping_id: str, scope_resolution: ScopeResolution | None = None
    ) -> CompiledUnit:
        """Compile one checked mapping. Raises `CodeGenError`."""

    @abstractmethod
    def unit_from_json(self, data: dict[str, Any]) -> CompiledUnit:
        """Inverse of `CompiledUnit.to_json` (build-cache entries)."""

    @classmethod
    def validate_config(cls, section: dict[str, Any]) -> None:
        """Checks beyond `required_keys` on the `[target.<name>]` section; raises
        `CodeGenError`. Called when `mapper.toml` is loaded."""
        return None

    @abstractmethod
    def assemble(self, units: list[CompiledUnit]) -> dict[str, str]:
        """All units of the project -> the deployable artifact files, as
        file name -> text (written under `build/compiled/`). Raises
        `CodeGenError` (e.g. duplicate mapping ids)."""

    def deploy_order(self, file_names: list[str]) -> list[str]:
        """The artifact files in the order the target environment needs them."""
        return sorted(file_names)
