"""The project's `fn/*.fn` files edited from the tool (`cli/fn_files.py`)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cli import fn_files
from compiler.function_registry import all_functions
from transpiler.model import FnYamlError

FIXTURE = Path(__file__).resolve().parents[3] / "desktop/fixtures/tour-project"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / "p")
    return tmp_path / "p"


def _messages(project: Path, text: str, name: str = "text") -> list[str]:
    return [i["message"] for i in fn_files.check_text(project, name, text)]


def test_the_files_list_what_they_define(project: Path) -> None:
    assert fn_files.list_files(project) == [
        {"name": "text", "functions": ["first_word"], "overrides": False}
    ]


def test_a_text_that_does_not_parse_is_refused_and_reported(project: Path) -> None:
    before = fn_files.read_file(project, "text")
    with pytest.raises(FnYamlError, match="not saved, line 1"):
        fn_files.write_file(project, "text", "def (:\n")
    assert fn_files.read_file(project, "text") == before
    (issue,) = fn_files.check_text(project, "text", "def (:\n")
    assert issue["severity"] == "error" and issue["line"] == 1


def test_the_check_wants_types_python_code_and_the_targets_code(project: Path) -> None:
    text = "def f(x):\n    ...\n"
    found = _messages(project, text)
    assert "parameter 'x' has no type" in found and "no return type" in found
    assert any(m.startswith("no code for Python") for m in found)
    assert any("no description" in m for m in found)
    # the tutorial project targets PL/SQL: a Python body alone is not enough
    typed = 'def f(x: str) -> str:\n    """Same."""\n    return x\n'
    assert _messages(project, typed) == [
        "no code for the project's backend 'plsql': add @override(plsql=...)"
    ]
    done = '@override(plsql="{x}")\n' + typed
    assert _messages(project, done) == []
    assert "not a backend" in _messages(project, '@override(cobol="x")\n' + typed)[0]


def test_a_name_that_is_a_builtin_or_in_another_file_is_a_warning(project: Path) -> None:
    body = '@override(plsql="{s}")\ndef {n}(s: str) -> str:\n    """D."""\n    return s\n'
    assert _messages(project, body.replace("{n}", "split_first")) == [
        "replaces the built-in of the same name"
    ]
    assert (
        "also defined in fn/text.fn"
        in _messages(project, body.replace("{n}", "first_word"), "more")[0]
    )


def test_create_and_delete_a_file(project: Path) -> None:
    fn_files.create_file(project, "money")
    assert fn_files.read_file(project, "money").startswith("# fn/money.fn")
    with pytest.raises(FnYamlError, match="exists already"):
        fn_files.create_file(project, "money")
    with pytest.raises(FnYamlError, match="not a valid file name"):
        fn_files.create_file(project, "../x")
    assert fn_files.delete_file(project, "text") == ["first_word"]
    assert [f["name"] for f in fn_files.list_files(project)] == ["money"]


def test_overriding_a_built_in_copies_it_under_a_warning(project: Path) -> None:
    assert fn_files.override_builtin(project, "round") == {
        "file": "builtin_overrides",
        "created": True,
    }
    text = fn_files.read_file(project, "builtin_overrides")
    assert text.startswith("# Built-in functions: changing them might break")
    assert "def round(x: float, digits: int=0)" in text and "def _quantize" in text
    assert fn_files.override_builtin(project, "round")["created"] is False
    fn_files.override_builtin(project, "trunc")
    functions = all_functions(project)
    assert functions["round"].origin == "fn/builtin_overrides.fn"
    assert [f for f in fn_files.list_files(project) if f["overrides"]][0]["functions"] == [
        "round",
        "trunc",
    ]
    with pytest.raises(FnYamlError, match="not a built-in"):
        fn_files.override_builtin(project, "nothing")
    fn_files.delete_file(project, "builtin_overrides")
    assert all_functions(project)["round"].origin == "built-in"


def test_a_test_call_runs_on_python(project: Path) -> None:
    assert fn_files.call_function(project, "first_word", ["hello big world"]) == {
        "ok": True,
        "result": "hello",
    }
    assert fn_files.call_function(project, "first_word", [""]) == {"ok": True, "result": None}
    failed = fn_files.call_function(project, "first_word", [])
    assert failed["ok"] is False and "TypeError" in failed["error"]


def test_a_test_call_uses_the_text_being_edited_and_says_when_python_cannot(project: Path) -> None:
    text = (
        'def shout(s: str) -> str:\n    """D."""\n    return s.upper() + split_first("a,b", ",")\n'
    )
    assert fn_files.call_function(project, "shout", ["x"], text) == {"ok": True, "result": "Xa"}
    stub = '@override(plsql="UPPER({s})")\ndef shout(s: str) -> str:\n    ...\n'
    with pytest.raises(FnYamlError, match="no code for Python in shout"):
        fn_files.call_function(project, "shout", ["x"], stub)
    with pytest.raises(FnYamlError, match="no project function called"):
        fn_files.call_function(project, "ghost", [])


def test_a_call_that_never_ends_is_stopped(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fn_files, "CALL_TIMEOUT", 1)
    loop = 'def spin(s: str) -> str:\n    """D."""\n    while True:\n        pass\n'
    assert fn_files.call_function(project, "spin", ["x"], loop)["error"].startswith("no answer")


def test_a_copied_built_in_runs_as_it_did(project: Path) -> None:
    fn_files.override_builtin(project, "round")
    assert fn_files.call_function(project, "round", [2.675, 2]) == {"ok": True, "result": 2.68}


def test_a_new_function_is_a_stub_for_python_and_the_projects_backend(project: Path) -> None:
    fn_files.add_function(project, "money", "to_cents")
    text = fn_files.read_file(project, "money")
    assert "from __mapping__ import override" in text
    assert "@override(plsql=\"NOT_IMPLEMENTED('plsql stub')\")" in text
    assert 'raise NotImplementedError("python stub")' in text
    assert _messages(project, text, "money") == [
        "stub for plsql: write the real code",
        "no code for Python: write a body or @override(python=...) (the tool and the golden cases "
        "run Python)",
    ]
    fn_files.add_function(project, "money", "to_units")
    assert "def to_units" in fn_files.read_file(project, "money")
    with pytest.raises(FnYamlError, match="exists already"):
        fn_files.add_function(project, "money", "to_cents")
    with pytest.raises(FnYamlError, match="exists already"):
        fn_files.add_function(project, "money", "split_first")


def test_the_overrides_file_is_kept_for_built_in_overrides(project: Path) -> None:
    with pytest.raises(FnYamlError, match="kept for the built-in overrides"):
        fn_files.add_function(project, "builtin_overrides", "mine")
    with pytest.raises(FnYamlError, match="kept for the built-in overrides"):
        fn_files.create_file(project, "builtin_overrides")


def test_an_overridden_built_in_shows_what_the_backends_write_for_it(project: Path) -> None:
    fn_files.override_builtin(project, "trunc")
    fn_files.override_builtin(project, "concat")
    text = fn_files.read_file(project, "builtin_overrides")
    assert "@override(plsql='TRUNC({x}, {digits})')" in text
    # variadic: the backend's rendering is not a template of the parameters
    assert '# plsql: written by the backend; add @override(plsql="...")' in text
    # trunc has its PL/SQL code now; the variadic concat is a stub for the developer to fill
    issues = fn_files.check_text(project, "builtin_overrides", text)
    assert [i["function"] for i in issues if i["message"].startswith("stub for plsql")] == [
        "concat"
    ]
    assert fn_files.call_function(project, "trunc", [2.678, 2]) == {"ok": True, "result": 2.67}


def test_a_built_in_the_backend_lowers_gets_a_stub_for_the_projects_backend(project: Path) -> None:
    fn_files.override_builtin(project, "avg")
    text = fn_files.read_file(project, "builtin_overrides")
    assert "@override(plsql=\"NOT_IMPLEMENTED('plsql stub')\")" in text
    assert "def _column" in text
