"""Projects in a synced folder: detection by path, and the build folder moved for one request."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import serve, synced
from cli.main import app
from tests.track1.cli.test_build_cli import MAPPER_TOML, PING_MAPPING

runner = CliRunner()


@pytest.mark.parametrize(
    ("folder", "name"),
    [
        ("OneDrive/work", "OneDrive"),
        ("OneDrive - Contoso/Team Site/maps", "OneDrive"),
        ("Contoso - Team Site/maps", None),  # only the folder name of a library: not enough
        ("SharePoint/Site", "SharePoint"),
        ("Dropbox/maps", "Dropbox"),
        ("Google Drive/maps", "Google Drive"),
        ("Library/CloudStorage/OneDrive-Contoso/maps", "OneDrive"),
        ("Library/CloudStorage/GoogleDrive-me@x.org/maps", "Google Drive"),
        ("src/maps", None),
    ],
)
def test_provider_by_the_names_on_the_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, folder: str, name: str | None
) -> None:
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / folder
    path.mkdir(parents=True)
    assert synced.provider(path) == name


def test_the_sync_folders_of_the_environment_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "Home" / "Contoso"  # a company that names its sync folder as it likes
    (root / "maps").mkdir(parents=True)
    monkeypatch.setenv("OneDriveCommercial", str(root))
    assert synced.provider(root / "maps") == "OneDrive"
    assert synced.provider(tmp_path) is None


def test_a_repository_in_a_synced_folder_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OneDrive", raising=False)
    repo = tmp_path / "OneDrive" / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "proj").mkdir()
    answer = synced.status(repo / "proj")
    assert answer == {"synced": "OneDrive", "git": str(repo.resolve())}
    plain = tmp_path / "plain" / "repo"
    (plain / ".git").mkdir(parents=True)
    assert synced.status(plain) == {"synced": None, "git": None}  # git is nobody's problem there


def test_the_worker_moves_the_build_folder_for_one_request(tmp_path: Path) -> None:
    seen: list[str | None] = []
    original = serve._handle  # pyright: ignore[reportPrivateUsage]
    serve._handle = lambda r: seen.append(os.environ.get("J2JME_BUILD_DIR")) or {"ok": True}  # pyright: ignore[reportPrivateUsage]
    try:
        serve.handle({"op": "x", "build_dir": str(tmp_path)})
        serve.handle({"op": "x"})
    finally:
        serve._handle = original  # pyright: ignore[reportPrivateUsage]
    assert seen == [str(tmp_path), None]
    assert "J2JME_BUILD_DIR" not in os.environ


@pytest.fixture
def onedrive_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("J2JME_BUILD_DIR", raising=False)
    monkeypatch.delenv("J2JME_ALLOW_SYNCED", raising=False)
    project = tmp_path / "OneDrive" / "maps"
    (project / "mappings").mkdir(parents=True)
    (project / "mapper.toml").write_text(MAPPER_TOML)
    (project / "mappings" / "ping.map.py").write_text(PING_MAPPING)
    monkeypatch.chdir(project)
    return project


def test_a_build_in_a_synced_folder_stops_and_writes_nothing(onedrive_project: Path) -> None:
    for command in ("build", "check", "stubs", "publish"):
        result = runner.invoke(app, [command])
        assert result.exit_code == 1, command
        assert "OneDrive folder" in result.output
    assert sorted(p.name for p in onedrive_project.iterdir()) == ["mapper.toml", "mappings"]


def test_a_moved_build_or_a_declared_ordinary_folder_goes_ahead(
    onedrive_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("J2JME_BUILD_DIR", str(tmp_path / "local"))
    assert runner.invoke(app, ["build"]).exit_code == 0
    assert (tmp_path / "local" / "compiled" / "map_ping.sql").is_file()
    monkeypatch.delenv("J2JME_BUILD_DIR")
    monkeypatch.setenv("J2JME_ALLOW_SYNCED", "1")
    assert runner.invoke(app, ["build"]).exit_code == 0
    assert (onedrive_project / "build" / "compiled" / "map_ping.sql").is_file()


def test_removing_the_git_of_a_synced_project_keeps_the_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        monkeypatch.delenv(var, raising=False)
    repo = tmp_path / "SharePoint" / "repo"
    (repo / ".git" / "objects").mkdir(parents=True)
    pack = repo / ".git" / "objects" / "pack.idx"
    pack.write_text("x")
    pack.chmod(0o444)  # git writes its packs read-only
    (repo / ".git").chmod(0o755)
    (repo / "mapper.toml").write_text("keep")
    assert synced.remove_git(repo) == {"removed": str(repo.resolve() / ".git")}
    assert not (repo / ".git").exists() and (repo / "mapper.toml").read_text() == "keep"
    assert synced.status(repo) == {"synced": "SharePoint", "git": None}


def test_only_a_git_in_a_synced_folder_can_be_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        monkeypatch.delenv(var, raising=False)
    plain = tmp_path / "work" / "repo"
    (plain / ".git").mkdir(parents=True)
    with pytest.raises(ValueError, match="no git repository in a synced folder"):
        synced.remove_git(plain)
    assert (plain / ".git").is_dir()
    above = tmp_path / "repo"  # the repository is above the synced folder: not the sync's
    (above / ".git").mkdir(parents=True)
    (above / "Dropbox" / "p").mkdir(parents=True)
    assert synced.status(above / "Dropbox" / "p")["git"] is None
    with pytest.raises(ValueError):
        synced.remove_git(above / "Dropbox" / "p")
