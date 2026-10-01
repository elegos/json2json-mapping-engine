"""Review state: manual overrides under a moved proposal, and resolving them."""

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
    stamp_validation,
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


def _project_with(tmp_path: Path, source: str) -> dict:
    (tmp_path / "fn").mkdir(exist_ok=True)
    (tmp_path / "fn" / "x.fn").write_text(source)
    return all_functions(tmp_path)


def _validated(funcs):
    file = make()
    file.rules[0].transform.expression = "shout(value)"
    file.rules[0].validation.validated = True
    return stamp_validation(file, funcs)


def test_signature_change_flags_a_validated_rule_but_a_body_change_does_not(tmp_path: Path):
    before = _project_with(tmp_path, "def shout(s: str) -> str:\n    return s + '!'\n")
    file = _validated(before)
    assert file.rules[0].validation.functions.keys() == {"shout"}
    assert review(file, before) == []

    body = _project_with(tmp_path, "def shout(s: str) -> str:\n    return s.upper()\n")
    assert review(file, body) == []

    params = _project_with(tmp_path, "def shout(s: str, n: int) -> str:\n    return s\n")
    [item] = review(file, params)
    assert item.changed_functions == ["shout"]

    returns = _project_with(tmp_path, "def shout(s: str) -> int:\n    return 1\n")
    assert [i.changed_functions for i in review(file, returns)] == [["shout"]]
    assert file.rules[0].validation.validated  # the tick stays


def test_stamp_keeps_a_record_and_clears_it_when_not_validated(tmp_path: Path):
    funcs = _project_with(tmp_path, "def shout(s: str) -> str:\n    return s\n")
    file = _validated(funcs)
    again = stamp_validation(
        file, _project_with(tmp_path, "def shout(s: str, n: int) -> str:\n    return s\n")
    )
    assert again.rules[0].validation.functions == file.rules[0].validation.functions
    again.rules[0].validation.validated = False
    assert stamp_validation(again, funcs).rules[0].validation.functions == {}


def test_the_record_survives_a_save_and_load(tmp_path: Path):
    from transpiler.serialize import functional_to_raw

    file = _validated(_project_with(tmp_path, "def shout(s: str) -> str:\n    return s\n"))
    back = parse_functional(functional_to_raw(file), "t")
    assert back.rules[0].validation.functions == file.rules[0].validation.functions
