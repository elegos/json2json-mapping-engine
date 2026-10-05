"""`mapper publish` (docs/ARCHITECTURE.md, §Build CLI): the generated files, with their
`manifest.json`, written to the publish directory so that whoever reads that folder (a deploy job,
a SharePoint library, another team's project) gets a complete, verifiable set.

The folder may not be ours (a "guest" project, a synced library), so it is never replaced or
emptied: only the files the previous manifest listed are ever removed. A reader tells a finished
set by the manifest, which is removed first and written last, and checks each file against the hash
it lists."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from cli.config import MapperConfig
from cli.manifest import MANIFEST_NAME, digest, manifest_text, read_manifest

ENV_DIR = "J2JME_PUBLISH_DIR"


class PublishError(Exception):
    """The set could not be published (the folder is not writable, a file did not read back)."""


def publish_dir(config: MapperConfig, to: str | None, default: Path, root: Path = Path()) -> Path:
    """Where to publish: `--to`, else `J2JME_PUBLISH_DIR` (a per-user choice), else `[publish]
    dir` of mapper.toml, else `default` (where the build writes). A relative path is relative to
    the project's root."""
    chosen = to or os.environ.get(ENV_DIR) or config.publish.dir
    if not chosen:
        return default
    path = Path(chosen).expanduser()
    return path if path.is_absolute() else root / path


def _write_atomically(path: Path, text: str) -> None:
    """The file appears whole or not at all (a sync client or a reader never sees half of it)."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def publish(files: dict[str, str], manifest: dict, folder: Path) -> list[Path]:
    """Write `files` (name -> text, in deploy order) and `manifest` to `folder`. Returns what was
    written. Order: the old manifest goes (the set is unfinished), the files are written and read
    back against the hashes of `manifest`, the files only the old manifest listed go, the new
    manifest is written."""
    for name, text in files.items():
        if manifest["outputs"].get(name) != digest(text):
            raise PublishError(f"{name} is not what the manifest says it is")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        old = read_manifest(folder)
        (folder / MANIFEST_NAME).unlink(missing_ok=True)
        written: list[Path] = []
        for name, text in files.items():
            target = folder / name
            _write_atomically(target, text)
            if digest(target.read_text(encoding="utf-8")) != manifest["outputs"][name]:
                raise PublishError(f"{target} did not read back as written")
            written.append(target)
        for name in sorted(set((old or {}).get("outputs", {})) - set(files)):
            if (
                Path(name).name == name
            ):  # a manifest of someone else's cannot reach out of the folder
                (folder / name).unlink(missing_ok=True)
        _write_atomically(folder / MANIFEST_NAME, manifest_text(manifest))
    except OSError as exc:
        raise PublishError(f"cannot write to {folder}: {exc.strerror or exc}") from exc
    return [*written, folder / MANIFEST_NAME]


def verify_folder(folder: Path) -> tuple[list[str], int]:
    """What is wrong with a published folder, and how many files it lists: no manifest
    (unfinished, or never published), a file it lists missing or changed. Empty when the set is
    complete."""
    manifest = read_manifest(folder)
    if manifest is None:
        return [f"no readable {MANIFEST_NAME} in {folder}: not published, or being published"], 0
    outputs = manifest.get("outputs", {})
    problems = []
    for name, wanted in outputs.items():
        if Path(name).name != name:  # a manifest cannot point outside its folder
            problems.append(f"{name}: not a file name")
            continue
        try:
            if digest((folder / name).read_bytes()) != wanted:
                problems.append(f"{name} changed since it was published")
        except OSError:
            problems.append(f"{name} is missing")
    return problems, len(outputs)


def verify(folder: Path) -> list[str]:
    """The problems of `verify_folder`."""
    return verify_folder(folder)[0]
