import subprocess

import pytest

from compiler.backends.plsql import integration as track2


def _fake_run(returncode: int, stdout: str):
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return run


@pytest.fixture(autouse=True)
def _only_docker(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        track2.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None
    )


def test_docker_answering_with_a_version_is_a_runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(track2.subprocess, "run", _fake_run(0, "26.1.5\n"))
    assert track2.detect_runtime() == "docker"


def test_docker_exiting_0_with_no_version_is_not_a_runtime(monkeypatch: pytest.MonkeyPatch):
    # daemon unreachable, yet `docker info --format` exited 0 with empty output (CI)
    monkeypatch.setattr(track2.subprocess, "run", _fake_run(0, ""))
    assert track2.detect_runtime() is None
