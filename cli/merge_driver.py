"""The `.fn.yaml` git merge driver (docs/ARCHITECTURE.md, §The merge engine): `mapper merge-driver`
is what git runs for `*.fn.yaml merge=j2jme`, `mapper merge-driver-install` sets it up."""

from __future__ import annotations

import subprocess
from pathlib import Path

from transpiler.merge import MergeError, merge_texts, text_merge

DRIVER = "j2jme"
ATTRIBUTE = f"*.fn.yaml merge={DRIVER}"


def run_driver(base: Path, ours: Path, theirs: Path) -> tuple[bool, str]:
    """Merge `theirs` into `ours` (the file is rewritten in place, as git expects). Returns
    `(clean, message)`. A rule-level merge when the files are YAML and no rule field was changed
    on both sides; otherwise the standard line merge, with conflict markers, which is not clean."""
    b, o, t = (p.read_text() for p in (base, ours, theirs))
    note = ""
    try:
        text, conflicts = merge_texts(b, o, t)
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


def install(project: Path, command: str = "mapper") -> list[str]:
    """Register the driver in the repository's git config and the attribute in the project's
    `.gitattributes`. The config is local to the clone, so every clone does this once. Returns
    what was done."""
    done: list[str] = []
    for key, value in (
        (f"merge.{DRIVER}.name", "J2JME rule-level merge of .fn.yaml"),
        (f"merge.{DRIVER}.driver", f"{command} merge-driver %O %A %B %P"),
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
    if ATTRIBUTE not in text.splitlines():
        attrs.write_text(
            text + ("" if not text or text.endswith("\n") else "\n") + ATTRIBUTE + "\n"
        )
        done.append(f"{attrs.name}: {ATTRIBUTE}")
    return done
