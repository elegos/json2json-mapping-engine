"""PL/SQL integration tests (track 2): an ephemeral Oracle container, the compiled packages
deployed to it, `map_<id>_safe` run for every golden case (docs/ARCHITECTURE.md, §Testing).

Detects Podman/Docker, starts the container from `[target.plsql.test]`
(`container_image`, `container_tag`), deploys the compiled `build/compiled/*.sql`, runs
`map_<id>_safe` for every test case and judges the output (`compiler.backends.integration`). The
raising twin `map_<id>` is then run on the same input and must agree with `_safe`: it succeeds
with the same output when `_safe` reported no rule errors, and raises the reserved error code
(payload `total_errors` = number of rule errors) otherwise.

The generated packages are deployed once, in the backend's deploy order; each case calls
`map_<id>_safe` through the package a caller uses (the index package when there is one, else the
mapping's own).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from compiler.backends.integration import (
    CaseResult,
    IntegrationContext,
    IntegrationError,
    TestCase,
    json_diff,
    judge,
)
from compiler.backends.plsql.naming import PlsqlNaming

DEFAULT_IMAGE = "container-registry.oracle.com/database/adb-free"
DEFAULT_TAG = "latest-23ai"
_ORACLE_PORT = 1521  # plain SQL*Net listener; 1522 is the wallet/TLS one (spike-notes.md)
_SERVICE = "myatp"
_STARTUP_TIMEOUT_S = 600


def split_sql_script(sql: str) -> list[str]:
    """Split a SQL*Plus-style script into statements: a line holding only `/`
    terminates a PL/SQL unit. The generated files contain nothing else."""
    statements: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        if line.strip() == "/":
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(line)
    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def generate_password() -> str:
    # Image verifier: 12-30 chars, upper+lower+digit, no literal "admin" (spike-notes.md).
    return "Mp1" + secrets.token_hex(8)


def _info_cmd(name: str) -> list[str]:
    # A bare `docker info` can exit 1 ("errors pretty printing info", e.g. a
    # broken CLI plugin) while the daemon is perfectly reachable; asking for
    # one server field only tests the connection.
    return [name, "info", "--format", "{{.ServerVersion}}"] if name == "docker" else [name, "info"]


def detect_runtime() -> str | None:
    """`podman` or `docker`, whichever is installed and answers `info`."""
    for name in ("podman", "docker"):
        if shutil.which(name) is None:
            continue
        try:
            done = subprocess.run(_info_cmd(name), capture_output=True, timeout=30)
        except OSError, subprocess.TimeoutExpired:
            continue
        # docker-cli 26 can exit 0 with an empty --format result when the daemon is
        # unreachable, so a docker answer counts only if it printed a server version.
        if done.returncode == 0 and (name != "docker" or done.stdout.strip()):
            return name
    return None


def runtime_diagnostic() -> str:
    """Why `detect_runtime` found nothing (for the 'unavailable' message)."""
    lines = []
    for name in ("podman", "docker"):
        path = shutil.which(name)
        if path is None:
            lines.append(f"{name}: not in PATH")
            continue
        try:
            done = subprocess.run(_info_cmd(name), capture_output=True, text=True, timeout=30)
            err = (done.stderr or done.stdout).strip().splitlines()
            lines.append(
                f"{name}: `info` exit {done.returncode}, "
                f"stdout {done.stdout.strip()!r}: {err[-1] if err else ''}"
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            lines.append(f"{name}: `info` failed: {exc}")
    lines.append(f"DOCKER_HOST={os.environ.get('DOCKER_HOST', '<unset>')}")
    return "; ".join(lines)


def _image_ref(test: Mapping[str, Any]) -> str:
    """The image to start: what `[target.plsql.test]` says, else the backend's defaults (the tag
    only follows the image when the image is not the default one too: a custom image without a
    tag is run as it is)."""
    image = test.get("container_image") or DEFAULT_IMAGE
    tag = test.get("container_tag") or (DEFAULT_TAG if image == DEFAULT_IMAGE else None)
    return f"{image}:{tag}" if tag else image


@dataclass
class Database:
    dsn: str
    user: str
    password: str


def remote_daemon_host(env: Mapping[str, str] | None = None) -> str | None:
    """Host of a remote Docker daemon (`DOCKER_HOST=tcp://host:port`), else None.

    With a remote daemon (e.g. a dind sidecar in CI) published ports live on
    the daemon's host, not on this process's loopback."""
    value = (os.environ if env is None else env).get("DOCKER_HOST", "")
    if not value.startswith(("tcp://", "ssh://")):
        return None
    return urlparse(value).hostname


@contextmanager
def ephemeral_oracle(runtime: str, test: Mapping[str, Any], log=print) -> Iterator[Database]:
    image = _image_ref(test)
    password = generate_password()
    remote = remote_daemon_host()
    bind = "0.0.0.0" if remote else "127.0.0.1"
    run = subprocess.run(
        [
            runtime, "run", "-d", "--rm",
            "-p", f"{bind}::{_ORACLE_PORT}",
            "-e", f"ADMIN_PASSWORD={password}",
            "-e", f"WALLET_PASSWORD={password}",
            image,
        ],
        capture_output=True,
        text=True,
    )  # fmt: skip
    if run.returncode != 0:
        raise IntegrationError(f"{runtime} run failed: {run.stderr.strip()}")
    cid = run.stdout.strip().splitlines()[-1]
    try:
        port = subprocess.run(
            [runtime, "port", cid, f"{_ORACLE_PORT}/tcp"], capture_output=True, text=True
        ).stdout.strip().splitlines()[0].rsplit(":", 1)[1]  # fmt: skip
        db = Database(f"{remote or '127.0.0.1'}:{port}/{_SERVICE}", "ADMIN", password)
        log(f"container {cid[:12]} started from {image}; waiting for the database...")
        _wait_ready(db)
        yield db
    finally:
        subprocess.run([runtime, "rm", "-f", cid], capture_output=True)


def _wait_ready(db: Database) -> None:
    import oracledb

    deadline = time.monotonic() + _STARTUP_TIMEOUT_S
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            oracledb.connect(user=db.user, password=db.password, dsn=db.dsn).close()
            return
        except oracledb.Error as exc:
            last = exc
            time.sleep(5)
    raise IntegrationError(f"database not ready after {_STARTUP_TIMEOUT_S}s: {last}")


def deploy(conn: Any, sql: str, schema: str | None = None) -> None:
    """Deploy every unit; raise with the error text if any fails to compile
    (`CREATE OR REPLACE` with a compile error does not raise client-side).

    With `schema` the packages are created as `<schema>.<package>`: the schema
    is created first (no login, ephemeral database) unless it already exists,
    and compile errors are read from that owner. Connecting as ADMIN, which
    holds the `CREATE ANY PROCEDURE` this needs."""
    cur = conn.cursor()
    owner = None
    if schema:
        owner = schema.upper()
        cur.execute(
            "BEGIN EXECUTE IMMEDIATE 'CREATE USER " + owner + " NO AUTHENTICATION'; "
            "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1920 THEN RAISE; END IF; END;"
        )
    for stmt in split_sql_script(sql):
        cur.execute(stmt)
    if owner:
        cur.execute(
            "SELECT name, line, position, text FROM all_errors "
            "WHERE owner = :o AND attribute = 'ERROR' ORDER BY name, sequence",
            o=owner,
        )
    else:
        cur.execute(
            "SELECT name, line, position, text FROM user_errors "
            "WHERE attribute = 'ERROR' ORDER BY name, sequence"
        )
    errs = cur.fetchall()
    if errs:
        detail = "\n".join(f"  {n} {ln}:{pos} {txt}" for n, ln, pos, txt in errs)
        raise IntegrationError(f"compiled SQL failed to compile on the target:\n{detail}")


def _lob_text(v: Any) -> str | None:
    return v.read() if hasattr(v, "read") else v


def check_raising(
    conn: Any,
    proc: str,
    case: TestCase,
    safe_out: Any,
    rule_errors: list[dict[str, Any]],
    error_code: int,
    report: list[dict[str, Any]] | None = None,
) -> str:
    """Run the raising twin `proc` and compare with the `_safe` result.
    Returns "" when consistent, else a description of the mismatch."""
    rejected = sorted(i["code"] for i in report or [] if i["action"] == "reject")
    import oracledb

    cur = conn.cursor()
    src = conn.createlob(oracledb.DB_TYPE_CLOB, case.input_path.read_text())
    out = cur.var(oracledb.DB_TYPE_CLOB)
    try:
        cur.execute(f"BEGIN {proc}(:s, :o); END;", s=src, o=out)
    except oracledb.Error as exc:
        (err,) = exc.args
        code = getattr(err, "code", None)
        if not rule_errors and not rejected:
            return f"{proc} raised but _safe reported no rule errors: {exc}"
        if code != abs(error_code) and code != error_code:
            return f"{proc} raised ORA{code}, expected {error_code}: {exc}"
        try:
            # the message is "ORA-20000: <json>" followed by ORA-06512 stack lines
            payload = json.loads(str(err.message).splitlines()[0].split(": ", 1)[-1])
        except ValueError:
            return f"{proc} error payload is not JSON: {exc}"
        if rejected:
            raised = sorted(c["code"] for c in payload.get("checks", []) if c["action"] == "reject")
            if not payload.get("rejected") or raised != rejected:
                return f"{proc} rejected by {raised}, _safe by {rejected}"
            return ""
        if payload.get("total_errors") != len(rule_errors):
            return (
                f"{proc} payload total_errors={payload.get('total_errors')}, "
                f"_safe reported {len(rule_errors)}"
            )
        return ""
    if rejected:
        return f"{proc} did not raise but _safe rejected the input ({rejected})"
    if rule_errors:
        return f"{proc} did not raise but _safe reported {len(rule_errors)} rule error(s)"
    actual = json.loads(_lob_text(out.getvalue()) or "null")
    diff = json_diff(safe_out, actual)
    return f"{proc} output differs from _safe:\n{diff}" if diff else ""


def check_parallel_wrapper(conn: Any, fn: str, case: TestCase, safe_out: Any) -> str:
    """Call the SQL-callable `PARALLEL_ENABLE` wrapper `fn` from a query (the way it
    is meant to be used) and compare with the `_safe` result. "" = consistent."""
    import oracledb

    cur = conn.cursor()
    src = conn.createlob(oracledb.DB_TYPE_CLOB, case.input_path.read_text())
    try:
        cur.execute(f"SELECT {fn}(:s) FROM dual", s=src)
        (row,) = cur.fetchall()
    except oracledb.Error as exc:
        return f"{fn} failed from SQL: {exc}"
    diff = json_diff(safe_out, json.loads(_lob_text(row[0]) or "null"))
    return f"{fn} output differs from _safe:\n{diff}" if diff else ""


def run_case(
    conn: Any,
    proc: str,
    case: TestCase,
    raising_proc: str | None = None,
    error_code: int = -20000,
    sql_fn: str | None = None,
    validated: bool = False,
) -> CaseResult:
    """`validated`: the mapping checks its input / output, so `_safe` has a fourth OUT parameter,
    the report, and gives no output for a rejected document."""
    import oracledb

    cur = conn.cursor()
    src = conn.createlob(oracledb.DB_TYPE_CLOB, case.input_path.read_text())
    out = cur.var(oracledb.DB_TYPE_CLOB)
    err = cur.var(oracledb.DB_TYPE_CLOB)
    rep = cur.var(oracledb.DB_TYPE_CLOB)
    try:
        if validated:
            cur.execute(f"BEGIN {proc}(:s, :o, :e, :r); END;", s=src, o=out, e=err, r=rep)
        else:
            cur.execute(f"BEGIN {proc}(:s, :o, :e); END;", s=src, o=out, e=err)
    except oracledb.Error as exc:
        return CaseResult(case, False, message=f"procedure raised: {exc}")
    out_text, err_text = out.getvalue(), err.getvalue()
    out_raw = out_text.read() if hasattr(out_text, "read") else out_text
    actual = json.loads(out_raw) if out_raw else None
    err_raw = err_text.read() if hasattr(err_text, "read") else err_text
    rule_errors = json.loads(err_raw) if err_raw else []
    report = None
    if validated:
        rep_text = rep.getvalue()
        rep_raw = rep_text.read() if hasattr(rep_text, "read") else rep_text
        report = json.loads(rep_raw) if rep_raw else []

    twin = (
        check_raising(conn, raising_proc, case, actual, rule_errors, error_code, report)
        if raising_proc
        else ""
    )
    rejected = any(i["action"] == "reject" for i in report or [])
    if (
        sql_fn and not rule_errors and not twin and not rejected
    ):  # the wrapper raises on a failing document
        twin = check_parallel_wrapper(conn, sql_fn, case, actual)
    return judge(case, actual, rule_errors, twin, report)


def _reports(package_text: str, safe_name: str) -> bool:
    """Whether the `_safe` procedure `safe_name` has the report parameter (the mapping validates)."""
    found = re.search(rf"PROCEDURE {re.escape(safe_name)} \(([^)]*)\)", package_text)
    return found is not None and "p_report OUT CLOB" in found.group(1)


def integration_unavailable() -> str | None:
    """Why the tests cannot run here: no `oracledb` (a development dependency, not shipped with
    the tool), or no container runtime answers."""
    if importlib.util.find_spec("oracledb") is None:
        return "the oracledb package is not installed (it is in the `dev` dependency group)"
    if detect_runtime() is not None:
        return None
    return f"no podman/docker available\n  {runtime_diagnostic()}"


def run_integration(config: Mapping[str, Any], context: IntegrationContext) -> list[CaseResult]:
    """Run the cases of `context` against an ephemeral Oracle; `config` is the validated
    `[target.plsql]` section (the container to start is under its `test` table)."""
    if not context.cases:
        return []
    runtime = detect_runtime()
    if runtime is None:
        raise IntegrationError("neither podman nor docker is available")
    package_text = "\n".join(context.files.values())

    import oracledb

    results: list[CaseResult] = []
    with ephemeral_oracle(runtime, config.get("test") or {}, context.log) as db:
        conn = oracledb.connect(user=db.user, password=db.password, dsn=db.dsn)
        try:
            naming = PlsqlNaming.from_config(dict(config))
            deploy(conn, package_text, naming.schema)
            for c in context.cases:
                mapping_id = context.mapping_ids.get(c.mapping, c.mapping)
                results.append(
                    run_case(
                        conn,
                        naming.call_path(mapping_id, "_safe"),
                        c,
                        raising_proc=naming.call_path(mapping_id),
                        error_code=int(config["error_code"]),
                        sql_fn=(
                            naming.call_path(mapping_id, "_fn")
                            if f"FUNCTION {naming.entry(mapping_id, '_fn')} " in package_text
                            else None
                        ),
                        validated=_reports(package_text, naming.entry(mapping_id, "_safe")),
                    )
                )
        finally:
            conn.close()
    return results
