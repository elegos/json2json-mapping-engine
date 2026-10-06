"""Creating, deleting and renaming a mapping (`mappings/functional/<name>.fn.yaml`) from the
desktop tool (ops of `mapper serve`). A mapping is its `.fn.yaml`, its two schema files by the
convention (`schemas/<name>_input.schema.json`, `..._output...`), what the build derives from it
and, if the project has them, its golden cases (`tests/golden/<name>/`)."""

from __future__ import annotations

import re
import shutil
from dataclasses import replace
from pathlib import Path

from cli.build_dir import build_root, generated_dir, relocated
from compiler.schema_files import Kind, schema_path
from transpiler.model import (
    _IDENT,
    FnYamlError,
    FunctionalFile,
    SchemasSection,
    load_functional_file,
)
from transpiler.serialize import write_functional

FUNCTIONAL = Path("mappings/functional")
GOLDEN = Path("tests/golden")
KINDS: tuple[Kind, ...] = ("input", "output")


def fn_path(project: Path, name: str) -> Path:
    return project / FUNCTIONAL / f"{name}.fn.yaml"


def _check_name(name: str) -> None:
    if not _IDENT.match(name):
        raise FnYamlError(
            f"{name!r} is not a valid mapping name: letters, digits and _, not starting with a digit"
        )


def _schemas(project: Path, name: str) -> list[Path]:
    return [schema_path(project / "schemas", name, kind) for kind in KINDS]


def _build(project: Path) -> Path:
    return build_root() if relocated() else project / "build"


def _generated(project: Path) -> Path:
    return generated_dir() if relocated() else project / "generated"


def derived(project: Path, name: str) -> list[Path]:
    """What the build and `mapper stubs` made from the mapping, as it is now on disk. The
    compiled `.sql` packages are not here: the next build drops those of a mapping that is gone."""
    candidates = [
        _build(project) / "transpiled" / f"{name}.map.py",
        _build(project) / "transpiled/stages" / name,
        _build(project) / "cache" / f"{name}.fn.yaml.unit.json",
        _generated(project) / "stubs" / f"{name}.pyi",
        _generated(project) / "dataclasses" / f"{name}.py",
    ]
    return [p for p in candidates if p.exists()]


def _shown(project: Path, paths: list[Path]) -> list[str]:
    return [str(p.relative_to(project)) for p in paths]


def _files_in(folder: Path) -> int:
    return sum(1 for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else 0


def golden_state(project: Path, name: str) -> dict[str, object]:
    """What `tests/golden/<name>/` holds (a mapping deleted earlier leaves its cases), and a
    free folder name to move them to."""
    folder = project / GOLDEN / name
    suggest, n = f"{name}_old", 1
    while (project / GOLDEN / suggest).exists():
        n += 1
        suggest = f"{name}_old{n}"
    return {
        "path": str(folder.relative_to(project)),
        "files": _files_in(folder),
        "suggest": suggest,
    }


def create_mapping(
    project: Path, name: str, golden: str | None = None, golden_to: str | None = None
) -> str:
    """A new, empty mapping; it loads, and building it says it is empty. Returns its path.

    When `tests/golden/<name>/` already holds cases, `golden` must say what becomes of them:
    `keep` (they are the new mapping's), `rename` (moved to `tests/golden/<golden_to>/`) or
    `delete`."""
    _check_name(name)
    path = fn_path(project, name)
    if path.exists():
        raise FnYamlError(f"there is already a mapping called {name!r}")
    folder = project / GOLDEN / name
    if _files_in(folder):
        if golden not in ("keep", "rename", "delete"):
            raise FnYamlError(
                f"{GOLDEN / name} is not empty: say whether to keep, rename or delete its cases"
            )
        if golden == "rename":
            if not golden_to or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", golden_to):
                raise FnYamlError(f"{golden_to!r} is not a valid folder name")
            if (project / GOLDEN / golden_to).exists():
                raise FnYamlError(f"{GOLDEN / golden_to} already exists")
            folder.rename(project / GOLDEN / golden_to)
        elif golden == "delete":
            shutil.rmtree(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_functional(path, FunctionalFile(name=name, id=name, rules=[], path=path))
    return str(path.relative_to(project))


def removal_plan(project: Path, name: str) -> list[str]:
    """What deleting the mapping removes, for the confirmation. The golden cases stay."""
    path = fn_path(project, name)
    if not path.is_file():
        raise FnYamlError(f"there is no mapping called {name!r}")
    files = [path, *[p for p in _schemas(project, name) if p.is_file()], *derived(project, name)]
    return _shown(project, files)


def delete_mapping(project: Path, name: str, golden: bool = False) -> list[str]:
    """Removes what `removal_plan` lists, and with `golden` also the golden cases."""
    plan = removal_plan(project, name)
    folder = project / GOLDEN / name
    if golden and folder.is_dir():
        plan.append(str(folder.relative_to(project)))
    for relative in plan:
        target = project / relative
        shutil.rmtree(target) if target.is_dir() else target.unlink()
    return plan


def rename_mapping(project: Path, old: str, new: str, new_id: str | None = None) -> dict[str, str]:
    """Renames `old` to `new`: the `.fn.yaml`, its schema files (and a `schemas:` entry that
    pointed at them), the golden folder; what the build derived is dropped (the next build
    makes it again). The file's `id`, which names the PL/SQL package, follows when it was the
    old name; `new_id` sets it by hand. `new == old` with a `new_id` only changes the id."""
    _check_name(new)
    source = fn_path(project, old)
    if not source.is_file():
        raise FnYamlError(f"there is no mapping called {old!r}")
    tree = load_functional_file(source)
    file_id = new_id if new_id else (new if tree.id == old else tree.id)
    _check_name(file_id)
    moves: list[tuple[Path, Path]] = []
    if new != old:
        target = fn_path(project, new)
        if target.exists():
            raise FnYamlError(f"there is already a mapping called {new!r}")
        for before, after in zip(_schemas(project, old), _schemas(project, new), strict=True):
            if before.is_file():
                if after.exists():
                    raise FnYamlError(f"{after.relative_to(project)} already exists")
                moves.append((before, after))
        golden = project / GOLDEN
        if (golden / old).is_dir():
            if (golden / new).exists():
                raise FnYamlError(f"{GOLDEN / new} already exists")
            moves.append((golden / old, golden / new))

    # what an entry of `schemas:` that named the old convention file becomes
    refs = tree.schemas
    renamed = {
        kind: str(schema_path(Path("schemas"), new, kind))
        if getattr(refs, kind) == str(schema_path(Path("schemas"), old, kind))
        else getattr(refs, kind)
        for kind in KINDS
    }
    tree = replace(
        tree,
        id=file_id,
        name=new if tree.name == old else tree.name,
        schemas=SchemasSection(input=renamed["input"], output=renamed["output"]),
        path=fn_path(project, new),
    )
    write_functional(fn_path(project, new), tree)
    if new != old:
        source.unlink()
        for before, after in moves:
            after.parent.mkdir(parents=True, exist_ok=True)
            before.rename(after)
        for path in derived(project, old):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    return {"name": new, "file_id": file_id}
