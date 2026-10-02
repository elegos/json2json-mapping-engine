"""The functions a mapping can call, for the desktop tool's explorer (op `functions` of
`mapper serve`): the registry's view, built-ins and the project's `fn/*.fn`, as plain data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from compiler.function_registry import FunctionInfo, all_functions, builtin_functions


def _entry(info: FunctionInfo, replaces: bool) -> dict[str, Any]:
    return {
        "name": info.name,
        "signature": info.signature(),
        "params": [
            {
                "name": p.name,
                "annotation": p.annotation,
                "default": p.default,
                "variadic": p.variadic,
            }
            for p in info.params
        ],
        "returns": info.returns,
        "doc": info.doc,
        "origin": info.origin,
        "builtin": info.origin == "built-in",
        "replaces_builtin": replaces,
        "targets": sorted(info.overrides),
    }


def function_list(project: Path | None) -> list[dict[str, Any]]:
    """Every callable function by name; a project function that has a built-in's name is
    marked as replacing it."""
    builtins = builtin_functions()
    return [
        _entry(info, info.origin != "built-in" and name in builtins)
        for name, info in sorted(all_functions(project).items())
    ]
