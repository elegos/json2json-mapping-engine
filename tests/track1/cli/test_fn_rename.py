"""Renaming a project function (`cli/fn_rename.py`)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cli import fn_files, fn_rename
from compiler.function_registry import all_functions
from transpiler.model import FnYamlError, load_functional_file
from transpiler.review import review

FIXTURE = Path(__file__).resolve().parents[3] / "desktop/fixtures/tour-project"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / "p")
    mapping = tmp_path / "p/mappings/functional/orders.fn.yaml"
    mapping.write_text(mapping.read_text().replace('split_nth(value, ",", 2)', "first_word(value)"))
    (tmp_path / "p/fn/more.fn").write_text(
        'def twice(s: str) -> str:\n    """D."""\n    return first_word(s) + first_word(s)\n'
    )
    return tmp_path / "p"


def test_calls_are_renamed_but_not_text_in_quotes_or_attributes() -> None:
    text = 'first_word(a) + "first_word(" + x.first_word(b) + $first_word(c) + first_word (d)'
    assert fn_rename.rename_calls(text, "first_word", "head") == (
        'head(a) + "first_word(" + x.first_word(b) + $first_word(c) + head (d)',
        2,
    )


def test_the_plan_says_where_the_function_is_used(project: Path) -> None:
    plan = fn_rename.rename_plan(project, "first_word")
    assert plan == {"files": ["more", "text"], "mappings": [{"name": "orders", "calls": 1}]}


def test_a_rename_changes_the_def_the_other_functions_and_the_mappings(project: Path) -> None:
    done = fn_rename.rename_function(project, "first_word", "head")
    assert done["files"] == ["more", "text"] and done["mappings"] == [
        {"name": "orders", "calls": 1}
    ]
    assert "first_word" not in fn_files.read_file(project, "text")
    assert "def head(s: str)" in fn_files.read_file(project, "text")
    assert fn_files.read_file(project, "more").count("head(s)") == 2
    assert "head(value)" in (project / "mappings/functional/orders.fn.yaml").read_text()
    assert "head" in all_functions(project) and "first_word" not in all_functions(project)
    assert review(load_functional_file(project / "mappings/functional/orders.fn.yaml")) == []


def test_a_manual_rule_that_was_current_stays_current(project: Path) -> None:
    from transpiler.review import take_over
    from transpiler.serialize import write_functional

    path = project / "mappings/functional/orders.fn.yaml"
    file = load_functional_file(path)
    write_functional(path, take_over(file, "rules[2]"))
    fn_rename.rename_function(project, "first_word", "head")
    renamed = load_functional_file(path)
    assert "head(" in (renamed.rules[2].transform.code_override or "")  # type: ignore[union-attr]
    assert [r for r in review(renamed) if r.stale_override] == []


def test_what_cannot_be_renamed_is_refused(project: Path) -> None:
    for old, new, message in [
        ("ghost", "x", "not a function of the project"),
        ("first_word", "two words", "not a valid function name"),
        ("first_word", "class", "not a valid function name"),
        ("first_word", "twice", "exists already"),
        ("first_word", "split_first", "exists already"),
    ]:
        with pytest.raises(FnYamlError, match=message):
            fn_rename.rename_function(project, old, new)
    fn_files.override_builtin(project, "round")
    with pytest.raises(FnYamlError, match="replaces a built-in"):
        fn_rename.rename_function(project, "round", "rnd")
