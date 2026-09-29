"""Function Linker (docs/ARCHITECTURE.md, §Project functions and overrides).

Resolution priority per function name, per target:
  1. Project `fn/` file with `@override(target=...)` for the current target
  2. Project `fn/` file with a DSL body → compiled through the pipeline
  3. Built-in hardcoded implementation for the current target
  4. None of the above → compile error

`FunctionImpl` and the linker are target-agnostic; the built-in
implementations belong to the backend, which passes them in (for `plsql`:
`compiler/backends/plsql/builtins.py`). Project `fn/` file loading is not
implemented yet — resolution always falls through to built-ins for now.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# A template is either a `str.format`-style string using positional
# `{0}`, `{1}`, ... (fixed arity), or a callable for variadic / structurally
# different renderings (e.g. `concat`, `lookup`).
Renderer = str | Callable[[list[str]], str]


class FunctionLinkError(Exception):
    pass


@dataclass(frozen=True)
class FunctionImpl:
    name: str
    target_templates: dict[str, Renderer]

    def render(self, target: str, arg_exprs: list[str]) -> str:
        try:
            template = self.target_templates[target]
        except KeyError as exc:
            raise FunctionLinkError(
                f"function '{self.name}' has no implementation for target {target!r}"
            ) from exc
        if callable(template):
            return template(arg_exprs)
        return template.format(*arg_exprs)


class FunctionLinker:
    def __init__(
        self,
        builtins: dict[str, FunctionImpl],
        project_functions: dict[str, FunctionImpl] | None = None,
    ):
        self._builtins = builtins
        # Project fn/ overrides (highest priority) — empty until the .fn
        # loader exists; kept as a constructor param so callers/tests can
        # inject them ahead of that.
        self._project_functions = project_functions or {}

    def resolve(self, name: str) -> FunctionImpl:
        if name in self._project_functions:
            return self._project_functions[name]
        if name in self._builtins:
            return self._builtins[name]
        raise FunctionLinkError(f"no implementation found for function '{name}'")
