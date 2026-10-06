"""Shared-folder mode (docs/ARCHITECTURE.md, §Shared-folder mode): a project in a folder that a sync
client (OneDrive, SharePoint, ...) keeps. The sync does not merge: of two writers one wins, or a
conflict copy (`file-PC.yaml`) appears. So the tool merges, with the engine of M6.3a:

- a **base per user**: the last version of each mapping (`.fn.yaml`) and function file (`.fn`) this
  user's tool has seen, kept outside the synced folder (`$J2JME_BASE_DIR`, the app's config);
- `prepare` / `settle`: before saving, if the file on disk is no longer the base (somebody else's
  version arrived), the three-way merge of base, disk and what is being saved; a clean merge is the
  text to save, a real conflict is listed item by item for the user to choose;
- `scan`: the files that changed on disk, and the conflict copies the sync made;
- `merge_copy` / `settle_copy`: a conflict copy merged into its original, then removed.

Files are written whole (`transpiler.atomic`: temporary file and rename), so the sync never uploads half.
Nothing here needs git.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from cli import merge_items
from transpiler.atomic import write_atomic

BASE_ENV = "J2JME_BASE_DIR"
FOLDERS = (("mappings/functional", ".fn.yaml"), ("fn", ".fn"))

# how the sync clients name a copy: OneDrive `name-PCNAME`, `name (1)`; Dropbox `name (X's conflicted
# copy 2026-01-01)`; Google Drive `name (1)`; Syncthing `name.sync-conflict-DATE-ID`
_COPY = re.compile(
    r"^(?P<stem>.+?)(?:-[^-.\s]+| \(\d+\)| \([^)]*conflicted copy[^)]*\)|\.sync-conflict-[\w-]+)$"
)


def base_dir() -> Path | None:
    value = os.environ.get(BASE_ENV)
    return Path(value) if value else None


def authored(project: Path) -> list[str]:
    """The files that are merged, relative to the project, with `/`."""
    return [
        f"{folder}/{p.name}"
        for folder, suffix in FOLDERS
        for p in sorted((project / folder).glob(f"*{suffix}"))
        if p.is_file()
    ]


def _base_file(rel: str) -> Path | None:
    root = base_dir()
    return root / rel if root else None


def base_text(rel: str) -> str | None:
    """The version of `rel` this user last saw; None if there is none (or no base folder)."""
    path = _base_file(rel)
    return path.read_text(encoding="utf-8") if path and path.is_file() else None


def seen(project: Path, rel: str) -> None:
    """The file on disk is now the version this user has seen (read or saved). Quiet without a
    base folder, which is every project that is not in a synced folder."""
    path = _base_file(rel)
    source = project / rel
    if path is None:
        return
    if source.is_file():
        write_atomic(path, source.read_text(encoding="utf-8"))
    else:
        path.unlink(missing_ok=True)


def _disk(project: Path, rel: str) -> str | None:
    path = project / rel
    return path.read_text(encoding="utf-8") if path.is_file() else None


def prepare(project: Path, rel: str, mine: str) -> dict[str, Any]:
    """Before saving `mine` as `rel`. `state`: `same` (the disk is what this user last saw, or
    there is no base: save as is), `merged` (the disk changed and both edits fit: `text` is what to
    save), or `conflict` (`kind`, `items`: what both changed, to settle with `settle`)."""
    base, disk = base_text(rel), _disk(project, rel)
    if base is None or disk is None or disk in (base, mine):
        return {"state": "same"}
    kind, found = merge_items.items(rel, base, disk, mine)
    if kind == "text":
        return {"state": "conflict", "kind": "text", "items": [], "disk": disk}
    if found:
        return {"state": "conflict", "kind": kind, "items": found}
    return {"state": "merged", "text": merge_items.settle(rel, base, disk, mine, {})}


def settle(project: Path, rel: str, mine: str, choices: dict[str, str]) -> dict[str, Any]:
    """The merge of `prepare` once the user chose (path -> `mine` | `remote`) for every item."""
    base, disk = base_text(rel) or "", _disk(project, rel) or ""
    return {"state": "merged", "text": merge_items.settle(rel, base, disk, mine, choices)}


def original_of(project: Path, rel: str) -> str | None:
    """If `rel` is a conflict copy of a file next to it, that file."""
    folder, _, name = rel.rpartition("/")
    for suffix in (s for f, s in FOLDERS if f == folder):
        if not name.endswith(suffix):
            continue
        found = _COPY.match(name.removesuffix(suffix))
        if not found:
            return None
        stem = found.group("stem")
        # `a-b-PC`: the original may be `a-b`, or (a name with a dash) `a`; the longest first
        for cut in sorted({m.start() for m in re.finditer(r"-", stem)} | {len(stem)}, reverse=True):
            candidate = f"{folder}/{stem[:cut]}{suffix}"
            if (project / candidate).is_file() and candidate != rel:
                return candidate
    return None


def scan(project: Path) -> dict[str, Any]:
    """`changed`: files whose disk version is no longer the one this user saw; `copies`: conflict
    copies the sync made, `{copy, original}`."""
    changed, copies = [], []
    for rel in authored(project):
        original = original_of(project, rel)
        if original:
            copies.append({"copy": rel, "original": original})
            continue
        base = base_text(rel)
        if base is not None and base != _disk(project, rel):
            changed.append(rel)
    return {"changed": changed, "copies": copies}


def merge_copy(project: Path, copy: str) -> dict[str, Any]:
    """The conflict copy `copy` merged into its original: both are edits of the version this user
    saw (the base), the original is *mine* and the copy *remote*. Same answer as `prepare`."""
    original = original_of(project, copy)
    if original is None:
        raise ValueError(f"{copy} is not a conflict copy of a file of the project")
    base = base_text(original) or ""
    mine, theirs = _disk(project, original) or "", _disk(project, copy) or ""
    kind, found = merge_items.items(original, base, theirs, mine)
    if kind == "text":
        return {"state": "conflict", "kind": "text", "items": [], "original": original}
    if found:
        return {"state": "conflict", "kind": kind, "items": found, "original": original}
    return {
        "state": "merged",
        "original": original,
        "text": merge_items.settle(original, base, theirs, mine, {}),
    }


def settle_copy(project: Path, copy: str, choices: dict[str, str]) -> dict[str, Any]:
    """Write the merged original, remove the copy, and take the result as seen."""
    original = original_of(project, copy)
    if original is None:
        raise ValueError(f"{copy} is not a conflict copy of a file of the project")
    base = base_text(original) or ""
    mine, theirs = _disk(project, original) or "", _disk(project, copy) or ""
    text = merge_items.settle(original, base, theirs, mine, choices)
    write_atomic(project / original, text)
    (project / copy).unlink()
    seen(project, original)
    return {"state": "merged", "original": original, "text": text}


def discard_copy(project: Path, copy: str) -> None:
    """Throw a conflict copy away (the user keeps the original as it is)."""
    if original_of(project, copy) is None:
        raise ValueError(f"{copy} is not a conflict copy of a file of the project")
    (project / copy).unlink()
