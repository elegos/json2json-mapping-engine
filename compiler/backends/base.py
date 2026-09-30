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
from typing import Any, ClassVar

from compiler.scope_resolver import ScopeResolution


class CodeGenError(Exception):
    """A mapping cannot be compiled or assembled for the target."""


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
