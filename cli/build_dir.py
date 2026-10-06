"""Where the build writes (docs/ARCHITECTURE.md, §Build folder): `build/` of the project, or a local
folder when the project is in a synced folder, which nothing generated may be written to."""

from __future__ import annotations

import os
from pathlib import Path

BUILD_ENV = "J2JME_BUILD_DIR"


def relocated() -> bool:
    """The build goes to the folder in `$J2JME_BUILD_DIR` (the desktop tool sets it, per user and
    per project, never in `mapper.toml`: a path differs on each machine)."""
    return bool(os.environ.get(BUILD_ENV))


def build_root() -> Path:
    return Path(os.environ.get(BUILD_ENV) or "build")


def transpiled_dir() -> Path:
    return build_root() / "transpiled"


def cache_dir() -> Path:
    return build_root() / "cache"


def compiled_dir() -> Path:
    return build_root() / "compiled"


def generated_dir() -> Path:
    """The IDE stubs and dataclasses: `generated/`, or inside the build folder when it is moved."""
    return build_root() / "generated" if relocated() else Path("generated")
