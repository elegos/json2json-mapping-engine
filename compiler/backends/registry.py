"""Backend registry (docs/ARCHITECTURE.md, §Target backends).

Self-maintaining: every module under `compiler.backends` is imported and each
concrete `Backend` subclass is registered under its `target` attribute. A new
target is a new subpackage (e.g. `compiler/backends/go/`) with a `Backend`
subclass that sets `target = "go"` — nothing to register by hand.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Any

import compiler.backends as backends_pkg
from compiler.backends.base import Backend, CodeGenError

DEFAULT_TARGET = "plsql"

_registry: dict[str, type[Backend]] | None = None


def _discover() -> dict[str, type[Backend]]:
    found: dict[str, type[Backend]] = {}
    for info in pkgutil.walk_packages(backends_pkg.__path__, prefix=f"{backends_pkg.__name__}."):
        module = importlib.import_module(info.name)
        for _name, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, Backend) and not inspect.isabstract(cls) and cls is not Backend:
                target = getattr(cls, "target", None)
                if not target:
                    raise CodeGenError(f"backend {cls.__qualname__} does not set `target`")
                if target in found and found[target] is not cls:
                    raise CodeGenError(
                        f"target {target!r} is claimed by both "
                        f"{found[target].__qualname__} and {cls.__qualname__}"
                    )
                found[target] = cls
    return found


def backends() -> dict[str, type[Backend]]:
    global _registry
    if _registry is None:
        _registry = _discover()
    return _registry


def backend_class(target: str) -> type[Backend]:
    try:
        return backends()[target]
    except KeyError:
        known = ", ".join(sorted(backends())) or "none"
        raise CodeGenError(f"unknown target {target!r} (available: {known})") from None


def create_backend(target: str, config: dict[str, Any] | None = None) -> Backend:
    """`config` = the (validated, defaults-merged) `[target.<name>]` section."""
    cls = backend_class(target)
    return cls({**cls.defaults, **(config or {})})
