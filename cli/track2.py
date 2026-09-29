"""Track 2 — target-environment tests (see docs/ARCHITECTURE.md, §Testing).

Detects Podman/Docker, starts an ephemeral Oracle container, deploys the
compiled `build/compiled/<mapping>.sql`, runs `map_<id>_safe` for every test
case and diffs the actual output against an optional expected file.

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
import secrets
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.build import find_source, mapping_id_of, package_name, package_path
from cli.config import MapperConfig

GOLDEN_DIR = Path("tests/golden")

_ORACLE_PORT = 1521  # plain SQL*Net listener; 1522 is the wallet/TLS one (spike-notes.md)
_SERVICE = "myatp"
_STARTUP_TIMEOUT_S = 600


class Track2Error(Exception):
    """Track 2 cannot run, or the environment failed (not a test failure)."""


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


def detect_runtime() -> str | None:
    """`podman` or `docker`, whichever is installed and answers `info`."""
    for name in ("podman", "docker"):
        if shutil.which(name) is None:
            continue
        try:
            done = subprocess.run([name, "info"], capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if done.returncode == 0:
            return name
    return None


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


@contextmanager
def ephemeral_oracle(runtime: str, config: MapperConfig, log=print) -> Iterator[Database]:
    image = _image_ref(config)
    password = generate_password()
    run = subprocess.run(
        [
            runtime, "run", "-d", "--rm",
            "-p", f"127.0.0.1::{_ORACLE_PORT}",
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
        db = Database(f"127.0.0.1:{port}/{_SERVICE}", "ADMIN", password)
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


def deploy(conn: Any, sql: str) -> None:
    """Deploy every unit; raise with USER_ERRORS text if any fails to compile
    (`CREATE OR REPLACE` with a compile error does not raise client-side)."""
    cur = conn.cursor()
    for stmt in split_sql_script(sql):
        cur.execute(stmt)
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


def run_case(conn: Any, proc: str, case: TestCase) -> CaseResult:
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

    if case.expected_path is None:
        return CaseResult(case, None, actual, rule_errors)
    expected = json.loads(case.expected_path.read_text())
    diff = json_diff(expected, actual)
    ok = not diff and not rule_errors
    msg = "" if ok else ("rule errors reported" if rule_errors and not diff else "")
    return CaseResult(case, ok, actual, rule_errors, diff, msg)


def run_track2(config: MapperConfig, mapping: str | None = None, log=print) -> list[CaseResult]:
    """Run all cases. Raises Track2Error if the environment is unusable."""
    cases = discover_cases(mapping=mapping)
    if not cases:
        return []
    runtime = detect_runtime()
    if runtime is None:
        raise Track2Error("neither podman nor docker is available")
    package_sql = package_path(config)
    if not package_sql.is_file():
        raise Track2Error(f"{package_sql} not found (run `mapper build` first)")

    import oracledb

    results: list[CaseResult] = []
    with ephemeral_oracle(runtime, config, log) as db:
        conn = oracledb.connect(user=db.user, password=db.password, dsn=db.dsn)
        try:
            deploy(conn, package_sql.read_text())
            pkg = package_name(config)
            for c in cases:
                src = find_source(c.mapping, config)
                mapping_id = mapping_id_of(src) if src else c.mapping
                results.append(run_case(conn, f"{pkg}.map_{mapping_id}_safe", c))
        finally:
            conn.close()
    return results
