"""packaging/release.py: the version and the notes a release takes from its tag."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "packaging" / "release.py"
spec = importlib.util.spec_from_file_location("release_script", SCRIPT)
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

CHANGELOG = """\
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Something not released yet.

## [1.2.3] - 2026-10-05

### Fixed
- The thing.

## [1.2.3-beta1] - 2026-10-01

### Added
- The beta.

## 1.0.0

- Plain heading, no brackets.

[Unreleased]: https://example.org/compare/v1.2.3...HEAD
[1.2.3]: https://example.org/compare/v1.0.0...v1.2.3
"""


@pytest.mark.parametrize(
    ("tag", "version", "pre"),
    [
        ("v1.2.3", "1.2.3", False),
        ("v10.0.0", "10.0.0", False),
        ("v1.2.3-beta1", "1.2.3-beta1", True),
        ("v1.2.3-rc.1", "1.2.3-rc.1", True),
    ],
)
def test_a_tag_names_a_version_and_whether_it_is_a_pre_release(tag, version, pre) -> None:
    assert release.parse_tag(tag) == (version, pre)


@pytest.mark.parametrize(
    "tag", ["1.2.3", "v1.2", "v1.2.3.4", "v01.2.3", "v1.2.3-", "v1.2.3+meta", "vx"]
)
def test_a_tag_that_is_not_semver_is_refused(tag) -> None:
    with pytest.raises(ValueError, match="not vMAJOR"):
        release.parse_tag(tag)


def test_the_package_version_is_replaced_and_nothing_else() -> None:
    toml = '[package]\nname = "x"\nversion = "0.1.0"\n\n[dependencies]\ntauri = { version = "2" }\nserde = "1"\n'
    out = release.set_cargo_version(toml, "1.2.3-beta1")
    assert 'version = "1.2.3-beta1"' in out and 'name = "x"' in out
    assert 'tauri = { version = "2" }' in out and out.count("0.1.0") == 0
    lock = 'name = "other"\nversion = "0.1.0"\n\n[[package]]\nname = "j2jme-desktop"\nversion = "0.1.0"\n'
    out = release.set_lock_version(lock, "j2jme-desktop", "1.2.3")
    assert out.endswith('name = "j2jme-desktop"\nversion = "1.2.3"\n')
    assert out.startswith('name = "other"\nversion = "0.1.0"')


def test_the_notes_are_the_section_of_the_version() -> None:
    notes = release.release_notes(CHANGELOG, "1.2.3")
    assert notes == "### Fixed\n- The thing."  # not the link definitions at the foot of the file
    assert release.release_notes(CHANGELOG, "1.2.3-beta1") == "### Added\n- The beta."
    assert release.release_notes(CHANGELOG, "1.0.0") == "- Plain heading, no brackets."


def test_without_a_section_of_its_own_the_unreleased_one_is_used() -> None:
    assert release.release_notes(CHANGELOG, "2.0.0") == "### Added\n- Something not released yet."


def test_without_either_there_is_nothing() -> None:
    assert release.release_notes("# Changelog\n\n## [1.0.0] - 2026-01-01\n\n- x\n", "2.0.0") == ""
    assert release.release_notes("", "1.0.0") == ""


def test_prepare_writes_the_version_and_the_notes(tmp_path, monkeypatch) -> None:
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text('[package]\nname = "j2jme-desktop"\nversion = "0.1.0"\n')
    lock = tmp_path / "Cargo.lock"
    lock.write_text('[[package]]\nname = "j2jme-desktop"\nversion = "0.1.0"\n')
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG)
    monkeypatch.setattr(release, "CARGO_TOML", cargo)
    monkeypatch.setattr(release, "CARGO_LOCK", lock)
    monkeypatch.setattr(release, "CHANGELOG", changelog)
    notes = tmp_path / "notes.md"

    lines = release.prepare("v1.2.3-beta1", notes)

    assert lines == ["J2JME_VERSION=1.2.3-beta1", "J2JME_PRERELEASE=true"]
    assert 'version = "1.2.3-beta1"' in cargo.read_text()
    assert 'version = "1.2.3-beta1"' in lock.read_text()
    assert notes.read_text() == "### Added\n- The beta.\n"

    assert release.prepare("v3.0.0", notes)[1] == "J2JME_PRERELEASE=false"
    assert notes.read_text().startswith("### Added\n- Something not released yet")

    changelog.unlink()
    release.prepare("v3.0.0", notes)
    assert notes.read_text() == ""  # the last resort: a release without a description
