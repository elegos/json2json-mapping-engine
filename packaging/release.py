"""What a release build takes from its tag (used by the release workflows).

    python packaging/release.py prepare v1.2.3-beta1 --notes notes.md >> "$GITHUB_ENV"

- the version is the tag without its `v`, and replaces the one in `desktop/src-tauri/Cargo.toml`
  (and its entry in `Cargo.lock`) and the engine's in `cli/_version.py` for this build;
- a tag with a suffix (`v1.2.3-beta1`) is a pre-release;
- the notes are the section of CHANGELOG.md (Keep a Changelog 1.1.0) of that version, else its
  `Unreleased` section, else nothing: the notes file is then empty.

Standard library only: it runs in the bare job container.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARGO_TOML = ROOT / "desktop" / "src-tauri" / "Cargo.toml"
CARGO_LOCK = ROOT / "desktop" / "src-tauri" / "Cargo.lock"
ENGINE_VERSION_FILE = ROOT / "cli" / "_version.py"
CHANGELOG = ROOT / "CHANGELOG.md"

# v1.2.3, v1.2.3-beta1, v1.2.3-rc.1: semantic versioning, without build metadata
_TAG = re.compile(
    r"^v(?P<version>(?P<core>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?)$"
)


def parse_tag(tag: str) -> tuple[str, bool]:
    """The version a tag names, and whether it is a pre-release."""
    found = _TAG.match(tag)
    if not found:
        raise ValueError(f"tag {tag!r} is not vMAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH-suffix")
    return found["version"], found["pre"] is not None


def set_cargo_version(cargo_toml: str, version: str) -> str:
    """`Cargo.toml` with the `[package]` version replaced."""
    table = re.search(r"^\[package\]\s*$", cargo_toml, re.MULTILINE)
    if not table:
        raise ValueError("no [package] table in Cargo.toml")
    line = re.compile(r'^version\s*=\s*".*"\s*$', re.MULTILINE).search(cargo_toml, table.end())
    if not line:
        raise ValueError("no version in the [package] table of Cargo.toml")
    return f'{cargo_toml[: line.start()]}version = "{version}"{cargo_toml[line.end() :]}'


def set_engine_version(source: str, version: str) -> str:
    """`cli/_version.py` with `ENGINE_VERSION` replaced (what `mapper version` prints and the
    manifest of the build artifacts records)."""
    line = re.compile(r'^ENGINE_VERSION[ \t]*=[ \t]*".*"[ \t]*$', re.MULTILINE).search(source)
    if line is None:
        raise ValueError("no ENGINE_VERSION in cli/_version.py")
    return f'{source[: line.start()]}ENGINE_VERSION = "{version}"{source[line.end() :]}'


def set_lock_version(cargo_lock: str, package: str, version: str) -> str:
    """`Cargo.lock` with the version of the workspace's own package replaced."""
    entry = re.compile(rf'(^name = "{re.escape(package)}"\nversion = ")[^"]*(")', re.MULTILINE)
    return entry.sub(rf"\g<1>{version}\g<2>", cargo_lock, count=1)


# `## [1.2.3] - 2026-10-05`, `## 1.2.3`, `## [Unreleased]`, `## [1.2.3] - 2026-10-05 [YANKED]`
_HEADING = re.compile(r"^##[ \t]+\[?(?P<name>[^\]\s]+)\]?(?:[ \t].*)?$")
# the link definitions Keep a Changelog puts at the foot of the file: `[1.2.3]: https://…`
_LINK_DEFINITION = re.compile(r"^\[[^\]]+\]:[ \t]+\S")


def _sections(changelog: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in changelog.splitlines():
        heading = _HEADING.match(line)
        if heading:
            current = sections.setdefault(heading["name"].lstrip("v").lower(), [])
        elif current is not None:
            current.append(line)
    return {name: _body(lines) for name, lines in sections.items()}


def _body(lines: list[str]) -> str:
    while lines and (not lines[-1].strip() or _LINK_DEFINITION.match(lines[-1])):
        lines = lines[:-1]
    return "\n".join(lines).strip("\n")


def release_notes(changelog: str, version: str) -> str:
    """The section of `version`; else `Unreleased`; else an empty text."""
    sections = _sections(changelog)
    return sections.get(version.lower()) or sections.get("unreleased") or ""


def prepare(tag: str, notes: Path | None) -> list[str]:
    version, prerelease = parse_tag(tag)
    CARGO_TOML.write_text(set_cargo_version(CARGO_TOML.read_text(), version))
    ENGINE_VERSION_FILE.write_text(set_engine_version(ENGINE_VERSION_FILE.read_text(), version))
    if CARGO_LOCK.exists():
        CARGO_LOCK.write_text(set_lock_version(CARGO_LOCK.read_text(), "j2jme-desktop", version))
    text = release_notes(CHANGELOG.read_text(), version) if CHANGELOG.exists() else ""
    if notes:
        notes.write_text(text + "\n" if text else "")
    return [
        f"J2JME_VERSION={version}",
        f"J2JME_PRERELEASE={'true' if prerelease else 'false'}",
    ]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("prepare", help="apply the tag's version, write the notes")
    one.add_argument("tag")
    one.add_argument("--notes", type=Path, help="where to write the release notes")
    args = parser.parse_args(argv)
    try:
        for line in prepare(args.tag, args.notes):
            print(line)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
