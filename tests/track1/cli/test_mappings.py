"""Create, delete and rename a mapping (`cli/mappings.py`)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.main import app
from cli.mappings import create_mapping, delete_mapping, removal_plan, rename_mapping
from cli.serve import serve
from tests.track1.cli.test_build_cli import MAPPER_TOML
from transpiler.model import FnYamlError, load_functional_file

runner = CliRunner()

SCHEMA = '{"type": "object", "properties": {"a": {"type": "string"}}}'


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "mapper.toml").write_text(MAPPER_TOML.replace("bootstrap", "driven"))
    return tmp_path


def _touch(project: Path, *names: str) -> None:
    for name in names:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SCHEMA if name.endswith(".json") else "x")


def test_a_new_mapping_loads_empty_and_building_it_says_so(project: Path, monkeypatch) -> None:
    assert create_mapping(project, "orders") == "mappings/functional/orders.fn.yaml"
    tree = load_functional_file(project / "mappings/functional/orders.fn.yaml")
    assert (tree.id, tree.name, tree.rules) == ("orders", "orders", [])
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 1 and "is empty" in result.output
    with pytest.raises(FnYamlError, match="already a mapping"):
        create_mapping(project, "orders")
    for bad in ("1abc", "a-b", "", "a b"):
        with pytest.raises(FnYamlError, match="not a valid mapping name"):
            create_mapping(project, bad)


def test_delete_takes_the_sources_and_what_was_derived_but_not_the_golden_cases(
    project: Path,
) -> None:
    create_mapping(project, "orders")
    create_mapping(project, "other")
    _touch(
        project,
        "schemas/orders_input.schema.json",
        "schemas/orders_output.schema.json",
        "schemas/other_input.schema.json",
        "build/transpiled/orders.map.py",
        "build/transpiled/stages/orders/1-load.json",
        "build/cache/orders.fn.yaml.unit.json",
        "generated/stubs/orders.pyi",
        "generated/dataclasses/orders.py",
        "tests/golden/orders/a.input.json",
    )
    plan = removal_plan(project, "orders")
    assert plan[0] == "mappings/functional/orders.fn.yaml"
    assert "tests/golden/orders/a.input.json" not in " ".join(plan) and len(plan) == 8
    assert delete_mapping(project, "orders") == plan
    assert not any((project / p).exists() for p in plan)
    assert (project / "tests/golden/orders/a.input.json").exists()
    assert (project / "schemas/other_input.schema.json").exists()  # another mapping's
    assert (project / "mappings/functional/other.fn.yaml").exists()
    with pytest.raises(FnYamlError, match="no mapping called"):
        removal_plan(project, "orders")


def test_rename_moves_the_schemas_the_golden_folder_and_follows_the_id(project: Path) -> None:
    create_mapping(project, "orders")
    _touch(
        project,
        "schemas/orders_input.schema.json",
        "build/transpiled/orders.map.py",
        "tests/golden/orders/a.input.json",
    )
    assert rename_mapping(project, "orders", "invoices") == {
        "name": "invoices",
        "file_id": "invoices",
    }
    assert not (project / "mappings/functional/orders.fn.yaml").exists()
    tree = load_functional_file(project / "mappings/functional/invoices.fn.yaml")
    assert (tree.id, tree.name) == ("invoices", "invoices")
    assert (project / "schemas/invoices_input.schema.json").is_file()
    assert not (project / "schemas/orders_input.schema.json").exists()
    assert (project / "tests/golden/invoices/a.input.json").is_file()
    assert not (
        project / "build/transpiled/orders.map.py"
    ).exists()  # derived: made again by a build


def test_the_id_stays_when_it_was_chosen_and_can_be_set_by_hand(project: Path) -> None:
    create_mapping(project, "orders")
    path = project / "mappings/functional/orders.fn.yaml"
    path.write_text(path.read_text().replace("id: orders", "id: custom"))
    assert rename_mapping(project, "orders", "invoices")["file_id"] == "custom"
    assert rename_mapping(project, "invoices", "invoices", new_id="billing") == {
        "name": "invoices",
        "file_id": "billing",
    }
    assert rename_mapping(project, "invoices", "bills", new_id="other")["file_id"] == "other"
    with pytest.raises(FnYamlError, match="not a valid mapping name"):
        rename_mapping(project, "bills", "bills", new_id="no good")


def test_rename_follows_a_schemas_entry_that_named_the_convention_file(project: Path) -> None:
    create_mapping(project, "orders")
    path = project / "mappings/functional/orders.fn.yaml"
    path.write_text(
        path.read_text()
        + "schemas:\n  input: schemas/orders_input.schema.json\n  output: contracts/x.json\n"
    )
    rename_mapping(project, "orders", "invoices")
    schemas = load_functional_file(project / "mappings/functional/invoices.fn.yaml").schemas
    assert (schemas.input, schemas.output) == (
        "schemas/invoices_input.schema.json",
        "contracts/x.json",
    )


def test_a_rename_that_cannot_be_done_changes_nothing(project: Path) -> None:
    create_mapping(project, "orders")
    create_mapping(project, "taken")
    _touch(project, "schemas/orders_input.schema.json", "schemas/free_input.schema.json")
    with pytest.raises(FnYamlError, match="already a mapping"):
        rename_mapping(project, "orders", "taken")
    with pytest.raises(FnYamlError, match="already exists"):
        rename_mapping(project, "orders", "free")  # its schema file name is taken
    assert (project / "mappings/functional/orders.fn.yaml").exists()
    assert not (project / "mappings/functional/free.fn.yaml").exists()
    assert (project / "schemas/orders_input.schema.json").exists()


def test_serve_mapping_ops(project: Path) -> None:
    base = {"project": str(project)}
    requests = [
        {"id": 1, "op": "mapping_create", "name": "orders", **base},
        {"id": 2, "op": "mapping_rename", "name": "orders", "new": "invoices", **base},
        {"id": 3, "op": "mapping_removal", "name": "invoices", **base},
        {"id": 4, "op": "mapping_delete", "name": "invoices", **base},
        {"id": 5, "op": "mapping_delete", "name": "invoices", **base},
    ]
    out = io.StringIO()
    serve(io.StringIO("".join(json.dumps(r) + "\n" for r in requests)), out)
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a["ok"] for a in answers] == [True, True, True, True, False]
    assert answers[2]["files"] == ["mappings/functional/invoices.fn.yaml"]


def test_creating_over_leftover_golden_cases_needs_a_decision(project: Path) -> None:
    from cli.mappings import golden_state

    _touch(project, "tests/golden/orders/a.input.json", "tests/golden/orders/a.expected.json")
    state = golden_state(project, "orders")
    assert (state["path"], state["files"], state["suggest"]) == (
        "tests/golden/orders",
        2,
        "orders_old",
    )
    with pytest.raises(FnYamlError, match="not empty"):
        create_mapping(project, "orders")
    assert not (project / "mappings/functional/orders.fn.yaml").exists()  # nothing was made

    create_mapping(project, "orders", golden="keep")
    assert (project / "tests/golden/orders/a.input.json").exists()

    delete_mapping(project, "orders")
    create_mapping(project, "orders", golden="rename", golden_to="orders_old")
    assert (project / "tests/golden/orders_old/a.input.json").exists()
    assert not (project / "tests/golden/orders").exists()

    delete_mapping(project, "orders")
    _touch(project, "tests/golden/orders/b.input.json")
    with pytest.raises(FnYamlError, match="already exists"):
        create_mapping(project, "orders", golden="rename", golden_to="orders_old")
    with pytest.raises(FnYamlError, match="not a valid folder name"):
        create_mapping(project, "orders", golden="rename", golden_to="a/b")
    create_mapping(project, "orders", golden="delete")
    assert not (project / "tests/golden/orders").exists()
    assert (project / "tests/golden/orders_old/a.input.json").exists()  # the other folder is safe
