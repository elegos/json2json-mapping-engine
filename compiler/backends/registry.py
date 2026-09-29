"""Backend registry (docs/ARCHITECTURE.md, §Target backends).

Self-maintaining: every module under `compiler.backends` is imported and each
concrete `Backend` subclass is registered under its `target` attribute. A new
target is a new subpackage (e.g. `compiler/backends/go/`) with a `Backend`
subclass that sets `target = "go"` — nothing to register by hand.

A project may add or override backends with its own `compiler/backends/`
folder (relative to the working directory, i.e. the project root). Its modules
are discovered the same way; a project backend whose `target` equals a
built-in one replaces it. Two backends of the *same* origin claiming one name
are an error. Project backends are project code executed at build time, like
any build script.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
import types
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import compiler.backends as backends_pkg
from compiler.backends.base import Backend, CodeGenError

DEFAULT_TARGET = "plsql"
PROJECT_BACKENDS_DIR = Path("compiler") / "backends"
_PROJECT_PACKAGE = "project_backends"

_cache: dict[Path | None, dict[str, type[Backend]]] = {}


def _collect(path: Iterable[str], prefix: str) -> dict[str, type[Backend]]:
    found: dict[str, type[Backend]] = {}
    for info in pkgutil.walk_packages(path, prefix=prefix):
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


def _project_dir() -> Path | None:
    """The project's own backends folder, if any (and not the built-in one —
    the engine's own checkout has the same relative path)."""
    directory = (Path.cwd() / PROJECT_BACKENDS_DIR).resolve()
    if not directory.is_dir() or directory == Path(backends_pkg.__path__[0]).resolve():
        return None
    return directory


def _load_project(directory: Path) -> dict[str, type[Backend]]:
    package = types.ModuleType(_PROJECT_PACKAGE)
    package.__path__ = [str(directory)]
    sys.modules[_PROJECT_PACKAGE] = package
    for name in [m for m in sys.modules if m.startswith(f"{_PROJECT_PACKAGE}.")]:
        del sys.modules[name]
    return _collect(package.__path__, f"{_PROJECT_PACKAGE}.")


def backends() -> dict[str, type[Backend]]:
    """All available backends: built-ins, overridden by the project's."""
    directory = _project_dir()
    if directory not in _cache:
        found = dict(_collect(backends_pkg.__path__, f"{backends_pkg.__name__}."))
        if directory is not None:
            found.update(_load_project(directory))
        _cache[directory] = found
    return _cache[directory]


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
