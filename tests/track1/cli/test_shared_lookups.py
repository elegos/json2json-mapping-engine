"""Project-wide lookups (`transpiler/shared_lookups.py`, ops `lookup_*` of `mapper serve`)."""

from __future__ import annotations

import contextlib
import shutil
from pathlib import Path

import pytest

from cli.build import compile_fresh
from cli.config import load_config
from cli.serve import handle
from transpiler import shared_lookups as sl
from transpiler.check import check_functional, schemas_for
from transpiler.model import FieldRule, FnYamlError, load_functional_file
from transpiler.review import _with_paths

FIXTURE = Path(__file__).resolve().parents[3] / "desktop/fixtures/tour-project"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / "p")
    return tmp_path / "p"


def _mapping(project: Path) -> Path:
    return project / "mappings/functional/orders.fn.yaml"


def _currency_rule(project: Path) -> FieldRule:
    rules = [r for _p, r in _with_paths(load_functional_file(_mapping(project)).rules)]
    (rule,) = [r for r in rules if isinstance(r, FieldRule) and r.id == "cur"]
    return rule


def _share(project: Path) -> list[str]:
    return sl.share(project, "orders", "countryCurrency")


def test_sharing_moves_the_table_into_the_project(project: Path) -> None:
    assert _share(project) == []
    assert "kind: lookup" not in _mapping(project).read_text()
    table = sl.read_shared(project, "countryCurrency")
    assert table.entries == {"IT": "EUR", "US": "USD"} and table.type == "str"
    tree = load_functional_file(_mapping(project))
    assert list(tree.shared) == ["countryCurrency"]
    assert sl.users(project, "countryCurrency") == ["orders"]


def test_the_mapping_still_builds_and_checks_with_a_shared_table(project: Path) -> None:
    with_local = _compile(project)
    _share(project)
    assert _compile(project) == with_local  # embedded as a constant, as a local one was
    tree = load_functional_file(_mapping(project))
    inp, out = schemas_for(project, "orders", tree.schemas)
    assert not [i for i in check_functional(tree, inp, out) if i.severity == "error"]


def _compile(project: Path) -> str:
    with contextlib.chdir(project):
        config = load_config()
        return str(compile_fresh(_mapping(project).relative_to(project), config).to_json())


def test_a_local_lookup_with_a_shared_name_is_an_error(project: Path) -> None:
    _share(project)
    text = (project / "lookups/countryCurrency.lookup.yaml").read_text()
    assert "entries" in text
    mapping = _mapping(project)
    mapping.write_text(
        mapping.read_text()
        + "- kind: lookup\n  id: dup\n  label: countryCurrency\n  entries:\n    A: B\n"
    )
    tree = load_functional_file(mapping)
    assert sl.clashes(tree) == ["countryCurrency"]
    inp, out = schemas_for(project, "orders", tree.schemas)
    assert any(
        "project-wide" in i.message
        for i in check_functional(tree, inp, out)
        if i.severity == "error"
    )


def test_changing_a_table_sends_the_rules_that_read_it_back_to_review_with_a_note(
    project: Path,
) -> None:
    _share(project)
    mapping = _mapping(project)
    text = mapping.read_text().replace(
        "    needs_review: true\n    notes: 'functional",
        "    validated: true\n    notes: 'functional",
        1,
    )
    mapping.write_text(text)
    assert _currency_rule(project).validation.validated
    marked = sl.save(
        project, "countryCurrency", {"IT": "EUR", "US": "USD", "DE": "EUR"}, "str", None
    )
    assert marked == {"orders": ["cur"]}
    v = _currency_rule(project).validation
    assert v.needs_review and not v.validated
    assert v.notes and "@countryCurrency changed" in v.notes and "added DE = 'EUR'" in v.notes
    assert "the list of countries is still open" in v.notes  # the reviewer's own note stays
    # the same change again leaves nothing new to say
    assert (
        sl.save(project, "countryCurrency", {"IT": "EUR", "US": "USD", "DE": "EUR"}, "str", None)
        == {}
    )


def test_an_unchanged_save_marks_nothing(project: Path) -> None:
    _share(project)
    assert sl.save(project, "countryCurrency", {"IT": "EUR", "US": "USD"}, "str", None) == {}


def test_describe_change_names_what_moved() -> None:
    from transpiler.model import LookupRule

    old = LookupRule(None, "t", {"A": 1, "B": 2, "C": 3})
    new = LookupRule(None, "t", {"A": 1, "B": 5, "D": 4})
    assert sl.describe_change(old, new) == ["B: 2 -> 5", "added D = 4", "removed C"]


def test_a_table_in_use_cannot_be_deleted(project: Path) -> None:
    _share(project)
    with pytest.raises(FnYamlError, match="read by orders"):
        sl.delete(project, "countryCurrency")
    assert (project / "lookups/countryCurrency.lookup.yaml").is_file()


def test_unsharing_gives_each_reader_its_own_copy(project: Path) -> None:
    _share(project)
    assert sl.unshare(project, "countryCurrency") == ["orders"]
    assert not (project / "lookups/countryCurrency.lookup.yaml").exists()
    tree = load_functional_file(_mapping(project))
    assert tree.shared == {}
    assert any(getattr(r, "label", None) == "countryCurrency" for r in tree.rules)


def test_a_new_table_needs_a_free_label(project: Path) -> None:
    with pytest.raises(FnYamlError, match="has its own lookup"):
        sl.save(project, "countryCurrency", {"A": "B"}, None, None, create=True)
    sl.save(project, "vatRates", {"IT": 22}, "int", "VAT by country", create=True)
    assert sl.describe(project)[0]["label"] == "vatRates"
    with pytest.raises(FnYamlError, match="already a project-wide"):
        sl.save(project, "vatRates", {"IT": 22}, "int", None, create=True)


def test_the_worker_ops(project: Path) -> None:
    base = {"project": str(project)}
    answer = handle({"op": "lookup_share", "stem": "orders", "label": "countryCurrency", **base})
    assert answer == {"ok": True, "clashing": []}
    (listed,) = handle({"op": "lookups_shared", **base})["lookups"]
    assert listed["label"] == "countryCurrency" and listed["used_by"] == ["orders"]
    tree = handle({"op": "check", "tree": _tree(project), "stem": "orders", **base})
    assert not [d for d in tree["diagnostics"] if d["severity"] == "error"]
    assert handle({"op": "lookup_unshare", "label": "countryCurrency", **base})["changed"] == [
        "orders"
    ]


def _tree(project: Path) -> dict:
    from transpiler.model import functional_to_dict

    return functional_to_dict(load_functional_file(_mapping(project)))
