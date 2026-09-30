"""Integration tests (track 2) — target-environment tests (see docs/ARCHITECTURE.md, §Testing).

Detects Podman/Docker, starts an ephemeral Oracle container, deploys the
compiled `build/compiled/<mapping>.sql`, runs `map_<id>_safe` for every test
case and diffs the actual output against an optional expected file. The raising
twin `map_<id>` is then run on the same input and must agree with `_safe`:
it succeeds with the same output when `_safe` reported no rule errors, and
raises the reserved error code (payload `total_errors` = number of rule
errors) otherwise.

Case layout (per mapping, by basename of `mappings/<name>.map.py`):

    tests/golden/<name>/<case>.input.json      required
    tests/golden/<name>/<case>.expected.json   optional — omitted = display only

The project's single generated package (`build/compiled/<package>.sql`) is
deployed once; each case calls `<package>.map_<id>_safe`. Rule functions are
namespaced `fn_<mapping_id>_<rule_id>`, so mappings never collide.
"""

from __future__ import annotations

import difflib
import json
import os
import secrets
import shutil
import subprocess
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cli.allowed import check_allowed, collect_constraints, unsupported_keywords
from cli.build import artifact_path, find_source, is_functional, mapping_id_of
from cli.config import MapperConfig
from compiler.backends.plsql.naming import PlsqlNaming
from transpiler.model import load_functional_file

GOLDEN_DIR = Path("tests/golden")

_ORACLE_PORT = 1521  # plain SQL*Net listener; 1522 is the wallet/TLS one (spike-notes.md)
_SERVICE = "myatp"
_STARTUP_TIMEOUT_S = 600


class Track2Error(Exception):
    """The integration tests cannot run, or the environment failed (not a test failure)."""


# --------------------------------------------------------------------------
# Pure helpers (no runtime needed)
# --------------------------------------------------------------------------


@dataclass
class TestCase:
    mapping: str
    name: str
    input_path: Path
    expected_path: Path | None


def discover_cases(golden_dir: Path = GOLDEN_DIR, mapping: str | None = None) -> list[TestCase]:
    if not golden_dir.is_dir():
        return []
    cases: list[TestCase] = []
    for mdir in sorted(p for p in golden_dir.iterdir() if p.is_dir()):
        if mapping is not None and mdir.name != mapping:
            continue
        for inp in sorted(mdir.glob("*.input.json")):
            name = inp.name.removesuffix(".input.json")
            expected = mdir / f"{name}.expected.json"
            cases.append(TestCase(mdir.name, name, inp, expected if expected.is_file() else None))
    return cases


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


def json_diff(expected: Any, actual: Any) -> str:
    """Unified diff of canonical (key-sorted) JSON; empty string = equal."""

    def dump(v: Any) -> list[str]:
        return json.dumps(v, indent=2, sort_keys=True, ensure_ascii=False).splitlines()

    return "\n".join(
        difflib.unified_diff(dump(expected), dump(actual), "expected", "actual", lineterm="")
    )


def generate_password() -> str:
    # Image verifier: 12-30 chars, upper+lower+digit, no literal "admin" (spike-notes.md).
    return "Mp1" + secrets.token_hex(8)


# --------------------------------------------------------------------------
# Container runtime
# --------------------------------------------------------------------------


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
        except (OSError, subprocess.TimeoutExpired):
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


def _image_ref(config: MapperConfig) -> str:
    image, tag = config.test.container_image, config.test.container_tag
    if not image:
        raise Track2Error("[test] container_image is not set in mapper.toml")
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
def ephemeral_oracle(runtime: str, config: MapperConfig, log=print) -> Iterator[Database]:
    image = _image_ref(config)
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
        raise Track2Error(f"{runtime} run failed: {run.stderr.strip()}")
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
    raise Track2Error(f"database not ready after {_STARTUP_TIMEOUT_S}s: {last}")


# --------------------------------------------------------------------------
# Deploy + run
# --------------------------------------------------------------------------


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
        raise Track2Error(f"compiled SQL failed to compile on the target:\n{detail}")


@dataclass
class CaseResult:
    case: TestCase
    passed: bool | None  # None = no expected file, output shown for inspection
    output: Any = None
    rule_errors: list[dict[str, Any]] = field(default_factory=list)
    diff: str = ""
    message: str = ""
    warnings: list[str] = field(default_factory=list)  # `allowed` violations


def _lob_text(v: Any) -> str | None:
    return v.read() if hasattr(v, "read") else v


