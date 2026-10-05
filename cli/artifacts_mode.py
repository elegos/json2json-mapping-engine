"""Whether a project commits its generated files (`build/compiled`) or builds them in CI
(docs/ARCHITECTURE.md, §Build folder and incremental compilation).

`ignore` puts `build/compiled/` in the project's `.gitignore` and takes the files out of the git
index (the files stay on disk; the removal is staged, never committed: that is the user's
commit); `track` does the opposite. Both go through `cli/gitops.py` (git, or gitoxide when git is
not installed) and check with `check-ignore` that the result is what was asked, restoring
`.gitignore` otherwise."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cli import gitops
from cli.config import MapperConfigError

COMPILED = "build/compiled"
GITIGNORE = ".gitignore"
MARK = "# generated files are built by CI, not committed (mapper artifacts ignore)"
KEEP = "# only build/compiled is committed (mapper artifacts track)"

Mode = Literal["committed", "ignored", "unknown"]


@dataclass(frozen=True)
class ArtifactsState:
    """`mode`: `committed`, `ignored` (git ignores the folder), or `unknown` (no git, or not a
    repository). `tracked`: the files of `build/compiled` that are in the git index."""

    mode: Mode
    tracked: tuple[str, ...]
    git: bool

    def to_json(self) -> dict:
        return {"mode": self.mode, "tracked": list(self.tracked), "git": self.git}


def _is_repo(project: Path) -> bool:
    return gitops.is_repo(project)


def _ignored(project: Path) -> bool:
    # what the rules say, whether or not the files are tracked yet
    return gitops.check_ignore(project, f"{COMPILED}/manifest.json")


def state(project: Path) -> ArtifactsState:
    if not _is_repo(project):
        return ArtifactsState("unknown", (), False)
    listed = gitops.ls_files(project, COMPILED)
    return ArtifactsState("ignored" if _ignored(project) else "committed", tuple(listed), True)


def _read(path: Path) -> str:
    return path.read_text() if path.is_file() else ""


def _without_compiled_rules(lines: list[str]) -> list[str]:
    """`lines` without what says anything about `build/compiled` (and our own comments)."""
    drop = {"build/compiled", "/build/compiled", "build/compiled/", "/build/compiled/"}
    kept = []
    for line in lines:
        bare = line.strip().removeprefix("!")
        if bare in drop or line.strip() in (MARK, KEEP):
            continue
        kept.append(line)
    return kept


def _write(path: Path, lines: list[str]) -> None:
    text = "\n".join(lines).rstrip("\n")
    path.write_text(text + "\n" if text else "")


def ignore(project: Path) -> ArtifactsState:
    """Stop committing the generated files. Returns the state before. Raises `MapperConfigError`
    when git is missing, the project is not in a repository, or the result is not ignored."""
    before = state(project)
    if not before.git:
        raise MapperConfigError("not a git repository (or git is not installed)")
    path = project / GITIGNORE
    original = _read(path)
    lines = _without_compiled_rules(original.splitlines())
    if lines and lines[-1].strip():
        lines.append("")
    lines += [MARK, f"{COMPILED}/"]
    _write(path, lines)
    if not _ignored(project):
        path.write_text(original) if original else path.unlink()
        raise MapperConfigError(
            f"{COMPILED} is still not ignored after editing {GITIGNORE}: a rule of a parent "
            "folder's .gitignore (or `!` rule) re-includes it"
        )
    if before.tracked:
        try:
            gitops.rm_cached(project, COMPILED)
        except gitops.GitError as exc:
            raise MapperConfigError(str(exc)) from exc
    return before


def track(project: Path) -> ArtifactsState:
    """Commit the generated files again: `build/compiled` is no longer ignored, and the files
    on disk are staged. Returns the state before."""
    before = state(project)
    if not before.git:
        raise MapperConfigError("not a git repository (or git is not installed)")
    path = project / GITIGNORE
    original = _read(path)
    lines = _without_compiled_rules(original.splitlines())
    # `build/` ignores the folder as a whole, and a file cannot be re-included from an ignored
    # folder: it has to ignore what is in it instead
    lines = [
        "build/*" if line.strip() in ("build/", "/build/", "build") else line for line in lines
    ]
    if any(line.strip() in ("build/*", "/build/*") for line in lines):
        lines += ["", KEEP, f"!{COMPILED}/"]
    _write(path, lines)
    if _ignored(project):
        path.write_text(original) if original else path.unlink()
        raise MapperConfigError(
            f"{COMPILED} is still ignored after editing {GITIGNORE}: a rule elsewhere ignores it"
        )
    if (project / COMPILED).is_dir():
        try:
            gitops.add(project, [COMPILED])
        except gitops.GitError as exc:
            raise MapperConfigError(str(exc)) from exc
    return before
