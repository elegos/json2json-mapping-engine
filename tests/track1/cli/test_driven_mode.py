import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.main import app
from tests.track1.cli.test_build_cli import MAPPER_TOML

runner = CliRunner()

FN = """\
id: order_summary
rules:
  - id: oid
    kind: field
    field: OrderId
    type: str
    transform:
      expression: "$.id"
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "mappings" / "functional").mkdir(parents=True)
    (tmp_path / "mapper.toml").write_text(MAPPER_TOML.replace("bootstrap", "driven"))
    (tmp_path / "mappings" / "functional" / "order_summary.fn.yaml").write_text(FN)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_transpile_writes_map_py(project: Path):
    result = runner.invoke(app, ["transpile"])
    assert result.exit_code == 0, result.output
    text = (project / "build/transpiled/order_summary.map.py").read_text()
    assert "__id__ = 'order_summary'" in text
    assert "out.OrderId = oid(root)" in text


def test_build_compiles_functional_files_into_the_package(project: Path):
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output
    sql = (project / "build/compiled/map_order_summary.sql").read_text()
    assert "PROCEDURE map_order_summary (" in sql
    assert "fn_order_summary_oid" in sql
    assert runner.invoke(app, ["check"]).exit_code == 0


def test_check_detects_a_changed_functional_file(project: Path):
    runner.invoke(app, ["build"])
    fn = project / "mappings/functional/order_summary.fn.yaml"
    fn.write_text(fn.read_text().replace("$.id", "$.orderId"))
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1
    assert "out of sync" in result.output


def test_functional_error_is_reported_with_file_and_rule(project: Path):
    fn = project / "mappings/functional/order_summary.fn.yaml"
    fn.write_text(FN.replace("$.id", "@.id"))
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 1
    assert "order_summary.fn.yaml" in result.output
    assert "rule 'oid'" in result.output


def test_schema_change_invalidates_the_cache(project: Path):
    (project / "schemas").mkdir(parents=True)
    (project / "schemas/order_summary_input.schema.json").write_text(
        json.dumps({"title": "O", "type": "object", "properties": {"id": {"type": "string"}}})
    )
    assert "compiled: " in runner.invoke(app, ["build"]).output
    assert "up-to-date: " in runner.invoke(app, ["build"]).output
    (project / "schemas/order_summary_input.schema.json").write_text(
        json.dumps({"title": "O", "type": "object", "properties": {"id": {"type": "integer"}}})
    )
    assert "compiled: " in runner.invoke(app, ["build"]).output


def test_transpile_refuses_bootstrap_mode(project: Path):
    (project / "mapper.toml").write_text(MAPPER_TOML)
    result = runner.invoke(app, ["transpile"])
    assert result.exit_code == 1
    assert "driven" in result.output


def _stages(project: Path) -> list[str]:
    d = project / "build/transpiled/stages/order_summary"
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def test_no_stage_option_writes_no_artifacts(project: Path):
    assert runner.invoke(app, ["transpile"]).exit_code == 0
    assert _stages(project) == []


def test_stage_writes_artifacts_up_to_it_and_removes_later_ones(project: Path):
    assert runner.invoke(app, ["transpile", "--dump-stages"]).exit_code == 0
    assert _stages(project) == ["1-load.json", "2-build.map.py", "3-fuse.map.py", "4-emit.map.py"]
    result = runner.invoke(app, ["transpile", "--stage", "fuse"])
    assert result.exit_code == 0, result.output
    assert _stages(project) == ["1-load.json", "2-build.map.py", "3-fuse.map.py"]
    assert runner.invoke(app, ["transpile", "--stage", "1"]).exit_code == 0
    assert _stages(project) == ["1-load.json"]


def test_cached_resumes_from_previous_stage(project: Path):
    assert runner.invoke(app, ["transpile", "--stage", "build"]).exit_code == 0
    build = project / "build/transpiled/stages/order_summary/2-build.map.py"
    build.write_text(build.read_text() + "# marker-from-artifact\n")
    assert runner.invoke(app, ["transpile", "--stage", "fuse", "--cached"]).exit_code == 0
    fused = project / "build/transpiled/stages/order_summary/3-fuse.map.py"
    assert "# marker-from-artifact" in fused.read_text()  # read from the artifact
    out = runner.invoke(app, ["transpile", "--stage", "emit", "--cached"])
    assert out.exit_code == 0, out.output
    assert (project / "build/transpiled/order_summary.map.py").is_file()


def test_cached_without_previous_artifact_runs_from_the_start(project: Path):
    result = runner.invoke(app, ["transpile", "--stage", "fuse", "--cached"])
    assert result.exit_code == 0, result.output
    assert "running from stage 1" in result.output
    assert _stages(project) == ["1-load.json", "2-build.map.py", "3-fuse.map.py"]


def test_stage_option_errors(project: Path):
    assert runner.invoke(app, ["transpile", "--cached"]).exit_code == 2
    assert runner.invoke(app, ["transpile", "--stage", "9"]).exit_code == 2
