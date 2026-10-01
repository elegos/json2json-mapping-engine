"""Review state: manual overrides under a moved proposal, and resolving them."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from transpiler.model import FnYamlError, parse_functional
from transpiler.review import (
    accept_proposal,
    keep_override,
    proposal_view,
    review,
    set_override,
    take_over,
)

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
    assert review(file) == []
    file.rules[0].transform.expression = "coalesce(value, '?')"
    [item] = review(file)
    assert (item.path, item.stale_override) == ("rules[0]", True)
    view = proposal_view(file, "rules[0]")
    assert (
        view["auto"] == "coalesce(root.name, '?')" and view["override"] == "concat(root.name, '!')"
    )


def test_keep_override_moves_the_baseline():
    file = take_over(make(), "rules[0]")
    file.rules[0].transform.expression = "coalesce(value, '?')"
    file = keep_override(file, "rules[0]")
    assert review(file) == []
    assert file.rules[0].transform.code_override == "concat(root.name, '!')"


def test_accept_proposal_returns_to_auto_and_keeps_the_validation():
    file = take_over(make(), "rules[0]")
    file.rules[0].validation.validated = True
    file = accept_proposal(file, "rules[0]")
    r = file.rules[0]
    assert r.transform.status == "auto" and r.transform.code_override is None
    assert r.transform.last_auto_version is None
    assert (r.validation.validated, r.validation.needs_review) == (True, False)


def test_set_override_needs_manual_and_code():
    with pytest.raises(FnYamlError):
        set_override(make(), "rules[0]", "x")
    file = take_over(make(), "rules[0]")
    with pytest.raises(FnYamlError):
        set_override(file, "rules[0]", "  ")
    assert set_override(file, "rules[0]", "root.name")


def test_serve_review_ops(tmp_path: Path):
    import io
    import json

    from cli.serve import serve
    from transpiler.model import functional_to_dict

    tree = functional_to_dict(make())
    steps = [
        {"op": "take_over", "tree": tree, "path": "rules[0]"},
        {"op": "proposal", "tree": tree, "path": "rules[0]"},
        {"op": "check", "tree": tree, "project": str(tmp_path), "stem": "t"},
    ]
    out = io.StringIO()
    serve(io.StringIO("".join(json.dumps({"id": i, **r}) + "\n" for i, r in enumerate(steps))), out)
    taken, view, checked = (json.loads(line) for line in out.getvalue().splitlines())
    assert taken["tree"]["rules"][0]["transform"]["status"] == "manual"
    assert view["auto"] == "concat(root.name, '!')" and view["override"] is None
    assert checked["ok"] and checked["review"] == []


def test_demote_invalid_sends_a_validated_rule_with_errors_back_to_review():
    from transpiler.review import demote_invalid

    file = make()
    file.rules[0].validation.validated = True
    out, demoted = demote_invalid(file, {"rules[0]"})
    assert demoted == ["a"]
    assert (out.rules[0].validation.validated, out.rules[0].validation.needs_review) == (
        False,
        True,
    )
    same, none = demote_invalid(file, {"rules[1]"})
    assert none == [] and same.rules[0].validation.validated


def test_fn_write_demotes_a_validated_rule_that_does_not_check(tmp_path: Path, monkeypatch):
    import json

    from typer.testing import CliRunner

    from cli.main import app
    from transpiler.model import functional_to_dict

    (tmp_path / "mappings").mkdir()
    target = tmp_path / "mappings" / "t.fn.yaml"
    file = make()
    file.rules[0].transform.expression = "split_first(value)"  # one argument too few
    file.rules[0].validation.validated = True
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app, ["fn", "write", str(target)], input=json.dumps({"file": functional_to_dict(file)})
    )
    assert json.loads(result.stdout)["decayed"] == ["a"]
    saved = parse_functional(__import__("yaml").safe_load(target.read_text()), "t")
    assert (saved.rules[0].validation.validated, saved.rules[0].validation.needs_review) == (
        False,
        True,
    )
