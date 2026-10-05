"""packaging/install-mapper.sh: the `mapper` a project's manifest names, from a release."""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "packaging" / "install-mapper.sh"
ASSET = "j2jme-cli-linux-x86_64.tar.gz"

pytestmark = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("sh", "curl", "tar", "sha256sum")),
    reason="needs sh, curl, tar and sha256sum",
)


def _release(releases: Path, version: str, launcher: str | None = None) -> None:
    """A release `v<version>` as a folder: the archive with a `bin/mapper`, and its checksum."""
    folder = releases / f"v{version}"
    folder.mkdir(parents=True)
    body = launcher or f'#!/bin/sh\necho "mapper {version}"\n'
    with tarfile.open(folder / ASSET, "w:gz") as tar:
        data = body.encode()
        info = tarfile.TarInfo("bin/mapper")
        info.size, info.mode = len(data), 0o755
        tar.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256((folder / ASSET).read_bytes()).hexdigest()
    (folder / f"{ASSET}.sha256").write_text(f"{digest}  {ASSET}\n")


def _config(path: Path, version: str) -> Path:
    path.write_text(
        '[optimizer]\nengine = "decoy"\n\n[project]  # the project\nmode = "driven"\n'
        f'engine   = "{version}"   # the tool that last opened it\ntarget = "plsql"\n'
    )
    return path


def _run(tmp_path: Path, *args: str, releases: Path | None = None, **env: str):
    gh_path = tmp_path / "github_path"
    full_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "GITHUB_PATH": str(gh_path),
        **env,
    }
    if releases is not None:
        full_env["J2JME_RELEASES_URL"] = f"file://{releases}"
    return subprocess.run(
        ["sh", str(SCRIPT), *args], capture_output=True, text=True, env=full_env, check=False
    )


def test_installs_the_version_of_mapper_toml_and_adds_it_to_the_path(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    _release(releases, "1.2.3")
    _release(releases, "9.9.9")
    config = _config(tmp_path / "mapper.toml", "1.2.3")
    done = _run(tmp_path, "--config", str(config), "--dir", str(tmp_path / "v"), releases=releases)
    assert done.returncode == 0, done.stderr
    bin_dir = tmp_path / "v" / "1.2.3" / "bin"
    assert (tmp_path / "github_path").read_text() == f"{bin_dir}\n"
    out = subprocess.run([str(bin_dir / "mapper")], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "mapper 1.2.3"
    assert not (tmp_path / "v" / "9.9.9").exists()


def test_a_version_already_installed_is_reused(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    _release(releases, "1.2.3")
    args = ("--version", "1.2.3", "--dir", str(tmp_path / "v"))
    assert _run(tmp_path, *args, releases=releases).returncode == 0
    shutil.rmtree(releases)  # nothing to download from any more
    done = _run(tmp_path, *args)
    assert done.returncode == 0, done.stderr


def test_without_github_path_it_prints_the_line_for_the_path(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    _release(releases, "1.0.0-beta1")
    done = _run(
        tmp_path,
        "--version",
        "1.0.0-beta1",
        "--dir",
        str(tmp_path / "v"),
        releases=releases,
        GITHUB_PATH="",
    )
    assert done.returncode == 0, done.stderr
    assert f'export PATH="{tmp_path}/v/1.0.0-beta1/bin:$PATH"' in done.stdout


def test_a_bad_checksum_installs_nothing(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    _release(releases, "1.2.3")
    (releases / "v1.2.3" / f"{ASSET}.sha256").write_text(f"{'0' * 64}  {ASSET}\n")
    done = _run(tmp_path, "--version", "1.2.3", "--dir", str(tmp_path / "v"), releases=releases)
    assert done.returncode == 1 and "bad checksum" in done.stderr
    assert not (tmp_path / "v" / "1.2.3").exists()


def test_a_missing_release_says_which(tmp_path: Path) -> None:
    (tmp_path / "releases").mkdir()
    done = _run(
        tmp_path, "--version", "4.0.0", "--dir", str(tmp_path / "v"), releases=tmp_path / "releases"
    )
    assert done.returncode == 1 and "release v4.0.0" in done.stderr


def test_the_errors_of_the_input(tmp_path: Path) -> None:
    none = _run(tmp_path, "--config", str(tmp_path / "nope.toml"))
    assert none.returncode == 1 and "no " in none.stderr
    (tmp_path / "m.toml").write_text('[optimizer]\nengine = "1.0.0"\n[project]\nmode = "driven"\n')
    asked = _run(tmp_path, "--config", str(tmp_path / "m.toml")).stderr
    assert "no engine version under [project]" in asked  # another table's key is not it
    assert "not a version" in _run(tmp_path, "--version", "1/../2").stderr
    assert "where are the releases" in _run(tmp_path, "--version", "1.0.0").stderr
    assert _run(tmp_path, "--bogus").returncode == 1


def test_help_prints_the_header() -> None:
    done = subprocess.run(
        ["sh", str(SCRIPT), "--help"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0 and "install-mapper.sh [--config FILE]" in done.stdout
    assert "set -eu" not in done.stdout
