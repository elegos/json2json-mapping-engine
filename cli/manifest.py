"""`build/compiled/manifest.json` (docs/ARCHITECTURE.md, §Build folder and incremental compilation):
what produced the artifacts. The output is deterministic only for the same sources **and** the same
engine version, so the manifest records both: the engine version, the hash of each source (the
mappings, the schemas, the shared lookups, the project's `fn/*.fn`, `mapper.toml`) and of each
output. No date, no machine: building twice from the same sources gives the same file, so it can be
committed and compared in CI."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from cli._version import ENGINE_VERSION
from cli.config import CONFIG_FILENAME

MANIFEST_NAME = "manifest.json"
FORMAT = 1

# where the sources of a project are, relative to its root
SOURCE_GLOBS = (
    CONFIG_FILENAME,
    "mappings/*.map.py",
    "mappings/functional/*.fn.yaml",
    "schemas/**/*.json",
    "lookups/*.lookup.yaml",
    "fn/*.fn",
)


def digest(data: bytes | str) -> str:
    """SHA-256 of a text, with CRLF read as LF (a checkout on Windows must hash the same)."""
    raw = data.encode() if isinstance(data, str) else data
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def source_hashes(root: Path = Path()) -> dict[str, str]:
    """Hash of each source file that exists, by its path (with `/`) relative to `root`."""
    found: dict[str, str] = {}
    for pattern in SOURCE_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                found[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    return dict(sorted(found.items()))


def build_manifest(target: str, files: dict[str, str], root: Path = Path()) -> dict:
    """The manifest of artifacts `files` (name -> text) built for `target` from the sources."""
    return {
        "manifest": FORMAT,
        "engine": ENGINE_VERSION,
        "target": target,
        "sources": source_hashes(root),
        "outputs": {name: digest(text) for name, text in sorted(files.items())},
    }


def manifest_text(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def read_manifest(folder: Path) -> dict | None:
    """The manifest in `folder`; None if there is none or it is not readable."""
    try:
        data = json.loads((folder / MANIFEST_NAME).read_text())
    except OSError, ValueError:
        return None
    return data if isinstance(data, dict) else None


def artifacts_ignored(folder: Path) -> bool:
    """Whether git ignores the artifacts folder (the project builds them in CI instead of
    committing them). False when git is not there or this is not a repository."""
    try:
        done = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", str(folder / MANIFEST_NAME)],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return done.returncode == 0


def compare(committed: dict | None, fresh: dict) -> tuple[list[str], list[str]]:
    """What differs between the manifest on disk and the one the current sources give, as
    `(problems, warnings)`. A different set of sources or outputs is a problem: the artifacts were
    not built from these sources. A different engine version alone is a warning: the outputs are
    what decides whether the artifacts are stale."""
    if committed is None:
        return [f"missing or unreadable: {MANIFEST_NAME}"], []
    problems: list[str] = []
    for key, what in (("sources", "source"), ("outputs", "output")):
        old, new = committed.get(key) or {}, fresh[key]
        problems += [f"manifest: {what} {n} is not in it" for n in sorted(new.keys() - old.keys())]
        problems += [f"manifest: {what} {n} is gone" for n in sorted(old.keys() - new.keys())]
        problems += [
            f"manifest: {what} {n} changed"
            for n in sorted(new.keys() & old.keys())
            if old[n] != new[n]
        ]
    if committed.get("target") != fresh["target"]:
        problems.append(f"manifest: target is {committed.get('target')!r}, not {fresh['target']!r}")
    warnings = []
    if committed.get("engine") != fresh["engine"]:
        warnings.append(
            f"built by engine {committed.get('engine')}, this one is {fresh['engine']}"
            " (the outputs decide whether they are stale)"
        )
    return problems, warnings
