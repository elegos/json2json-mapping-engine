"""`cli/gitops.py`: the same answers from the `git` binary and from gitoxide (the helper), and what
gitoxide does differently, found by trying it (docs/ARCHITECTURE.md, §Without git)."""

from __future__ import annotations

import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from cli import gitops

pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed"),
    pytest.mark.usefixtures("backend"),
]


@pytest.fixture(autouse=True)
def _git_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def git(where: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(where), *args], capture_output=True, text=True, check=True
    )
    return done.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    return root


def committed(repo: Path) -> Path:
    (repo / "a.txt").write_text("one\n")
    (repo / "sub").mkdir()
    (repo / "sub" / "b.txt").write_text("two\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    return repo


def test_a_repository_just_created_commits_its_first_commit(repo: Path) -> None:
    (repo / "a.txt").write_text("hello\n")
    assert gitops.is_repo(repo)
    assert gitops.state(repo, [])["changes"] == [{"path": "a.txt", "code": "??"}]
    done = gitops.commit(repo, ["first"], [])  # no HEAD, no index file yet
    assert done["committed"] is True
    assert git(repo, "log", "--format=%s").strip() == "first"
    assert git(repo, "status", "--porcelain") == ""
    assert gitops.show_head(repo, "a.txt") == "hello\n"
    assert gitops.show_head(repo, "nowhere.txt") is None


def test_state_names_the_changes_as_git_does(repo: Path) -> None:
    committed(repo)
    (repo / "a.txt").write_text("changed\n")
    (repo / "new.txt").write_text("new\n")
    (repo / "sub" / "b.txt").unlink()
    (repo / "staged.txt").write_text("s\n")
    git(repo, "add", "staged.txt")
    got = {c["path"]: c["code"] for c in gitops.state(repo, [])["changes"]}
    assert got == {"a.txt": " M", "new.txt": "??", "sub/b.txt": " D", "staged.txt": "A "}
    assert git(repo, "status", "--porcelain").count("\n") == len(got)


def test_a_project_in_a_folder_of_the_repository_sees_its_own_paths(repo: Path) -> None:
    committed(repo)
    (repo / "a.txt").write_text("outside\n")
    (repo / "sub" / "b.txt").write_text("inside\n")
    got = gitops.state(repo / "sub", [])
    assert got["changes"] == [{"path": "b.txt", "code": " M"}]
    assert gitops.ls_files(repo / "sub", "b.txt") == ["b.txt"]
    assert gitops.show_head(repo / "sub", "b.txt") == "two\n"


def test_add_is_seen_by_git_as_it_should(repo: Path) -> None:
    """Gitoxide leaves the index's cached trees as they were unless told: git then believed a
    modified file was new. The index it writes must read right in `git diff --cached`."""
    committed(repo)
    (repo / "sub" / "b.txt").write_text("edited\n")
    (repo / "sub" / "c.txt").write_text("new\n")
    gitops.add(repo, ["sub"])
    assert git(repo, "diff", "--cached", "--name-status").split() == [
        "A",
        "sub/c.txt",
        "M",
        "sub/b.txt",
    ] or (
        sorted(git(repo, "diff", "--cached", "--name-status").splitlines())
        == ["A\tsub/c.txt", "M\tsub/b.txt"]
    )
    assert git(repo, "status", "--porcelain").splitlines() == ["M  sub/b.txt", "A  sub/c.txt"]


def test_commit_takes_only_the_specs_and_leaves_what_else_is_staged(repo: Path) -> None:
    committed(repo)
    (repo / "sub" / "gone.txt").write_text("x\n")
    git(repo, "add", "sub/gone.txt")
    git(repo, "commit", "-qm", "gone")
    (repo / "a.txt").write_text("outside the specs\n")
    git(repo, "add", "a.txt")  # staged by someone else
    (repo / "sub" / "b.txt").write_text("in the specs\n")
    (repo / "sub" / "gone.txt").unlink()
    done = gitops.commit(repo, ["title", "body paragraph"], ["sub"])
    assert done["committed"] is True and len(done["commit"]) >= 7
    assert git(repo, "show", "--name-status", "--format=%s%n%b", "HEAD").split() == [
        "title",
        "body",
        "paragraph",
        "M",
        "sub/b.txt",
        "D",
        "sub/gone.txt",
    ]
    assert git(repo, "status", "--porcelain").strip() == "M  a.txt"  # still staged, not lost
    assert gitops.commit(repo, ["again"], ["sub"]) == {"committed": False, "commit": None}


def test_rm_cached_keeps_the_files_and_check_ignore_follows_the_rules(repo: Path) -> None:
    committed(repo)
    (repo / ".gitignore").write_text("build/\n*.log\n")
    (repo / "build").mkdir()
    (repo / "build" / "x.sql").write_text("x\n")
    assert gitops.check_ignore(repo, "build/x.sql") is True
    assert gitops.check_ignore(repo, "debug.log") is True
    assert gitops.check_ignore(repo, "sub/b.txt") is False
    assert gitops.ls_files(repo, "sub") == ["sub/b.txt"]
    gitops.rm_cached(repo, "sub")
    assert (repo / "sub" / "b.txt").is_file()
    assert git(repo, "status", "--porcelain").splitlines()[:1] == ["D  sub/b.txt"]
    assert gitops.ls_files(repo, "sub") == []


def test_config_is_read_back_exactly_by_git(repo: Path) -> None:
    value = "PYTHONPATH='/a b' run \"quoted\" %O %A; rc=$?; # not a comment\\n"
    gitops.config_set(repo, "merge.j2jme.driver", value)
    gitops.config_set(repo, "merge.j2jme.name", "J2JME")
    assert git(repo, "config", "--local", "--get", "merge.j2jme.driver").rstrip("\n") == value
    assert gitops.config_get(repo, "merge.j2jme.driver") == value
    assert gitops.config_get(repo, "merge.j2jme.nothing") == ""
    assert gitops.config_remove_section(repo, "merge", "j2jme") is True
    assert gitops.config_get(repo, "merge.j2jme.driver") == ""
    assert gitops.config_remove_section(repo, "merge", "j2jme") is False


def test_autocrlf_the_files_are_stored_as_git_stores_them(tmp_path: Path) -> None:
    """With `core.autocrlf` the repository holds LF and the work tree CRLF; a commit must store LF,
    and a pull must write CRLF, or every file would show as changed."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    one, two = tmp_path / "one", tmp_path / "two"
    for clone in (one, two):
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
        git(clone, "config", "core.autocrlf", "true")
    (one / "a.txt").write_bytes(b"x\r\ny\r\n")
    git(one, "add", "-A")
    git(one, "commit", "-qm", "base")
    git(one, "push", "-q", "origin", "HEAD:main")
    git(one, "branch", "-q", "-M", "main")
    git(one, "branch", "-q", "--set-upstream-to=origin/main")
    git(two, "pull", "-q", "origin", "main")
    git(two, "branch", "-q", "--set-upstream-to=origin/main", "main")

    (one / "a.txt").write_bytes(b"x\r\ny\r\nz\r\n")  # what an editor on Windows saves
    assert gitops.commit(one, ["z"], [])["committed"] is True
    assert git(one, "show", "HEAD:a.txt") == "x\ny\nz\n"  # LF in the repository
    assert (one / "a.txt").read_bytes() == b"x\r\ny\r\nz\r\n"  # untouched on disk
    assert git(one, "status", "--porcelain") == ""
    git(one, "push", "-q")

    assert gitops.pull(two)["ok"] is True
    assert (two / "a.txt").read_bytes() == b"x\r\ny\r\nz\r\n"  # CRLF in the work tree
    assert git(two, "status", "--porcelain") == ""


def test_push_sends_what_the_remote_lacks_and_refuses_what_is_not_a_fast_forward(
    tmp_path: Path,
) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    one, two = tmp_path / "one", tmp_path / "two"
    subprocess.run(["git", "clone", "-q", str(remote), str(one)], check=True)
    (one / "a.txt").write_text("1\n")
    git(one, "add", "-A")
    git(one, "commit", "-qm", "base")
    git(one, "push", "-q", "origin", "HEAD:main")
    git(one, "branch", "-q", "-M", "main")
    git(one, "branch", "-q", "--set-upstream-to=origin/main")
    subprocess.run(["git", "clone", "-q", str(remote), str(two)], check=True)

    (one / "deep" / "er").mkdir(parents=True)
    (one / "deep" / "er" / "f.txt").write_text("nested\n")
    (one / "a.txt").write_text("2\n")
    git(one, "add", "-A")
    git(one, "commit", "-qm", "two")
    (one / "link").symlink_to("a.txt")
    (one / "run.sh").write_text("#!/bin/sh\n")
    (one / "run.sh").chmod(0o755)
    (one / "deep" / "er" / "f.txt").unlink()
    git(one, "add", "-A")
    git(one, "commit", "-qm", "three")
    gitops.push(one)
    assert git(remote, "log", "--format=%s").split() == ["three", "two", "base"]
    subprocess.run(["git", "-C", str(remote), "fsck", "--strict"], check=True, capture_output=True)
    git(two, "pull", "-q")
    assert (two / "a.txt").read_text() == "2\n" and (two / "link").is_symlink()
    assert not (two / "deep" / "er").exists() and (two / "run.sh").stat().st_mode & 0o111
    gitops.push(one)  # nothing new: no harm

    (two / "other.txt").write_text("x\n")
    git(two, "add", "-A")
    git(two, "commit", "-qm", "other")
    git(two, "push", "-q")
    (one / "a.txt").write_text("3\n")
    git(one, "commit", "-qam", "late")
    with pytest.raises(gitops.GitError) as refused:
        gitops.push(one)
    assert not refused.value.auth  # more credentials would not help: pull first


class _Refuses(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="x"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_POST = do_GET

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def test_a_remote_that_asks_for_credentials_is_told_so(repo: Path) -> None:
    server = HTTPServer(("127.0.0.1", 0), _Refuses)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        committed(repo)
        git(repo, "remote", "add", "origin", f"http://127.0.0.1:{server.server_port}/p.git")
        git(repo, "config", "branch.main.remote", "origin")
        git(repo, "config", "branch.main.merge", "refs/heads/main")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(repo, "config", "core.askPass", "/bin/false")
        git(repo, "config", "credential.helper", "")
        with pytest.raises(gitops.GitError) as asked:
            gitops.pull(repo)
        assert asked.value.auth, str(asked.value)
    finally:
        server.shutdown()


def test_a_failing_pre_commit_hook_stops_git_and_not_gitoxide(repo: Path, backend: str) -> None:
    """Found by trying: gitoxide's commit runs no hook."""
    committed(repo)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'no' >&2\nexit 1\n")
    hook.chmod(0o755)
    (repo / "a.txt").write_text("changed\n")
    if backend == "git":
        with pytest.raises(gitops.GitError):
            gitops.commit(repo, ["x"], [])
    else:
        assert gitops.commit(repo, ["x"], [])["committed"] is True


class _BasicAuthGit(BaseHTTPRequestHandler):
    """git's smart HTTP protocol behind a user name and a password (git http-backend as CGI)."""

    root = ""
    login = ("alice", "s3cret")

    def _serve(self) -> None:
        import base64
        import os

        wanted = "Basic " + base64.b64encode(":".join(self.login).encode()).decode()
        if self.headers.get("Authorization") != wanted:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="repo"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        path, _, query = self.path.partition("?")
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            body = b""
            while True:
                size = int(self.rfile.readline().strip().split(b";")[0] or b"0", 16)
                if size == 0:
                    self.rfile.readline()
                    break
                body += self.rfile.read(size)
                self.rfile.readline()
        else:
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        env = {
            "GIT_PROJECT_ROOT": self.root,
            "GIT_HTTP_EXPORT_ALL": "1",
            "PATH_INFO": path,
            "REQUEST_METHOD": self.command,
            "QUERY_STRING": query,
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(len(body)),
            "REMOTE_USER": self.login[0],
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "HTTP_GIT_PROTOCOL": self.headers.get("Git-Protocol", ""),
            "PATH": os.environ["PATH"],
        }
        out = subprocess.run(
            ["git", "http-backend"], input=body, env=env, capture_output=True
        ).stdout
        head, _, payload = out.partition(b"\r\n\r\n")
        status, headers = 200, []
        for line in head.split(b"\r\n"):
            key, _, value = line.partition(b": ")
            if key.lower() == b"status":
                status = int(value.split()[0])
            else:
                headers.append((key.decode(), value.decode()))
        self.send_response(status)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = _serve

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def test_the_login_the_user_typed_reaches_git_and_is_not_kept(tmp_path: Path, backend: str) -> None:
    if backend != "git":
        pytest.skip(
            "gitoxide refuses a password over plain http; its path is the same code over https"
        )
    served = tmp_path / "served"
    served.mkdir()
    bare = served / "p.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    git(bare, "config", "http.receivepack", "true")
    _BasicAuthGit.root = str(served)
    server = HTTPServer(("127.0.0.1", 0), _BasicAuthGit)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/p.git"
        seed = tmp_path / "seed"
        subprocess.run(
            ["git", "clone", "-q", str(bare), str(seed)], check=True, capture_output=True
        )
        (seed / "a.txt").write_text("1\n")
        git(seed, "add", "-A")
        git(seed, "commit", "-qm", "base")
        git(seed, "push", "-q", "origin", "HEAD:main")
        clone = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True
        )
        git(clone, "remote", "set-url", "origin", url)
        git(clone, "config", "credential.helper", "")
        git(clone, "branch", "-q", "--set-upstream-to=origin/main", "main")
        (seed / "a.txt").write_text("2\n")
        git(seed, "commit", "-qam", "next")
        git(seed, "push", "-q", "origin", "HEAD:main")

        with pytest.raises(gitops.GitError) as asked:
            gitops.pull(clone)  # no login: git cannot ask anybody, and says so
        assert asked.value.auth, str(asked.value)
        wrong = {"username": "alice", "password": "nope"}
        with pytest.raises(gitops.GitError) as refused:
            gitops.pull(clone, wrong)
        assert refused.value.auth
        right = {"username": "alice", "password": "s3cret"}
        assert gitops.pull(clone, right)["ok"] is True
        assert (clone / "a.txt").read_text() == "2\n"

        (clone / "b.txt").write_text("mine\n")
        git(clone, "add", "-A")
        git(clone, "commit", "-qm", "mine")
        gitops.push(clone, right)
        assert "mine" in git(bare, "log", "--format=%s")
        assert "s3cret" not in (clone / ".git" / "config").read_text()
    finally:
        server.shutdown()
