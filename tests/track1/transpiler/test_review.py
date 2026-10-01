"""Review state: manual overrides under a moved proposal, validated rules under changed functions."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from compiler.function_registry import all_functions
from transpiler.model import FnYamlError, parse_functional
from transpiler.review import (
    accept_proposal,
    keep_override,
    proposal_view,
    review,
    set_override,
    take_over,
    validate,
)
from transpiler.serialize import functional_to_raw

RAW = {
    "id": "t",
    "rules": [
        {
            "kind": "field",
            "id": "a",
            "field": "Name",
            "type": "str",
            "source": {"path": "$.name"},
            "transform": {"expression": "concat(value, '!')"},
        },
        {
            "kind": "loop",
            "id": "l",
            "source": "$.items[*]",
            "output": "$.Lines[*]",
            "rules": [
                {
                    "kind": "field",
                    "id": "s",
                    "field": "Sku",
                    "type": "str",
                    "transform": {"expression": "@.sku"},
                }
            ],
        },
    ],
}
FUNCS = all_functions(None)


def make():
    return parse_functional(copy.deepcopy(RAW), "t")


def test_take_over_copies_the_auto_code_and_remembers_it():
    out = take_over(make(), "rules[0]")
    t = out.rules[0].transform
    assert t.status == "manual"
    assert t.code_override == t.last_auto_version == "concat(root.name, '!')"


def test_take_over_a_nested_rule():
    out = take_over(make(), "rules[1].rules[0]")
    assert out.rules[1].rules[0].transform.code_override == "src.sku"


def test_stale_override_after_the_expression_changes():
    file = take_over(make(), "rules[0]")
    assert review(file, FUNCS) == []
    file.rules[0].transform.expression = "coalesce(value, '?')"
    [item] = review(file, FUNCS)
    assert (item.path, item.stale_override) == ("rules[0]", True)
    view = proposal_view(file, "rules[0]")
    assert (
        view["auto"] == "coalesce(root.name, '?')" and view["override"] == "concat(root.name, '!')"
    )


def test_keep_override_moves_the_baseline():
    file = take_over(make(), "rules[0]")
    file.rules[0].transform.expression = "coalesce(value, '?')"
    file = keep_override(file, "rules[0]")
    assert review(file, FUNCS) == []
    assert file.rules[0].transform.code_override == "concat(root.name, '!')"


def test_accept_proposal_returns_to_auto_and_flags_review():
    file = take_over(make(), "rules[0]")
    file.rules[0].validation.validated = True
    file = accept_proposal(file, "rules[0]")
    r = file.rules[0]
    assert r.transform.status == "auto" and r.transform.code_override is None
    assert r.transform.last_auto_version is None
    assert (r.validation.validated, r.validation.needs_review) == (False, True)


def test_set_override_needs_manual_and_code():
    with pytest.raises(FnYamlError):
        set_override(make(), "rules[0]", "x")
    file = take_over(make(), "rules[0]")
    with pytest.raises(FnYamlError):
        set_override(file, "rules[0]", "  ")
    assert set_override(file, "rules[0]", "root.name")


def test_changed_function_flags_a_validated_rule():
    file = validate(make(), "rules[0]", True, FUNCS)
    assert file.rules[0].validation.functions == {"concat": FUNCS["concat"].fingerprint}
    assert review(file, FUNCS) == []
    file.rules[0].validation.functions["concat"] = "0000000000"
    [item] = review(file, FUNCS)
    assert item.changed_functions == ["concat"]
    unvalidated = validate(file, "rules[0]", False, FUNCS)
    assert unvalidated.rules[0].validation.functions == {} and review(unvalidated, FUNCS) == []


def test_project_function_edit_changes_the_fingerprint(tmp_path: Path):
    (tmp_path / "fn").mkdir()
    fn = tmp_path / "fn" / "x.fn"
    fn.write_text("def shout(s: str) -> str:\n    return s + '!'\n")
    before = all_functions(tmp_path)
    fn.write_text("def shout(s: str) -> str:\n    return s + '!!'\n")
    assert all_functions(tmp_path)["shout"].fingerprint != before["shout"].fingerprint


def test_the_functions_survive_a_save_and_load():
    file = validate(make(), "rules[0]", True, FUNCS)
    again = parse_functional(functional_to_raw(file), "t")
    assert again.rules[0].validation.functions == file.rules[0].validation.functions


def test_serve_review_ops(tmp_path: Path):
    import io
    import json

    from cli.serve import serve
    from transpiler.model import functional_to_dict

    tree = functional_to_dict(make())
    steps = [
        {"op": "take_over", "tree": tree, "path": "rules[0]"},
        {
            "op": "set_validated",
            "tree": tree,
            "path": "rules[0]",
            "value": True,
            "project": str(tmp_path),
        },
        {"op": "proposal", "tree": tree, "path": "rules[0]"},
        {"op": "check", "tree": tree, "project": str(tmp_path), "stem": "t"},
    ]
    out = io.StringIO()
    serve(io.StringIO("".join(json.dumps({"id": i, **r}) + "\n" for i, r in enumerate(steps))), out)
    taken, validated, view, checked = (json.loads(line) for line in out.getvalue().splitlines())
    assert taken["tree"]["rules"][0]["transform"]["status"] == "manual"
    assert validated["tree"]["rules"][0]["validation"]["functions"].keys() == {"concat"}
    assert view["auto"] == "concat(root.name, '!')" and view["override"] is None
    assert checked["ok"] and checked["review"] == []
