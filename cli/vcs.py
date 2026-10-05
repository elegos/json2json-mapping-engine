"""Version control for the desktop tool (docs/ARCHITECTURE.md, §Version control, git mode).

Everything goes through the `git` binary, run in the project's folder and limited to the project's
own paths (the project may be a folder of a bigger repository). Functions take the project folder,
work with it as the current directory where the build needs that, and answer plain data.

- `state` — branch, upstream, what changed, a rebase in progress, conflicted files;
- `commit` — check and build, then one commit of the sources **and** the generated files
  (when they are committed), so that what is deployed from git is what was reviewed; a failing
  check blocks it, or makes it a WIP commit with no generated files;
- `pull` / `push` — `git pull --rebase --autostash`; the conflicts that remain are settled
  with the merge engine (`conflicts`, `resolve`, `abort`);
"""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path
from typing import Any

from cli import artifacts_mode
from cli.config import MapperConfigError
from transpiler.merge import MergeError, load_raw, merge3, merge_fn_texts, merge_texts

# what a person writes in a project; what the commit takes, besides the generated files
AUTHORED = (
    "mapper.toml",
    ".gitignore",
    ".gitattributes",
    "mappings",
    "schemas",
    "lookups",
    "fn",
    "tests/golden",
)
COMPILED = artifacts_mode.COMPILED
WIP = "WIP: "


class VcsError(Exception):
    """A version-control operation that cannot be done (no git, not a repository, a rebase
    already stopped, a commit with nothing to say)."""


def _git(
    project: Path, *args: str, check: bool = True, text: bool = True
) -> subprocess.CompletedProcess[Any]:
    try:
        done = subprocess.run(
            ["git", "-C", str(project), *args], capture_output=True, text=text, check=False
        )
    except FileNotFoundError as exc:
        raise VcsError("git is not installed") from exc
    if check and done.returncode != 0:
        err = done.stderr if text else done.stderr.decode(errors="replace")
        raise VcsError(f"git {args[0]}: {err.strip() or 'failed'}")
    return done


