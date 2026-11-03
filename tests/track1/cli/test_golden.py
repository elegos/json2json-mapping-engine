"""The golden cases of a mapping from the tool (`cli/golden.py`)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cli.golden import delete_case, import_case, list_cases, rename_case
from cli.serve import serve
from compiler.backends.integration import discover_cases
from transpiler.model import FnYamlError


def _file(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / "elsewhere" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    return path


def test_a_case_is_copied_under_the_standard_names(tmp_path: Path) -> None:
    project = tmp_path / "p"
    written = import_case(
        project,
        "orders",
        "two_lines",
        _file(tmp_path, "my data.json", '{"a": 1}'),
        _file(tmp_path, "result.json", '{"b": 2}'),
        _file(tmp_path, "errs.json", '["unit_price"]'),
    )
    assert written == [
        "tests/golden/orders/two_lines.input.json",
        "tests/golden/orders/two_lines.expected.json",
        "tests/golden/orders/two_lines.expected_errors.json",
    ]
    assert list_cases(project, "orders") == [
        {
            "name": "two_lines",
            "expected": True,
            "errors": True,
            "rejected": False,
            "warnings": False,
        }
    ]
    # the harness reads it as a case, with the same names
    [case] = discover_cases(project / "tests/golden", "orders")
    assert (case.name, case.expected_errors) == ("two_lines", ["unit_price"])
    assert case.expected_path is not None


def test_only_the_input_is_required(tmp_path: Path) -> None:
    import_case(tmp_path / "p", "m", "c1", _file(tmp_path, "i.json", "{}"))
    assert list_cases(tmp_path / "p", "m") == [
        {"name": "c1", "expected": False, "errors": False, "rejected": False, "warnings": False}
    ]
    assert list_cases(tmp_path / "p", "no_such_mapping") == []


def test_a_bad_file_or_name_writes_nothing(tmp_path: Path) -> None:
    project = tmp_path / "p"
    good = _file(tmp_path, "good.json", "{}")
    cases = [
        ("c", _file(tmp_path, "bad.json", "{nope"), None, None, "not valid JSON"),
        ("c", good, _file(tmp_path, "bad2.json", "["), None, "not valid JSON"),
        ("c", good, None, _file(tmp_path, "e.json", '{"x": 1}'), "list of rule ids"),
        ("c", good, None, _file(tmp_path, "e2.json", "[1]"), "list of rule ids"),
        ("a b", good, None, None, "not a valid case name"),
        ("../x", good, None, None, "not a valid case name"),
        ("c", tmp_path / "missing.json", None, None, "No such file"),
    ]
    for name, inp, exp, errs, why in cases:
        with pytest.raises(FnYamlError, match=why):
            import_case(project, "m", name, inp, exp, errs)
    assert not (project / "tests").exists()
    import_case(project, "m", "c", good)
    with pytest.raises(FnYamlError, match="already has a case"):
        import_case(project, "m", "c", good)


def test_rename_and_delete_move_all_the_files_of_a_case(tmp_path: Path) -> None:
    project = tmp_path / "p"
    import_case(project, "m", "a", _file(tmp_path, "i.json", "{}"), _file(tmp_path, "o.json", "{}"))
    import_case(project, "m", "b", _file(tmp_path, "i.json", "{}"))
    with pytest.raises(FnYamlError, match="already has a case"):
        rename_case(project, "m", "a", "b")
    rename_case(project, "m", "a", "z")
    assert [c["name"] for c in list_cases(project, "m")] == ["b", "z"]
    assert (project / "tests/golden/m/z.expected.json").is_file()
    assert delete_case(project, "m", "z") == [
        "tests/golden/m/z.input.json",
        "tests/golden/m/z.expected.json",
    ]
    assert [c["name"] for c in list_cases(project, "m")] == ["b"]
    with pytest.raises(FnYamlError, match="no case called"):
        delete_case(project, "m", "z")


def test_serve_golden_ops(tmp_path: Path) -> None:
    source = _file(tmp_path, "i.json", "{}")
    base = {"project": str(tmp_path / "p"), "mapping": "m"}
    requests = [
        {"id": 1, "op": "golden_import", "name": "c", "input": str(source), **base},
        {"id": 2, "op": "golden_cases", **base},
        {"id": 3, "op": "golden_rename", "name": "c", "new": "d", **base},
        {"id": 4, "op": "golden_delete", "name": "d", **base},
        {"id": 5, "op": "golden_delete", "name": "d", **base},
    ]
    out = io.StringIO()
    serve(io.StringIO("".join(json.dumps(r) + "\n" for r in requests)), out)
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a["ok"] for a in answers] == [True, True, True, True, False]
    assert answers[1]["cases"] == [
        {"name": "c", "expected": False, "errors": False, "rejected": False, "warnings": False}
    ]


def test_a_case_is_created_read_edited_and_its_files_removed(tmp_path: Path) -> None:
    from cli.golden import create_case, read_case, write_case_file

    create_case(tmp_path, "orders", "first")
    assert read_case(tmp_path, "orders", "first") == {
        "input": "{}\n",
        "expected": None,
        "errors": None,
        "rejected": None,
        "warnings": None,
    }
    write_case_file(tmp_path, "orders", "first", "input", '{"id": "A1"}')
    write_case_file(tmp_path, "orders", "first", "expected", '{"OrderId": "A1"}\n')
    write_case_file(tmp_path, "orders", "first", "errors", '["rules[0]"]')
    got = read_case(tmp_path, "orders", "first")
    assert got["input"] == '{"id": "A1"}\n' and got["errors"] == '["rules[0]"]\n'
    assert [c["name"] for c in list_cases(tmp_path, "orders")] == ["first"]
    assert discover_cases(tmp_path / "tests/golden", "orders")  # the names every backend reads
    write_case_file(tmp_path, "orders", "first", "errors", None)
    assert read_case(tmp_path, "orders", "first")["errors"] is None


def test_a_file_that_is_not_valid_is_refused_and_the_old_one_stays(tmp_path: Path) -> None:
    from cli.golden import create_case, read_case, write_case_file

    create_case(tmp_path, "orders", "first", '{"a": 1}')
    for role, text in (
        ("input", "{"),
        ("expected", "nope"),
        ("errors", '{"a": 1}'),
        ("errors", "[1]"),
    ):
        with pytest.raises(FnYamlError):
            write_case_file(tmp_path, "orders", "first", role, text)
    with pytest.raises(FnYamlError, match="needs its input"):
        write_case_file(tmp_path, "orders", "first", "input", None)
    with pytest.raises(FnYamlError, match="no case"):
        write_case_file(tmp_path, "orders", "ghost", "input", "{}")
    with pytest.raises(FnYamlError, match="already has"):
        create_case(tmp_path, "orders", "first")
    assert read_case(tmp_path, "orders", "first") == {
        "input": '{"a": 1}\n',
        "expected": None,
        "errors": None,
        "rejected": None,
        "warnings": None,
    }
