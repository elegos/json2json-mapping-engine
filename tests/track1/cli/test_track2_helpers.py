from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import track2
from cli.main import app
from cli.track2 import (
    discover_cases,
    generate_password,
    json_diff,
    split_sql_script,
)


def test_split_sql_script_on_slash_lines():
    sql = "CREATE A;\nx\n/\n\nCREATE B;\n/\n"
    assert split_sql_script(sql) == ["CREATE A;\nx", "CREATE B;"]


def test_split_sql_script_ignores_slash_inside_statement():
    assert split_sql_script("SELECT 1/2;\n/\n") == ["SELECT 1/2;"]


def test_json_diff_ignores_key_order():
    assert json_diff({"a": 1, "b": 2}, {"b": 2, "a": 1}) == ""
    assert '-  "a": 1' in json_diff({"a": 1}, {"a": 2})


def test_generate_password_meets_image_rules():
    pw = generate_password()
    assert 12 <= len(pw) <= 30
    assert "admin" not in pw.lower()
    assert any(c.isupper() for c in pw) and any(c.islower() for c in pw)
    assert any(c.isdigit() for c in pw)


def test_discover_cases(tmp_path: Path):
    d = tmp_path / "golden" / "order"
    d.mkdir(parents=True)
    (d / "a.input.json").write_text("{}")
    (d / "a.expected.json").write_text("{}")
    (d / "b.input.json").write_text("{}")
    (tmp_path / "golden" / "other").mkdir()
    (tmp_path / "golden" / "other" / "c.input.json").write_text("{}")
    cases = discover_cases(tmp_path / "golden")
    assert [(c.mapping, c.name, c.expected_path is not None) for c in cases] == [
        ("order", "a", True),
        ("order", "b", False),
        ("other", "c", False),
    ]
    assert [c.mapping for c in discover_cases(tmp_path / "golden", "other")] == ["other"]
    assert discover_cases(tmp_path / "missing") == []


def test_discover_cases_reads_expected_errors(tmp_path: Path):
    d = tmp_path / "golden" / "order"
    d.mkdir(parents=True)
    (d / "a.input.json").write_text("{}")
    (d / "a.expected_errors.json").write_text('["unit_price"]')
    (d / "b.input.json").write_text("{}")
    a, b = discover_cases(tmp_path / "golden")
    assert a.expected_errors == ["unit_price"]
    assert b.expected_errors is None


def test_test_command_track2_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from tests.track1.cli.test_build_cli import MAPPER_TOML

    monkeypatch.chdir(tmp_path)
    (tmp_path / "mapper.toml").write_text(MAPPER_TOML)
    monkeypatch.setattr("cli.main.detect_runtime", lambda: None)
    runner = CliRunner()
    both = runner.invoke(app, ["test"])
    assert both.exit_code == 0
    assert "integration tests unavailable" in both.output
    assert "== Offline tests ==" in both.output
    only2 = runner.invoke(app, ["test", "--track", "2"])
    assert only2.exit_code == 1
    assert runner.invoke(app, ["test", "--integration"]).exit_code == 1
    assert runner.invoke(app, ["test", "--offline", "--integration"]).exit_code == 2
    assert runner.invoke(app, ["test", "--track", "3"]).exit_code == 2


def test_run_track2_without_cases_needs_no_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from cli.config import parse_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(track2, "detect_runtime", lambda: pytest.fail("must not probe"))
    cfg = parse_config(
        {
            "project": {"mode": "bootstrap"},
            "target": {
                "plsql": {"schema": "S", "package": "P", "fn_package": "F", "error_code": -20000}
            },
        }
    )
    assert track2.run_track2(cfg) == []


def test_remote_daemon_host():
    assert track2.remote_daemon_host({"DOCKER_HOST": "tcp://docker:2375"}) == "docker"
    assert track2.remote_daemon_host({"DOCKER_HOST": "unix:///var/run/docker.sock"}) is None
    assert track2.remote_daemon_host({}) is None


class _FakeVar:
    def __init__(self, text: str):
        self._text = text

    def getvalue(self) -> str:
        return self._text


class _FakeCursor:
    def __init__(self, raises: Exception | None, out: str):
        self._raises, self._out = raises, out

    def var(self, _type):
        return _FakeVar(self._out)

    def execute(self, *_a, **_k):
        if self._raises:
            raise self._raises

    def fetchall(self):
        return [(self._out,)]


class _FakeConn:
    def __init__(self, raises: Exception | None = None, out: str = "{}"):
        self._cur = _FakeCursor(raises, out)

    def cursor(self):
        return self._cur

    def createlob(self, _type, text):
        return text


def _case(tmp_path: Path) -> track2.TestCase:
    p = tmp_path / "a.input.json"
    p.write_text("{}")
    return track2.TestCase("m", "a", p, None)


def test_check_raising_agrees_on_success(tmp_path: Path):
    conn = _FakeConn(out='{"a": 1}')
    assert track2.check_raising(conn, "P.map_m", _case(tmp_path), {"a": 1}, [], -20000) == ""
    msg = track2.check_raising(conn, "P.map_m", _case(tmp_path), {"a": 2}, [], -20000)
    assert "differs from _safe" in msg


def test_check_raising_flags_missing_raise(tmp_path: Path):
    conn = _FakeConn()
    msg = track2.check_raising(conn, "P.map_m", _case(tmp_path), {}, [{"rule": "r"}], -20000)
    assert "did not raise" in msg


def test_check_raising_validates_error_payload(tmp_path: Path):
    import oracledb

    class _Err:
        code = 20000
        message = 'ORA-20000: {"total_errors": 1, "errors": []}'

    exc = oracledb.DatabaseError(_Err())
    case = _case(tmp_path)
    ok = track2.check_raising(_FakeConn(exc), "P.map_m", case, {}, [{"rule": "r"}], -20000)
    assert ok == ""
    bad = track2.check_raising(_FakeConn(exc), "P.map_m", case, {}, [{}, {}], -20000)
    assert "total_errors=1" in bad
    stacked = type("E", (), {"code": 20000, "message": _Err.message + "\nORA-06512: at line 1"})
    with_stack = oracledb.DatabaseError(stacked())
    ok_stack = track2.check_raising(_FakeConn(with_stack), "P.map_m", case, {}, [{}], -20000)
    assert ok_stack == ""
    unexpected = track2.check_raising(_FakeConn(exc), "P.map_m", case, {}, [], -20000)
    assert "raised but _safe reported no rule errors" in unexpected


def test_check_parallel_wrapper_compares_with_safe(tmp_path: Path):
    conn = _FakeConn(out='{"a": 1}')
    case = _case(tmp_path)
    assert track2.check_parallel_wrapper(conn, "P.map_m_fn", case, {"a": 1}) == ""
    assert "differs from _safe" in track2.check_parallel_wrapper(conn, "P.map_m_fn", case, {"a": 2})


def test_check_parallel_wrapper_reports_sql_failure(tmp_path: Path):
    import oracledb

    class _Err:
        code = 904
        message = "ORA-00904: invalid identifier"

    conn = _FakeConn(oracledb.DatabaseError(_Err()))
    msg = track2.check_parallel_wrapper(conn, "P.map_m_fn", _case(tmp_path), {})
    assert "failed from SQL" in msg
