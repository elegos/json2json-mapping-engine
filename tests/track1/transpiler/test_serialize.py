"""`.fn.yaml` writer and the `mapper fn read|write` commands (desktop tool)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.main import app
from transpiler.model import (
    FieldRule,
    FnYamlError,
    FunctionalFile,
    ObjectRule,
    functional_from_dict,
    functional_to_dict,
    load_functional_file,
    parse_functional,
)
from transpiler.serialize import apply_decay_tree, functional_to_raw, functional_to_yaml

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


@pytest.mark.parametrize("name", ["order_event", "nested"])
def test_round_trip_keeps_the_tree(name: str, tmp_path: Path) -> None:
    original = load_functional_file(FIXTURES / f"{name}.fn.yaml")
    out = tmp_path / f"{name}.fn.yaml"
    out.write_text(functional_to_yaml(original))
    again = load_functional_file(out)
    assert functional_to_dict(again) | {"path": None} == functional_to_dict(original) | {
        "path": None
    }


def _first_field(file: FunctionalFile) -> FieldRule:
    return next(r for r in file.rules if isinstance(r, FieldRule))


def test_decay_tree_flags_only_functionally_changed_rules() -> None:
    old = load_functional_file(FIXTURES / "order_event.fn.yaml")
    validated = _first_field(old)
    validated.validation.validated = True
    nested = next(r for r in old.rules if isinstance(r, ObjectRule))
    child = next(r for r in nested.rules if isinstance(r, FieldRule))
    child.validation.validated = True

    new = load_functional_file(FIXTURES / "order_event.fn.yaml")
    _first_field(new).validation.validated = True
    nested_new = next(r for r in new.rules if isinstance(r, ObjectRule))
    child_new = next(r for r in nested_new.rules if isinstance(r, FieldRule))
    child_new.validation.validated = True
    child_new.transform.expression = "$.other"  # functional change, inside an object

    result, decayed = apply_decay_tree(old, new)
    assert decayed == [child.id]
    assert _first_field(result).validation.validated is True
    inner = next(r for r in result.rules if isinstance(r, ObjectRule)).rules[0]
    assert isinstance(inner, FieldRule)
    assert inner.validation.validated is False and inner.validation.needs_review is True


def test_fn_read_prints_the_tree() -> None:
    result = runner.invoke(app, ["fn", "read", str(FIXTURES / "nested.fn.yaml")])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True and payload["file"]["id"] == "nested"


def test_fn_read_reports_a_bad_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.fn.yaml"
    bad.write_text("rules: 3\n")
    result = runner.invoke(app, ["fn", "read", str(bad)])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_fn_write_applies_decay_and_saves(tmp_path: Path) -> None:
    target = tmp_path / "order_event.fn.yaml"
    shutil.copy(FIXTURES / "order_event.fn.yaml", target)
    tree = json.loads(runner.invoke(app, ["fn", "read", str(target)]).stdout)
    first = tree["file"]["rules"][0]
    first["validation"]["validated"] = True
    assert runner.invoke(app, ["fn", "write", str(target)], input=json.dumps(tree)).exit_code == 0

    first["transform"]["expression"] = "$.id2"
    result = runner.invoke(app, ["fn", "write", str(target)], input=json.dumps(tree))
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"ok": True, "decayed": [first["id"]]}
    saved = load_functional_file(target)
    rule = _first_field(saved)
    assert rule.validation.needs_review is True and rule.validation.validated is False


def test_fn_write_refuses_an_invalid_tree(tmp_path: Path) -> None:
    target = tmp_path / "x.fn.yaml"
    tree = functional_to_dict(load_functional_file(FIXTURES / "nested.fn.yaml"))
    tree["rules"][0]["kind"] = "bogus"
    result = runner.invoke(app, ["fn", "write", str(target)], input=json.dumps({"file": tree}))
    assert result.exit_code == 1 and json.loads(result.stdout)["ok"] is False
    assert not target.exists()


def test_a_lookup_keeps_its_declared_type() -> None:
    raw = {
        "id": "t",
        "rules": [
            {"kind": "lookup", "label": "tab", "type": "int", "entries": {"a": 1}},
            {"kind": "field", "field": "X", "type": "int", "transform": {"expression": "1"}},
        ],
    }
    again = parse_functional(functional_to_raw(parse_functional(raw, default_id="t")), "t")
    assert again.rules[0].type == "int"  # type: ignore[union-attr]


def test_targets_are_written_without_prefix_and_sources_in_full() -> None:
    from transpiler.model import FieldRule, LoopRule, parse_functional

    raw = {
        "id": "t",
        "rules": [
            {"kind": "field", "field": "A", "type": "str", "source": {"path": "$.id"}},
            {
                "kind": "loop",
                "source": "$.items[*]",
                "output": "$.Lines[*]",
                "rules": [
                    {"kind": "field", "field": "S", "type": "str", "source": {"path": "@.sku"}},
                    {"kind": "field", "field": "C", "type": "str", "source": {"path": "$.cur"}},
                ],
            },
        ],
    }
    file = parse_functional(raw, default_id="t")
    out = functional_to_raw(file)
    assert out["rules"][0]["source"] == {"path": "$.id"}
    loop = out["rules"][1]
    assert (loop["source"], loop["output"]) == ("$.items[*]", "Lines[*]")
    assert [r["source"]["path"] for r in loop["rules"]] == ["@.sku", "$.cur"]
    again = parse_functional(out, default_id="t")  # and it reads back as the same tree
    assert again == file
    assert isinstance(again.rules[1], LoopRule) and isinstance(again.rules[0], FieldRule)


def test_the_schemas_section_round_trips_and_is_checked() -> None:
    raw = {
        "id": "t",
        "schemas": {"input": "contracts/in.json"},
        "rules": [
            {
                "kind": "field",
                "id": "a",
                "field": "A",
                "type": "str",
                "transform": {"expression": "'x'"},
            }
        ],
    }
    file = parse_functional(raw, "t")
    assert (file.schemas.input, file.schemas.output) == ("contracts/in.json", None)
    assert functional_to_raw(file)["schemas"] == {"input": "contracts/in.json"}
    assert "schemas" not in functional_to_raw(parse_functional({**raw, "schemas": None}, "t"))
    assert functional_from_dict(functional_to_dict(file)).schemas == file.schemas
    for bad in ({"input": 3}, {"other": "x"}, ["x"]):
        with pytest.raises(FnYamlError):
            parse_functional({**raw, "schemas": bad}, "t")
