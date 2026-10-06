"""Who is editing which mapping, in a project in a synced folder (docs/ARCHITECTURE.md,
§Shared-folder mode, Presence). Advisory: nothing is locked, and a stale or missing file only means
the tool does not know.

One file per user and machine, `.j2jme/presence/<mapping>.<user>@<host>.json`, written by that tool
alone, so the sync never has two writers on it (no conflict copies). A tool that is editing a mapping
rewrites its file every half minute; a file older than `TTL` is a tool that closed or crashed. The
sync's own delay is the other margin: the list is what the folder showed a moment ago.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import socket
import time
from pathlib import Path
from typing import Any

from transpiler.atomic import write_atomic

FOLDER = ".j2jme/presence"
TTL = 120  # seconds; the tool beats every 30
USER_ENV = "J2JME_USER"


def identity() -> str:
    """`user@host` of this tool: the OS user (or `$J2JME_USER`) and the machine."""
    user = os.environ.get(USER_ENV) or _safe(getpass.getuser)
    return f"{user}@{_safe(socket.gethostname)}"


def _safe(source: Any) -> str:
    try:
        return re.sub(r"[^\w.-]+", "_", str(source())) or "unknown"
    except KeyError, OSError:
        return "unknown"


def _folder(project: Path) -> Path:
    return project / FOLDER


def _mine(project: Path) -> list[Path]:
    return sorted(_folder(project).glob(f"*.{identity()}.json"))


def announce(project: Path, mapping: str | None) -> None:
    """This tool is editing `mapping` now (None: none). It is one mapping at a time, so the files
    of the others go."""
    keep = _folder(project) / f"{mapping}.{identity()}.json" if mapping else None
    for old in _mine(project):
        if old != keep:
            old.unlink(missing_ok=True)
    if keep is not None:
        record = {"mapping": mapping, "user": identity(), "at": time.time()}
        write_atomic(keep, json.dumps(record))


def others(project: Path, now: float | None = None) -> list[dict[str, Any]]:
    """Who else is editing: `{mapping, user, age}` of every fresh file that is not this tool's.
    A file that cannot be read is skipped (the sync may be halfway through it)."""
    moment = time.time() if now is None else now
    found = []
    for path in sorted(_folder(project).glob("*.json")):
        if path.name.endswith(f".{identity()}.json"):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            age = moment - float(record["at"])
            found.append(
                {"mapping": str(record["mapping"]), "user": str(record["user"]), "age": age}
            )
        except OSError, ValueError, KeyError, TypeError:
            continue
    return [f for f in found if f["age"] < TTL]
