"""Shared fixtures of the offline tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = (
    ROOT / "desktop/gitfallback/target/debug/j2jme-git-helper",
    ROOT / "desktop/gitfallback/target/release/j2jme-git-helper",
)


@pytest.fixture(params=["git", "gix"])
def backend(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """The same cases on both git backends (`cli/gitops.py`): the `git` binary, and gitoxide through
    the helper. The helper is built with `dev_scripts/gix.sh`; without it the gix runs are skipped."""
    if request.param == "gix":
        found = os.environ.get("J2JME_GIT_HELPER") or next(
            (str(h) for h in HELPERS if h.is_file()), None
        )
        if found is None or not Path(found).is_file():
            pytest.skip("the gix helper is not built: dev_scripts/gix.sh")
        monkeypatch.setenv("J2JME_GIT_HELPER", found)
    monkeypatch.setenv("J2JME_GIT_BACKEND", request.param)
    return request.param
