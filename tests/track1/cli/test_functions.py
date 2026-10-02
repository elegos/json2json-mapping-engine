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
