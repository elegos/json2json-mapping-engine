"""Is a project in a folder that a sync client keeps (OneDrive, SharePoint, Dropbox, ...)?

Nothing generated may be written there (the sync would upload the build, and every user would
overwrite everybody's), and a git repository there is not supported (the sync corrupts `.git`).
Detection goes by the path alone: the sync clients leave no marker the tool can rely on, so the
user can always say a folder is, or is not, a synced one (the desktop tool keeps that choice).
"""

from __future__ import annotations

import os
from pathlib import Path

from cli.build_dir import BUILD_ENV

# a path component that gives the provider away: (prefix or word, what the user knows it as)
_COMPONENTS = (
    ("onedrive", "OneDrive"),
    ("sharepoint", "SharePoint"),
    ("dropbox", "Dropbox"),
    ("google drive", "Google Drive"),
    ("googledrive", "Google Drive"),
    ("icloud drive", "iCloud Drive"),
    ("com~apple~clouddocs", "iCloud Drive"),
    ("box sync", "Box"),
)
_ENV = ("OneDrive", "OneDriveCommercial", "OneDriveConsumer")


def provider(path: Path) -> str | None:
    """The sync provider `path` is under, by the sync folders the environment names and by the
    names of the folders on the way; None when it looks like an ordinary folder."""
    full = path.resolve()
    for var in _ENV:
        root = os.environ.get(var)
        if root and _under(full, Path(root)):
            return "SharePoint" if "sharepoint" in str(full).lower() else "OneDrive"
    parts = [p.lower() for p in full.parts]
    for i, part in enumerate(parts):
        if part == "cloudstorage" and i + 1 < len(
            parts
        ):  # macOS: ~/Library/CloudStorage/<Provider-...>
            part = parts[i + 1]
        for needle, name in _COMPONENTS:
            if part.startswith(needle) or (needle == "sharepoint" and needle in part):
                return name
    return None


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return False
    return True


def git_inside(project: Path) -> Path | None:
    """The folder holding the `.git` the project belongs to, if any (the project's own, or a
    bigger repository's above it)."""
    for folder in (project.resolve(), *project.resolve().parents):
        if (folder / ".git").exists():
            return folder
    return None


def status(project: Path) -> dict[str, object]:
    """`synced`: the provider or None; `git`: a repository in a synced folder (not supported)."""
    found = provider(project)
    repo = git_inside(project) if found else None
    return {"synced": found, "git": str(repo) if repo else None}


ALLOW_ENV = "J2JME_ALLOW_SYNCED"


def refusal(project: Path) -> str | None:
    """Why a build must not write in `project`: it is in a synced folder and the build has not
    been moved out of it (`$J2JME_BUILD_DIR`), nor the folder declared an ordinary one
    (`$J2JME_ALLOW_SYNCED=1`, for a name that only looks like a sync folder). None: go ahead."""
    if os.environ.get(BUILD_ENV) or os.environ.get(ALLOW_ENV):
        return None
    found = provider(project)
    if found is None:
        return None
    return (
        f"this project is in a {found} folder, and nothing generated may be written there: set "
        f"{BUILD_ENV} to a folder on this machine, or {ALLOW_ENV}=1 if it is not a synced folder"
    )
