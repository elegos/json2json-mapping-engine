"""The golden cases of a mapping (`tests/golden/<mapping>/`), managed from the desktop tool
(ops of `mapper serve`). A case is `<case>.input.json` (it exists when that file does) with an
optional `<case>.expected.json` and `<case>.expected_errors.json` (a list of rule ids): the
names every backend and CI read (`compiler/backends/integration.py`). Loading a case copies
the user's files under those names, so that the role of a file is its name."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from compiler.backends.integration import ERRORS_SUFFIX, EXPECTED_SUFFIX, GOLDEN_DIR, INPUT_SUFFIX
from transpiler.model import FnYamlError

_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")
_SUFFIXES = (INPUT_SUFFIX, EXPECTED_SUFFIX, ERRORS_SUFFIX)


def _folder(project: Path, mapping: str) -> Path:
    return project / GOLDEN_DIR / mapping


def _check_name(name: str) -> None:
    if not _NAME.match(name):
        raise FnYamlError(f"{name!r} is not a valid case name: letters, digits, _ and -")


def _files(project: Path, mapping: str, case: str) -> list[Path]:
    folder = _folder(project, mapping)
    return [p for p in (folder / f"{case}{s}" for s in _SUFFIXES) if p.is_file()]


def list_cases(project: Path, mapping: str) -> list[dict[str, Any]]:
    """The cases of the mapping and which of their files exist."""
    folder = _folder(project, mapping)
    names = sorted(p.name.removesuffix(INPUT_SUFFIX) for p in folder.glob(f"*{INPUT_SUFFIX}"))
    return [
        {
            "name": n,
            "expected": (folder / f"{n}{EXPECTED_SUFFIX}").is_file(),
            "errors": (folder / f"{n}{ERRORS_SUFFIX}").is_file(),
        }
        for n in names
    ]


def _read_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text())
    except OSError as exc:
        raise FnYamlError(f"{what}: {path.name}: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise FnYamlError(f"{what}: {path.name} is not valid JSON ({exc})") from exc


def import_case(
    project: Path,
    mapping: str,
    name: str,
    input_file: Path,
    expected_file: Path | None = None,
    errors_file: Path | None = None,
) -> list[str]:
    """Copies the files into the mapping's golden folder as `<name>.input.json`, `.expected.json`
    and `.expected_errors.json`. Every file is read first (it must be JSON; the errors file a list
    of rule ids) and nothing is written if one is wrong or the case exists. Returns the files."""
    _check_name(name)
    if _files(project, mapping, name):
        raise FnYamlError(f"the mapping already has a case called {name!r}")
    _read_json(input_file, "input")
    if expected_file:
        _read_json(expected_file, "expected output")
    if errors_file:
        errors = _read_json(errors_file, "expected errors")
        if not (isinstance(errors, list) and all(isinstance(e, str) for e in errors)):
            raise FnYamlError("expected errors: the file must be a list of rule ids")
    folder = _folder(project, mapping)
    folder.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for source, suffix in (
        (input_file, INPUT_SUFFIX),
        (expected_file, EXPECTED_SUFFIX),
        (errors_file, ERRORS_SUFFIX),
    ):
        if source:
            shutil.copyfile(source, folder / f"{name}{suffix}")
            written.append(str((folder / f"{name}{suffix}").relative_to(project)))
    return written


def rename_case(project: Path, mapping: str, old: str, new: str) -> None:
    _check_name(new)
    files = _files(project, mapping, old)
    if not files:
        raise FnYamlError(f"the mapping has no case called {old!r}")
    if old != new and _files(project, mapping, new):
        raise FnYamlError(f"the mapping already has a case called {new!r}")
    folder = _folder(project, mapping)
    for path in files:
        suffix = next(s for s in _SUFFIXES if path.name.endswith(s))
        path.rename(folder / f"{new}{suffix}")


def delete_case(project: Path, mapping: str, name: str) -> list[str]:
    files = _files(project, mapping, name)
    if not files:
        raise FnYamlError(f"the mapping has no case called {name!r}")
    for path in files:
        path.unlink()
    return [str(p.relative_to(project)) for p in files]
