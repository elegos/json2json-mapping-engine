"""The `.fn.yaml` git merge driver (docs/ARCHITECTURE.md, §The merge engine): `mapper merge-driver`
is what git runs for `*.fn.yaml merge=j2jme`, `mapper merge-driver-install` sets it up."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from transpiler.merge import MergeError, merge_fn_texts, merge_texts, text_merge

DRIVER = "j2jme"
ATTRIBUTES = (f"*.fn.yaml merge={DRIVER}", f"*.fn merge={DRIVER}")


def run_driver(base: Path, ours: Path, theirs: Path, name: str = "") -> tuple[bool, str]:
    """Merge `theirs` into `ours` (the file is rewritten in place, as git expects). `name` is the
    file's path in the tree: `*.fn` is a Python file of project functions, merged function by
    function, anything else a `.fn.yaml`. Returns `(clean, message)`. A rule- or function-level
    merge when the files parse and nothing was changed on both sides; otherwise the standard line
    merge, with conflict markers, which is not clean."""
    b, o, t = (p.read_text() for p in (base, ours, theirs))
    note = ""
    merge = merge_fn_texts if name.endswith(".fn") else merge_texts
    try:
        text, conflicts = merge(b, o, t)
    except MergeError as exc:
        text, conflicts, note = "", [], f"{exc}; text-level merge"
    if text and not conflicts:
        ours.write_text(text)
        return True, ""
    if conflicts:
        note = "conflicts on " + ", ".join(c.path for c in conflicts) + "; text-level merge"
    try:
        merged, clean = text_merge(b, o, t)
    except MergeError as exc:
        return False, f"{note}: {exc}" if note else str(exc)
    ours.write_text(merged)
    return clean, note


def app_driver_line(python: str | None = None, engine: str | None = None) -> str:
    """The command git runs for the driver, for the tool: this very interpreter and engine
    (`mapper` is not in the PATH of an app that brings its own Python). If that interpreter is
    gone (an AppImage mounts somewhere else every time, an app was uninstalled) the shell says 126
    or 127 and git's own line merge takes over, so a merge from a terminal still works, with the
    conflict markers git would have made."""
    interpreter = Path(python or sys.executable).as_posix()
    root = engine or Path(__file__).resolve().parent.parent.as_posix()
    run = (
        f"PYTHONPATH={shlex.quote(root)} PYTHONUTF8=1 PYTHONNOUSERSITE=1 "
        f"{shlex.quote(interpreter)} -m cli.main merge-driver %O %A %B %P"
    )
    fallback = "git merge-file -L ours -L base -L theirs %A %O %B"
    return (
        f"{run}; rc=$?; if [ $rc -eq 126 ] || [ $rc -eq 127 ]; then {fallback}; rc=$?; fi; exit $rc"
    )


def _config(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(project), "config", "--local", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MergeError("git is not installed") from exc


def ensure(project: Path, line: str | None = None) -> dict[str, bool]:
    """Make sure the clone merges `*.fn.yaml` and `*.fn` with the driver, quietly: nobody who
    edits mappings should have to know about it. Writes the driver's command into the repository's
    local git config (it does not travel with the repository, so every clone needs it, and the
    command names this install, so it is rewritten when it differs) and the attributes into the
    project's `.gitattributes` (those travel with the repository). Does nothing outside a git
    repository or without git. Returns `{installed, changed}`."""
    wanted = line or app_driver_line()
    try:
        inside = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return {"installed": False, "changed": False}
    if inside.returncode != 0:
        return {"installed": False, "changed": False}
    current = _config(project, "--get", f"merge.{DRIVER}.driver").stdout.strip()
    attrs = project / ".gitattributes"
    present = set(attrs.read_text().splitlines()) if attrs.is_file() else set()
    if current == wanted and all(a in present for a in ATTRIBUTES):
        return {"installed": True, "changed": False}
    install(project, driver=wanted)
    return {"installed": True, "changed": True}


def install(project: Path, command: str = "mapper", driver: str | None = None) -> list[str]:
    """Register the driver in the repository's git config and the attribute in the project's
    `.gitattributes`. The config is local to the clone, so every clone does this once. `driver` is
    the whole command line, else `<command> merge-driver %O %A %B %P`. The attributes are written
    in the project's folder, so they apply there and not to the rest of a bigger repository.
    Returns what was done."""
    done: list[str] = []
    for key, value in (
        (f"merge.{DRIVER}.name", "J2JME rule-level merge of .fn.yaml"),
        (f"merge.{DRIVER}.driver", driver or f"{command} merge-driver %O %A %B %P"),
    ):
        try:
            subprocess.run(
                ["git", "-C", str(project), "config", "--local", key, value],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise MergeError("git is not installed") from exc
        except subprocess.CalledProcessError as exc:
            raise MergeError(f"git config {key}: {exc.stderr.strip()}") from exc
        done.append(f"git config {key}")
    attrs = project / ".gitattributes"
    text = attrs.read_text() if attrs.is_file() else ""
    for attribute in ATTRIBUTES:
        if attribute not in text.splitlines():
            text += ("" if not text or text.endswith("\n") else "\n") + attribute + "\n"
            attrs.write_text(text)
            done.append(f"{attrs.name}: {attribute}")
    return done
