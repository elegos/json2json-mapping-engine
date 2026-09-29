from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import track2
from cli.main import app
from cli.track2 import (
    Track2Error,
    discover_cases,
    generate_password,
    json_diff,
    safe_procedure_name,
    split_sql_script,
)


def test_split_sql_script_on_slash_lines():
    sql = "CREATE A;\nx\n/\n\nCREATE B;\n/\n"
    assert split_sql_script(sql) == ["CREATE A;\nx", "CREATE B;"]


def test_split_sql_script_ignores_slash_inside_statement():
    assert split_sql_script("SELECT 1/2;\n/\n") == ["SELECT 1/2;"]


def test_safe_procedure_name():
    sql = "CREATE OR REPLACE PROCEDURE map_x (\n) AS\n/\nCREATE OR REPLACE PROCEDURE map_x_safe (\n"
    assert safe_procedure_name(sql) == "map_x_safe"
    with pytest.raises(Track2Error):
        safe_procedure_name("CREATE OR REPLACE PROCEDURE map_x (")


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


def test_test_command_track2_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from tests.track1.cli.test_build_cli import MAPPER_TOML

    monkeypatch.chdir(tmp_path)
    (tmp_path / "mapper.toml").write_text(MAPPER_TOML)
    monkeypatch.setattr("cli.main.detect_runtime", lambda: None)
    runner = CliRunner()
    both = runner.invoke(app, ["test"])
    assert both.exit_code == 0
    assert "Track 2 unavailable" in both.output
    only2 = runner.invoke(app, ["test", "--track", "2"])
    assert only2.exit_code == 1
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
