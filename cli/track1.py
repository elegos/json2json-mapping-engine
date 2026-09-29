"""Track 1 — runtime-free unit tests (see docs/ARCHITECTURE.md, §Testing).

A project's own `tests/track1/` suite (transpiler snapshots, compiler golden
files), run through pytest so `mapper test --track 1` is one entry point.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TRACK1_DIR = Path("tests/track1")


def run_track1(extra_args: list[str] | None = None) -> int | None:
    """Exit code of pytest, or None if the project has no Track 1 suite."""
    if not TRACK1_DIR.is_dir():
        return None
    cmd = [sys.executable, "-m", "pytest", str(TRACK1_DIR), *(extra_args or [])]
    return subprocess.run(cmd).returncode
