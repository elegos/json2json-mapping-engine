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
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from compiler.backends.integration import CaseResult, IntegrationContext
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
    # what a new project proposes for a key that has no default (the user may change it); for a
    # key that must be given, or that a rule across keys makes necessary
    suggest: Any = None
    # limits the value must respect; the form shows what `check_options` says about them
    minimum: int | None = None  # `int` kind
    maximum: int | None = None
    min_length: int | None = None  # `string` kind
    max_length: int | None = None
    pattern: str | None = None  # `string` kind: the whole value matches this regular expression
    pattern_hint: str = ""  # how to say the pattern in words ("letters, digits and _")


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


def check_target_options(
    cls: type[Backend], section: dict[str, Any], *, missing: bool = True
) -> list[tuple[str, str]]:
    """`check_options` for a whole `[target.<name>]` section: its own keys, and the keys of its
    `test` sub-table (`[target.<name>.test]`, what the backend's integration tests need) under the
    name `test.<key>`. A backend that declares neither is not checked."""
    own = {k: v for k, v in section.items() if k != "test" or not cls.test_options}
    problems = check_options(cls.options, own, missing=missing) if cls.options else []
    if cls.test_options and "test" in section:
        test = section["test"]
        if not isinstance(test, dict):
            problems.append(("test", "must be a table"))
        else:
            problems += [
                (f"test.{key}", message)
                for key, message in check_options(cls.test_options, test, missing=False)
            ]
    return problems


def _out_of_range(option: Option, value: int) -> str | None:
    low, high = option.minimum, option.maximum
    if low is not None and high is not None and not low <= value <= high:
        return f"must be between {low} and {high}"
    if low is not None and value < low:
        return f"must be at least {low}"
    if high is not None and value > high:
        return f"must be at most {high}"
    return None


def _wrong_text(option: Option, value: str) -> str | None:
    if option.choices and value not in option.choices:
        return f"must be one of {', '.join(option.choices)}"
    if option.min_length is not None and len(value) < option.min_length:
        return f"must have at least {option.min_length} characters"
    if option.max_length is not None and len(value) > option.max_length:
        return f"must have at most {option.max_length} characters"
    if option.pattern is not None and not re.fullmatch(option.pattern, value):
        return option.pattern_hint or f"must match {option.pattern}"
    return None


def _wrong_kind(option: Option, value: Any) -> str | None:
    if option.kind == "bool":
        return None if isinstance(value, bool) else "must be true or false"
    if option.kind == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            return "must be an integer"
        return _out_of_range(option, value)
    if option.kind == "string":
        if not isinstance(value, str):
            return "must be a string"
        return _wrong_text(option, value)
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
    # Every key of `[target.<name>.test]`, what this backend's integration tests need (an image
    # for a database that runs in a container, say). Empty when it needs nothing.
    test_options: ClassVar[tuple[Option, ...]] = ()
    # Whether the backend can run the golden cases (track 2) at all.
    has_integration: ClassVar[bool] = False

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

    def integration_unavailable(self) -> str | None:
        """Why the integration tests cannot run here (no container runtime, say), or None when
        they can. Only asked of a backend with `has_integration`."""
        return None

    def run_integration(self, context: IntegrationContext) -> list[CaseResult]:
        """Run every case of `context` in the target environment. Raises `IntegrationError` when
        the environment is unusable. Only called on a backend with `has_integration`."""
        raise NotImplementedError(f"the {self.target} backend has no integration tests")

    def deploy_order(self, file_names: list[str]) -> list[str]:
        """The artifact files in the order the target environment needs them."""
        return sorted(file_names)
