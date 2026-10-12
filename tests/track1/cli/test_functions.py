from pathlib import Path

from cli.functions import function_list


def test_builtins_are_listed_by_name_with_signature_and_doc() -> None:
    found = {f["name"]: f for f in function_list(None)}
    assert list(found) == sorted(found)
    split = found["split_first"]
    assert split["builtin"] and not split["replaces_builtin"]
    assert split["signature"].startswith("split_first(") and split["doc"]
    assert [p["name"] for p in split["params"]][0]


def test_project_functions_show_their_file_and_what_they_replace(tmp_path: Path) -> None:
    (tmp_path / "fn").mkdir()
    (tmp_path / "fn/text.fn").write_text(
        'def word(s: str, n: int) -> str:\n    """The n-th word."""\n    return s\n\n'
        "def split_first(s: str) -> str:\n    return s\n"
    )
    found = {f["name"]: f for f in function_list(tmp_path)}
    assert found["word"]["origin"] == "fn/text.fn" and not found["word"]["replaces_builtin"]
    assert found["word"]["doc"] == "The n-th word."
    assert found["split_first"]["replaces_builtin"] and not found["split_first"]["builtin"]


def test_a_project_function_says_whether_python_can_run_it(tmp_path: Path) -> None:
    (tmp_path / "fn").mkdir()
    (tmp_path / "fn/text.fn").write_text(
        "from __mapping__ import override\n\n"
        '@override(plsql="UPPER({s})")\ndef only_plsql(s: str) -> str:\n    ...\n\n'
        '@override(python="{s}.upper()", plsql="UPPER({s})")\ndef both(s: str) -> str:\n    ...\n\n'
        "def plain(s: str) -> str:\n    return s\n"
    )
    found = {f["name"]: f for f in function_list(tmp_path)}
    assert [found[n]["python_code"] for n in ("only_plsql", "both", "plain")] == [False, True, True]
    assert all(f["python_code"] for f in function_list(None))  # the built-ins run everywhere


def test_the_functions_command_lists_the_project_and_the_builtins_as_json(
    tmp_path: Path, monkeypatch
) -> None:
    import json

    from typer.testing import CliRunner

    from cli.main import app

    (tmp_path / "fn").mkdir()
    (tmp_path / "fn/text.fn").write_text(
        'def word(s: str, n: int) -> str:\n    """The n-th word."""\n    return s\n'
    )
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    answer = json.loads(runner.invoke(app, ["functions", "--json"]).output)
    names = {f["name"]: f for f in answer["functions"]}
    assert (
        answer["ok"] and names["word"]["origin"] == "fn/text.fn" and names["split_first"]["builtin"]
    )
    text = runner.invoke(app, ["functions"]).output
    assert "word(s, n) -> str  [fn/text.fn]\n    The n-th word." in text
    assert "split_first(" in text
