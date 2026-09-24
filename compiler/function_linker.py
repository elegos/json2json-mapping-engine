"""Function Linker (docs/ARCHITECTURE.md, §Project functions and overrides).

Resolution priority per function name, per target:
  1. Project `fn/` file with `@override(target=...)` for the current target
  2. Project `fn/` file with a DSL body → compiled through the pipeline
  3. Built-in hardcoded implementation for the current target
  4. None of the above → compile error

M2a ships exactly one hand-written built-in (`coalesce`) to prove the
mechanism end-to-end; the full built-in library lands in M2b
(`compiler/backends/plsql/builtins.py`). Project `fn/` file loading is not
implemented yet — the registry always falls through to built-ins for now.
"""

from __future__ import annotations

from dataclasses import dataclass


class FunctionLinkError(Exception):
    pass


@dataclass(frozen=True)
class FunctionImpl:
    name: str
    # target -> a `str.format`-style template using positional `{0}`, `{1}`, ...
    target_templates: dict[str, str]

    def render(self, target: str, arg_exprs: list[str]) -> str:
        try:
            template = self.target_templates[target]
        except KeyError as exc:
            raise FunctionLinkError(
                f"function '{self.name}' has no implementation for target {target!r}"
            ) from exc
        return template.format(*arg_exprs)


_BUILTINS: dict[str, FunctionImpl] = {
    "coalesce": FunctionImpl(
        name="coalesce",
        target_templates={"plsql": "COALESCE({0}, {1})"},
    ),
}


class FunctionLinker:
    def __init__(self, project_functions: dict[str, FunctionImpl] | None = None):
        # Project fn/ overrides (highest priority) — empty until the .fn
        # loader exists; kept as a constructor param so callers/tests can
        # inject them ahead of that.
        self._project_functions = project_functions or {}

    def resolve(self, name: str) -> FunctionImpl:
        if name in self._project_functions:
            return self._project_functions[name]
        if name in _BUILTINS:
            return _BUILTINS[name]
        raise FunctionLinkError(f"no implementation found for function '{name}'")