def _require_repo(project: Path) -> None:
    if _git(project, "rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        raise VcsError(f"{project} is not in a git repository")


def _git_dir(project: Path) -> Path:
    out = _git(project, "rev-parse", "--absolute-git-dir").stdout.strip()
    return Path(out)


def _rebasing(project: Path) -> bool:
    gd = _git_dir(project)
    return (gd / "rebase-merge").is_dir() or (gd / "rebase-apply").is_dir()


def _authored(project: Path) -> list[str]:
    return [p for p in AUTHORED if (project / p).exists()]


def _tracked_compiled(project: Path) -> bool:
    """Whether the generated files are committed (not git-ignored)."""
    return artifacts_mode.state(project).mode == "committed"


def _pathspec(project: Path, *, generated: bool) -> list[str]:
    specs = _authored(project)
    if generated:
        specs.append(COMPILED)
    return specs


def _relative_to_project(project: Path, path: str) -> str:
    """`path`, as git prints it (from the repository's root), as a path from the project's."""
    prefix = _git(project, "rev-parse", "--show-prefix").stdout.strip()
    return path.removeprefix(prefix)


def state(project: Path) -> dict[str, Any]:
    """`{git, repo, branch, upstream, ahead, behind, rebasing, changes, conflicts}`. `changes`
    are `{path, status, generated}` for the project's paths (paths from the project), `conflicts`
    the unmerged files. Without git or a repository, only `git` / `repo`."""
    try:
        have = _git(project, "--version", check=False).returncode == 0
    except VcsError:
        return {"git": False, "repo": False}
    if not have or _git(project, "rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        return {"git": have, "repo": False}
    branch = _git(project, "branch", "--show-current").stdout.strip() or None
    upstream = None
    ahead = behind = 0
    found = _git(project, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    if found.returncode == 0:
        upstream = found.stdout.strip()
        counts = _git(project, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        ahead, behind = (int(n) for n in counts.stdout.split())
    changes = []
    out = _git(
        project,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--",
        *_pathspec(project, generated=True),
        text=False,
    ).stdout.decode()
    entries = out.split("\0")
    i = 0
    while i < len(entries) and entries[i]:
        code, path = entries[i][:2], entries[i][3:]
        if code[0] in "RC":  # a rename lists the old path next
            i += 1
        i += 1
        rel = _relative_to_project(project, path)
        changes.append(
            {
                "path": rel,
                "status": "?" if code == "??" else code.strip() or "?",
                "generated": rel.startswith(f"{COMPILED}/"),
            }
        )
    unmerged = _git(project, "diff", "--name-only", "--diff-filter=U").stdout.split()
    return {
        "git": True,
        "repo": True,
        "branch": branch,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "rebasing": _rebasing(project),
        "changes": changes,
        "conflicts": [_relative_to_project(project, p) for p in unmerged],
    }


# --- what changed, in the words of the grid -----------------------------------------------------

_GROUPS = {"source": "source", "transform": "transform", "description": "description"}


def _walk(rules: list[Any] | None, prefix: str = "") -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for i, rule in enumerate(rules or []):
        if not isinstance(rule, dict):
            continue
        key = str(
            rule.get("id") or rule.get("field") or rule.get("label") or rule.get("output") or i
        )
        fq = f"{prefix}.{key}" if prefix else key
        found[fq] = {k: v for k, v in rule.items() if k != "rules"}
        found.update(_walk(rule.get("rules") or [], fq))
    return found


def diff_rules(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[str]]:
    """Which rules (by id) were `added`, `removed` or `changed` between two `.fn.yaml` (raw data),
    and for a changed rule which field groups it touched: `source`, `transform`, `description`,
    `other`. A rule is `id` or, nested, `parent.id`."""
    before, after = _walk(old.get("rules")), _walk(new.get("rules"))
    out: dict[str, list[str]] = {
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": [],
    }
    for key in sorted(before.keys() & after.keys()):
        groups = set()
        for field in before[key].keys() | after[key].keys():
            if before[key].get(field) != after[key].get(field):
                groups.add(_GROUPS.get(field, "other"))
        if groups:
            order = ("source", "transform", "description", "other")
            out["changed"].append(f"{key} ({', '.join(g for g in order if g in groups)})")
    return out


def _head_text(project: Path, rel: str) -> str:
    done = _git(project, "show", f"HEAD:./{rel}", check=False)
    return done.stdout if done.returncode == 0 else ""


def summary(project: Path) -> list[str]:
    """One line per changed mapping: the rules added, removed and changed (by id, with the field
    groups touched), against HEAD."""
    lines = []
    for change in state(project).get("changes", []):
        rel = change["path"]
        if not (rel.startswith("mappings/functional/") and rel.endswith(".fn.yaml")):
            continue
        try:
            new = load_raw((project / rel).read_text(), rel) if (project / rel).is_file() else {}
            old_text = _head_text(project, rel)
            old = load_raw(old_text, rel) if old_text.strip() else {}
        except MergeError:
            lines.append(f"{Path(rel).name.removesuffix('.fn.yaml')}: changed")
            continue
        found = diff_rules(old, new)
        name = Path(rel).name.removesuffix(".fn.yaml")
        parts = []
        if not old_text.strip():
            parts.append("new mapping")
        for key, label in (("added", "added"), ("removed", "removed"), ("changed", "changed")):
            if found[key]:
                parts.append(f"{label}: {', '.join(found[key])}")
        lines.append(f"{name}: {'; '.join(parts) or 'changed'}")
    return lines


# --- commit -------------------------------------------------------------------------------------


def _problems(project: Path) -> list[str]:
    """What stops a clean commit: a rule with an error, or a mapping that does not build."""
    from cli.build import BuildError, compile_mapping, discover_mappings
    from cli.config import load_config
    from compiler.function_registry import all_functions
    from transpiler.check import check_functional, schemas_for
    from transpiler.model import FnYamlError, load_functional_file

    problems: list[str] = []
    with contextlib.chdir(project):
        config = load_config()
        functions = all_functions(Path.cwd())
        for path in sorted(Path("mappings/functional").glob("*.fn.yaml")):
            try:
                tree = load_functional_file(path)
            except (FnYamlError, OSError) as exc:
                problems.append(str(exc))
                continue
            inp, out = schemas_for(Path.cwd(), path.name.removesuffix(".fn.yaml"), tree.schemas)
            problems += [
                f"{path.name}: {i.rule}: {i.message}"
                for i in check_functional(tree, inp, out, functions)
                if i.severity == "error"
            ]
        if not problems:
            try:
                for mapping in discover_mappings(config):
                    compile_mapping(mapping, config)
            except (BuildError, MapperConfigError) as exc:
                problems.append(str(exc))
            except Exception as exc:  # a mapping the compiler cannot take
                problems.append(f"{type(exc).__name__}: {exc}")
    return problems


def _build(project: Path) -> None:
    from cli.build import compile_mapping, discover_mappings, write_package
    from cli.config import load_config

    with contextlib.chdir(project):
        config = load_config()
        units = [compile_mapping(p, config).unit for p in discover_mappings(config)]
        write_package(units, config)


def commit(project: Path, notes: str = "", *, wip: bool = False) -> dict[str, Any]:
    """Check, build, and commit the project's changes.

    The check is the rules' errors and a build of every mapping. If it fails, nothing is
    committed (`blocked`, with `problems`) unless `wip`: then the sources are committed with
    `WIP: ` in front of the subject and the generated files are left out. If it passes, the
    generated files are regenerated first and go in the same commit (when they are committed, not
    git-ignored). `notes`: the version notes: the first line is the subject, the rest the body; the
    rules changed are listed after them. Only the project's paths are committed, whatever else is
    staged in the repository."""
    _require_repo(project)
    if _rebasing(project):
        raise VcsError("a rebase is in progress: finish or abort it first")
    if state(project)["conflicts"]:
        raise VcsError("there are unresolved conflicts")
    problems = _problems(project)
    if problems and not wip:
        return {"ok": False, "blocked": True, "problems": problems}
    generated = not problems and _tracked_compiled(project)
    if generated:
        _build(project)
    specs = _pathspec(project, generated=generated)
    # also what was deleted: `add -A` with a pathspec sees it, as long as git still knows the path
    _git(project, "add", "-A", "--", *[s for s in specs if (project / s).exists()])
    if _git(project, "diff", "--cached", "--quiet", "--", *specs, check=False).returncode == 0:
        return {"ok": True, "committed": False, "message": "nothing to commit", "problems": []}
    first, _, rest = notes.strip().partition("\n")
    subject = first.strip() or "Update mappings"
    if problems:
        subject = WIP + subject
    body = [rest.strip()] if rest.strip() else []
    lines = summary(project)
    if lines:
        body.append("\n".join(lines))
    args = ["commit", "-q", "-m", subject]
    for part in body:
        args += ["-m", part]
    _git(project, *args, "--", *specs)
    rev = _git(project, "rev-parse", "--short", "HEAD").stdout.strip()
    return {"ok": True, "committed": True, "commit": rev, "subject": subject, "problems": problems}


# --- pull, push, conflicts ----------------------------------------------------------------------


def _is_generated(rel: str) -> bool:
    return rel.startswith(f"{COMPILED}/")


def _continue(project: Path) -> dict[str, Any]:
    """Carry a rebase on as far as it goes by itself. The generated files are never merged: when
    only they are in conflict, the sources are settled, so they are regenerated, staged, and the
    rebase continues (the next commit of the rebase may stop again). Returns what is left:
    `{conflicts, rebasing}`, `conflicts` without the generated files."""
    for _ in range(100):  # one round per replayed commit
        info = state(project)
        if not info["rebasing"]:
            return {"conflicts": [], "rebasing": False}
        left = [c for c in info["conflicts"] if not _is_generated(c)]
        if left:
            return {"conflicts": left, "rebasing": True}
        if info["conflicts"]:  # only generated files: regenerate them
            _build(project)
            _git(project, "add", "-A", "--", COMPILED)
        done = _git(project, "-c", "core.editor=true", "rebase", "--continue", check=False)
        if done.returncode != 0 and not state(project)["conflicts"]:
            raise VcsError(f"git rebase --continue: {done.stderr.strip() or 'failed'}")
    raise VcsError("the rebase does not end")


def ensure_driver(project: Path) -> dict[str, bool]:
    """Have this clone merge mappings and functions at the rule level (`cli/merge_driver.py`),
    without the user knowing: done when a project is opened, and before every pull."""
    from cli.merge_driver import ensure

    return ensure(project)


def pull(project: Path) -> dict[str, Any]:
    """`git pull --rebase --autostash`. `{ok, conflicts}`: when the rebase stops on files it could
    not merge, `conflicts` lists them (settle them with `conflicts` / `resolve`, or `abort`)."""
    _require_repo(project)
    if _rebasing(project):
        raise VcsError("a rebase is in progress: finish or abort it first")
    ensure_driver(project)
    if state(project)["upstream"] is None:
        raise VcsError("this branch has no upstream to pull from")
    done = _git(project, "pull", "--rebase", "--autostash", "-q", check=False)
    if done.returncode == 0:
        return {"ok": True, "conflicts": []}
    stopped = state(project)
    if stopped["rebasing"] or stopped["conflicts"]:
        left = _continue(project)
        if not left["rebasing"]:
            return {"ok": True, "conflicts": []}
        return {"ok": False, "conflicts": left["conflicts"], "message": done.stderr.strip()}
    raise VcsError(f"git pull: {done.stderr.strip() or 'failed'}")


def push(project: Path) -> dict[str, Any]:
    _require_repo(project)
    info = state(project)
    if info["upstream"] is None:
        done = _git(project, "push", "-q", "-u", "origin", "HEAD", check=False)
    else:
        done = _git(project, "push", "-q", check=False)
    if done.returncode != 0:
        raise VcsError(f"git push: {done.stderr.strip() or 'failed'}")
    return {"ok": True}


def _stage(project: Path, n: int, rel: str) -> str | None:
    done = _git(project, "show", f":{n}:./{rel}", check=False)
    return done.stdout if done.returncode == 0 else None


def _sides(project: Path, rel: str) -> tuple[str, str, str]:
    """(base, remote, mine) of a conflicted file. In a rebase the index calls the branch being
    rebased onto *ours* (stage 2) and the commit being replayed *theirs* (stage 3); in a merge,
    the other way round."""
    base, two, three = (_stage(project, n, rel) for n in (1, 2, 3))
    rebasing = _rebasing(project)
    remote, mine = (two, three) if rebasing else (three, two)
    return base or "", remote or "", mine or ""


def conflicts(project: Path) -> list[dict[str, Any]]:
    """The conflicted files and, for a `.fn.yaml` or `.fn` file, what conflicts in it: per file
    `{file, kind, items}`; `kind` is `rules` (`.fn.yaml`), `functions` (`.fn`) or `text`. An item
    is `{path, base, mine, remote, mine_missing, remote_missing}`: a rule field, a rule, or a
    function that both sides changed. A file the rule- or function-level merge settles by itself
    comes with no items: `resolve` will write it. A `text` file cannot be settled here."""
    _require_repo(project)
    out = []
    for rel in state(project)["conflicts"]:
        if _is_generated(rel):  # regenerated, never merged
            out.append({"file": rel, "kind": "generated", "items": []})
            continue
        base, remote, mine = _sides(project, rel)
        kind, items = "text", []
        try:
            if rel.endswith(".fn.yaml"):
                kind = "rules"
                result = merge3(
                    load_raw(base, "base") if base.strip() else None,
                    load_raw(remote, "remote"),
                    load_raw(mine, "mine"),
                )
                found = result.conflicts
            elif rel.endswith(".fn"):
                kind = "functions"
                _, found = merge_fn_texts(base, remote, mine)
            else:
                found = []
                kind = "text"
        except MergeError:
            kind, found = "text", []
        for c in found:
            items.append(
                {
                    "path": c.path,
                    "base": c.base,
                    "mine": c.theirs,
                    "remote": c.ours,
                    "mine_missing": c.theirs_missing,
                    "remote_missing": c.ours_missing,
                }
            )
        out.append({"file": rel, "kind": kind, "items": items})
    return out


def _settle(project: Path, rel: str, choices: dict[str, str]) -> str:
    """The merged text of a conflicted file with `choices` (path -> `mine` | `remote`)."""
    base, remote, mine = _sides(project, rel)
    merge_choices: Any = {p: ("theirs" if c == "mine" else "ours") for p, c in choices.items()}
    try:
        if rel.endswith(".fn.yaml"):
            text, left = merge_texts(base, remote, mine, merge_choices)
        elif rel.endswith(".fn"):
            text, left = merge_fn_texts(base, remote, mine, merge_choices)
        else:
            raise VcsError(f"{rel} is not a file the tool can settle: edit it, or abort")
    except MergeError as exc:
        raise VcsError(f"{rel}: {exc}") from exc
    if left:
        raise VcsError(f"{rel}: still to choose: {', '.join(c.path for c in left)}")
    return text


def resolve(project: Path, file: str, choices: dict[str, str] | None = None) -> dict[str, Any]:
    """Settle one conflicted file with `choices` (path -> `mine` | `remote`, for every item
    `conflicts` listed), stage it, and when no conflicted file is left, continue the rebase. Returns
    `{ok, conflicts, done}`: `conflicts` the files still unmerged (the next commit of the rebase may
    stop on others; the generated files are not listed, they are regenerated), `done` true when the
    rebase is over."""
    _require_repo(project)
    text = _settle(project, file, choices or {})
    (project / file).write_text(text)
    _git(project, "add", "--", file)
    if not _rebasing(project):
        left = [c for c in state(project)["conflicts"] if not _is_generated(c)]
        return {"ok": True, "conflicts": left, "done": not left}
    rest = _continue(project)
    return {"ok": True, "conflicts": rest["conflicts"], "done": not rest["rebasing"]}


def abort(project: Path) -> dict[str, Any]:
    """Give up the rebase: the branch and the working files are as before the pull."""
    _require_repo(project)
    if not _rebasing(project):
        raise VcsError("no rebase in progress")
    _git(project, "rebase", "--abort")
    return {"ok": True}