def check_raising(
    conn: Any,
    proc: str,
    case: TestCase,
    safe_out: Any,
    rule_errors: list[dict[str, Any]],
    error_code: int,
) -> str:
    """Run the raising twin `proc` and compare with the `_safe` result.
    Returns "" when consistent, else a description of the mismatch."""
    import oracledb

    cur = conn.cursor()
    src = conn.createlob(oracledb.DB_TYPE_CLOB, case.input_path.read_text())
    out = cur.var(oracledb.DB_TYPE_CLOB)
    try:
        cur.execute(f"BEGIN {proc}(:s, :o); END;", s=src, o=out)
    except oracledb.Error as exc:
        (err,) = exc.args
        code = getattr(err, "code", None)
        if not rule_errors:
            return f"{proc} raised but _safe reported no rule errors: {exc}"
        if code != abs(error_code) and code != error_code:
            return f"{proc} raised ORA{code}, expected {error_code}: {exc}"
        try:
            payload = json.loads(str(err.message).split(": ", 1)[-1])
        except ValueError:
            return f"{proc} error payload is not JSON: {exc}"
        if payload.get("total_errors") != len(rule_errors):
            return (
                f"{proc} payload total_errors={payload.get('total_errors')}, "
                f"_safe reported {len(rule_errors)}"
            )
        return ""
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
    constraints: dict[tuple[str, ...], dict[str, Any]] | None = None,
    sql_fn: str | None = None,
) -> CaseResult:
    import oracledb

    cur = conn.cursor()
    src = conn.createlob(oracledb.DB_TYPE_CLOB, case.input_path.read_text())
    out = cur.var(oracledb.DB_TYPE_CLOB)
    err = cur.var(oracledb.DB_TYPE_CLOB)
    try:
        cur.execute(f"BEGIN {proc}(:s, :o, :e); END;", s=src, o=out, e=err)
    except oracledb.Error as exc:
        return CaseResult(case, False, message=f"procedure raised: {exc}")
    out_text, err_text = out.getvalue(), err.getvalue()
    actual = json.loads(out_text.read() if hasattr(out_text, "read") else out_text)
    err_raw = err_text.read() if hasattr(err_text, "read") else err_text
    rule_errors = json.loads(err_raw) if err_raw else []

    warnings = (
        [*unsupported_keywords(constraints), *check_allowed(actual, constraints)]
        if constraints
        else []
    )
    twin = (
        check_raising(conn, raising_proc, case, actual, rule_errors, error_code)
        if raising_proc
        else ""
    )
    if sql_fn and not rule_errors and not twin:  # the wrapper raises on a failing document
        twin = check_parallel_wrapper(conn, sql_fn, case, actual)
    if case.expected_path is None:
        if twin:
            return CaseResult(case, False, actual, rule_errors, message=twin, warnings=warnings)
        return CaseResult(case, None, actual, rule_errors, warnings=warnings)
    expected = json.loads(case.expected_path.read_text())
    diff = json_diff(expected, actual)
    ok = not diff and not rule_errors and not twin
    msg = twin or ("rule errors reported" if rule_errors and not diff else "")
    return CaseResult(case, ok, actual, rule_errors, diff, msg, warnings)


def run_track2(config: MapperConfig, mapping: str | None = None, log=print) -> list[CaseResult]:
    """Run all cases. Raises Track2Error if the environment is unusable."""
    cases = discover_cases(mapping=mapping)
    if not cases:
        return []
    runtime = detect_runtime()
    if runtime is None:
        raise Track2Error("neither podman nor docker is available")
    package_sql = artifact_path(config)
    if not package_sql.is_file():
        raise Track2Error(f"{package_sql} not found (run `mapper build` first)")

    import oracledb

    results: list[CaseResult] = []
    with ephemeral_oracle(runtime, config, log) as db:
        conn = oracledb.connect(user=db.user, password=db.password, dsn=db.dsn)
        try:
            naming = PlsqlNaming.from_config(config.target_config())
            package_text = package_sql.read_text()
            deploy(conn, package_text, naming.schema)
            for c in cases:
                src = find_source(c.mapping, config)
                mapping_id = mapping_id_of(src) if src else c.mapping
                constraints = (
                    collect_constraints(load_functional_file(src))
                    if src and is_functional(src)
                    else None
                )
                results.append(
                    run_case(
                        conn,
                        naming.call_path(mapping_id, "_safe"),
                        c,
                        raising_proc=naming.call_path(mapping_id),
                        error_code=int(config.target_config()["error_code"]),
                        constraints=constraints,
                        sql_fn=(
                            naming.call_path(mapping_id, "_fn")
                            if f"FUNCTION {naming.entry(mapping_id, '_fn')} " in package_text
                            else None
                        ),
                    )
                )
        finally:
            conn.close()
    return results
