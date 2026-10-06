"""git for the tool, with or without the `git` binary (docs/ARCHITECTURE.md, §Version control,
§Without git).

The functions here are what `cli/vcs.py`, `cli/artifacts_mode.py` and `cli/merge_driver.py` need of
git, and nothing more. Two backends answer them the same way:

- **git**: the `git` binary, run in the project's folder;
- **gix**: the desktop tool's own executable, which carries gitoxide (`j2jme-desktop --git-helper`,
  `desktop/src-tauri/src/gitfallback.rs`): one JSON request on stdin, one answer on stdout. It is used
  when `git` is not installed, and the tool tells the helper's path in `J2JME_GIT_HELPER`.

`J2JME_GIT_BACKEND=git|gix` forces one (the tests run the same cases on both). A project may be a
folder of a bigger repository: paths in and out are relative to the project's folder."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ENV_BACKEND = "J2JME_GIT_BACKEND"
ENV_HELPER = "J2JME_GIT_HELPER"


class GitError(Exception):
    """A git operation that failed. `auth`: more credentials could cure it."""

    def __init__(self, message: str, auth: bool = False) -> None:
        super().__init__(message)
        self.auth = auth


def _helper_path() -> str | None:
    found = os.environ.get(ENV_HELPER)
    return found if found and Path(found).is_file() else None


def backend() -> str | None:
    """`git`, `gix`, or None when there is neither."""
    forced = os.environ.get(ENV_BACKEND)
    if forced == "gix":
        return "gix" if _helper_path() else None
    if forced == "git":
        return "git" if shutil.which("git") else None
    if shutil.which("git"):
        return "git"
    return "gix" if _helper_path() else None


def available() -> bool:
    return backend() is not None


def _require() -> str:
    found = backend()
    if found is None:
        raise GitError("git is not installed")
    return found


# --- the git binary ------------------------------------------------------------------------------


def _run(
    project: Path,
    *args: str,
    check: bool = True,
    text: bool = True,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[Any]:
    try:
        done = subprocess.run(
            ["git", "-C", str(project), *args],
            capture_output=True,
            text=text,
            check=False,
            input=stdin,
            # nobody is at a terminal: a remote that asks must fail at once, not wait for typing.
            # An empty GIT_ASKPASS also shuts the desktop's own helper (core.askPass, SSH_ASKPASS:
            # ksshaskpass, ...), which would pop a window of its own; the tool asks for the login
            # itself (`_askpass`, which overrides this)
            # messages in English whatever the language of the machine: they are looked at
            env={
                **os.environ,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "",
                "LC_ALL": "C",
                **(env or {}),
            },
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed") from exc
    if check and done.returncode != 0:
        err = done.stderr if text else done.stderr.decode(errors="replace")
        raise GitError(f"git {args[0]}: {err.strip() or 'failed'}")
    return done


@contextlib.contextmanager
def _askpass(credentials: dict[str, str] | None) -> Iterator[dict[str, str]]:
    """The environment that makes git use `credentials` (a user name and a password or token the
    user typed into the tool): a throw-away `GIT_ASKPASS` script that answers by the prompt. POSIX
    only; on Windows git has its own credential manager. Nothing is written but the script, which
    holds no secret: it reads them from the environment of this one command."""
    if not credentials or os.name == "nt":
        yield {}
        return
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "askpass.sh"
        script.write_text(
            '#!/bin/sh\ncase "$1" in *sername*) printf %s "$J2JME_GIT_USER" ;;'
            ' *) printf %s "$J2JME_GIT_PASS" ;; esac\n'
        )
        script.chmod(0o700)
        yield {
            "GIT_ASKPASS": str(script),
            "J2JME_GIT_USER": credentials.get("username", ""),
            "J2JME_GIT_PASS": credentials.get("password", ""),
        }


# --- the helper ----------------------------------------------------------------------------------


def _helper(op: str, project: Path, **fields: Any) -> dict[str, Any]:
    exe = _helper_path()
    if exe is None:
        raise GitError("git is not installed")
    request = json.dumps({"op": op, "project": str(project), **fields})
    try:
        done = subprocess.run(
            [exe, "--git-helper"], input=request, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise GitError(f"cannot run the git helper: {exc}") from exc
    try:
        answer = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise GitError(f"the git helper answered nothing readable: {done.stderr.strip()}") from exc
    if not answer.get("ok"):
        raise GitError(str(answer.get("error", "failed")), bool(answer.get("auth")))
    return answer


def _value(answer: dict[str, Any]) -> Any:
    return answer.get("value")


# --- the operations ------------------------------------------------------------------------------


def is_repo(project: Path) -> bool:
    found = backend()
    if found is None:
        return False
    if found == "gix":
        try:
            return bool(_value(_helper("is_repo", project)))
        except GitError:
            return False
    return _run(project, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0


def _prefix(project: Path) -> str:
    return _run(project, "rev-parse", "--show-prefix").stdout.strip()


def rebasing(project: Path) -> bool:
    if _require() == "gix":
        return bool(_helper("rebasing", project)["rebasing"])
    gd = Path(_run(project, "rev-parse", "--absolute-git-dir").stdout.strip())
    return (gd / "rebase-merge").is_dir() or (gd / "rebase-apply").is_dir()


def state(project: Path, specs: list[str]) -> dict[str, Any]:
    """`{branch, upstream, ahead, behind, rebasing, changes: [{path, code}], conflicts: [path]}`.
    `code` is git's two-letter short status (` M`, `??`, `D `, `UU`...)."""
    if _require() == "gix":
        answer = _helper("state", project, specs=specs)
        answer.pop("ok", None)
        return answer
    branch = _run(project, "branch", "--show-current").stdout.strip() or None
    upstream = None
    ahead = behind = 0
    found = _run(project, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    if found.returncode == 0:
        upstream = found.stdout.strip()
        counts = _run(project, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        ahead, behind = (int(n) for n in counts.stdout.split())
    prefix = _prefix(project)
    changes = []
    out = _run(
        project,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--",
        *(specs or ["."]),  # the project's folder, not the whole repository
        text=False,
    ).stdout.decode()
    entries = out.split("\0")
    i = 0
    while i < len(entries) and entries[i]:
        code, path = entries[i][:2], entries[i][3:]
        if code[0] in "RC":  # a rename lists the old path next
            i += 1
        i += 1
        changes.append({"path": path.removeprefix(prefix), "code": code})
    unmerged = _run(project, "diff", "--name-only", "--diff-filter=U").stdout.split()
    return {
        "branch": branch,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "rebasing": rebasing(project),
        "changes": changes,
        "conflicts": [p.removeprefix(prefix) for p in unmerged],
    }


def add(project: Path, specs: list[str]) -> None:
    """`git add -A -- specs`: what is on disk under `specs` (also what was deleted)."""
    if _require() == "gix":
        _helper("add", project, specs=specs)
        return
    _run(project, "add", "-A", "--", *specs)


def rm_cached(project: Path, spec: str) -> None:
    """`git rm -r --cached -- spec`: out of the index, the files stay."""
    if _require() == "gix":
        _helper("rm_cached", project, spec=spec)
        return
    _run(project, "rm", "-r", "--cached", "-q", "--", spec)


def ls_files(project: Path, spec: str) -> list[str]:
    """The files of `spec` in the index, from the project's folder."""
    if _require() == "gix":
        return list(_value(_helper("ls_files", project, spec=spec)) or [])
    return _run(project, "ls-files", "--", spec).stdout.splitlines()


def check_ignore(project: Path, path: str) -> bool:
    """Whether the ignore rules cover `path`, tracked or not (`git check-ignore --no-index`)."""
    if _require() == "gix":
        return bool(_value(_helper("check_ignore", project, path=path)))
    return _run(project, "check-ignore", "-q", "--no-index", path, check=False).returncode == 0


def commit(project: Path, parts: list[str], specs: list[str]) -> dict[str, Any]:
    """Stage what is on disk under `specs` and commit exactly that, whatever else is staged:
    `{committed, commit}`. `parts` are the paragraphs of the message (the first is the title)."""
    if _require() == "gix":
        answer = _helper("commit", project, message="\n\n".join(parts), specs=specs)
        return {"committed": bool(answer.get("committed")), "commit": answer.get("commit")}
    existing = [s for s in specs if (project / s).exists()]
    _run(project, "add", "-A", "--", *existing)
    if _run(project, "diff", "--cached", "--quiet", "--", *specs, check=False).returncode == 0:
        return {"committed": False, "commit": None}
    args = ["commit", "-q"]
    for part in parts:
        args += ["-m", part]
    _run(project, *args, "--", *specs)
    return {
        "committed": True,
        "commit": _run(project, "rev-parse", "--short", "HEAD").stdout.strip(),
    }


def show_head(project: Path, rel: str) -> str | None:
    """The text of `rel` at HEAD, or None."""
    if _require() == "gix":
        return _value(_helper("show_head", project, path=rel))
    done = _run(project, "show", f"HEAD:./{rel}", check=False)
    return done.stdout if done.returncode == 0 else None


def stage_text(project: Path, n: int, rel: str) -> str | None:
    """The text of `rel` at index stage `n`: 1 the base, 2 what a rebase goes onto, 3 the commit
    being replayed."""
    if _require() == "gix":
        return _value(_helper("stage_text", project, n=n, path=rel))
    done = _run(project, "show", f":{n}:./{rel}", check=False)
    return done.stdout if done.returncode == 0 else None


def mark_resolved(project: Path, rel: str) -> None:
    """`git add -- rel` for a file that was in conflict."""
    if _require() == "gix":
        _helper("mark_resolved", project, path=rel)
        return
    _run(project, "add", "--", rel)


def pull(project: Path, credentials: dict[str, str] | None = None) -> dict[str, Any]:
    """`git pull --rebase` (with the work in progress put aside and back). `{ok, conflicts}`;
    when the rebase stopped on files it could not merge, `ok` is false and `conflicts` lists them.
    Raises `GitError` for anything else. `credentials` (`username`, `password`) are what the user
    typed for a remote that asks and has no helper."""
    if _require() == "gix":
        answer = _helper("pull", project, credentials=credentials)
        return {"ok": bool(answer["finished"]), "conflicts": answer.get("conflicts", [])}
    with _askpass(credentials) as env:
        done = _run(project, "pull", "--rebase", "--autostash", "-q", check=False, env=env)
    if done.returncode == 0:
        return {"ok": True, "conflicts": []}
    stopped = state(project, [])
    if stopped["rebasing"] or stopped["conflicts"]:
        return {"ok": False, "conflicts": stopped["conflicts"], "message": done.stderr.strip()}
    raise GitError(
        f"git pull: {done.stderr.strip() or 'failed'}", auth=_looks_like_auth(done.stderr)
    )


def _looks_like_auth(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in ("authentication", "could not read username", "403", "401"))


def rebase_continue(project: Path) -> dict[str, Any]:
    """Go on with a stopped rebase. The gix backend replays the rest of the commits and answers
    `{ok, conflicts}`; git is asked to continue, and the caller looks at the state."""
    if _require() == "gix":
        answer = _helper("continue", project)
        return {"ok": bool(answer["finished"]), "conflicts": answer.get("conflicts", [])}
    done = _run(project, "-c", "core.editor=true", "rebase", "--continue", check=False)
    return {"ok": done.returncode == 0, "conflicts": [], "message": done.stderr.strip()}


def rebase_abort(project: Path) -> None:
    if _require() == "gix":
        _helper("abort", project)
        return
    _run(project, "rebase", "--abort")


def push(project: Path, credentials: dict[str, str] | None = None) -> None:
    if _require() == "gix":
        _helper("push", project, credentials=credentials)
        return
    info = state(project, [])
    with _askpass(credentials) as env:
        if info["upstream"] is None:
            done = _run(project, "push", "-q", "-u", "origin", "HEAD", check=False, env=env)
        else:
            done = _run(project, "push", "-q", check=False, env=env)
    if done.returncode != 0:
        raise GitError(
            f"git push: {done.stderr.strip() or 'failed'}", auth=_looks_like_auth(done.stderr)
        )


def config_get(project: Path, key: str) -> str:
    """The value of `key` in the repository's own config; "" if there is none."""
    if _require() == "gix":
        return str(_value(_helper("config_get", project, key=key)) or "")
    return _run(project, "config", "--local", "--get", key, check=False).stdout.strip()


def config_remove_section(project: Path, name: str, subsection: str | None = None) -> bool:
    """Drop `[name "subsection"]` from the repository's own config; whether it was there."""
    if _require() == "gix":
        return bool(
            _helper("config_remove_section", project, name=name, subsection=subsection)["removed"]
        )
    section = f"{name}.{subsection}" if subsection else name
    return (
        _run(project, "config", "--local", "--remove-section", section, check=False).returncode == 0
    )


def config_set(project: Path, key: str, value: str) -> None:
    if _require() == "gix":
        _helper("config_set", project, key=key, value=value)
        return
    _run(project, "config", "--local", key, value)
