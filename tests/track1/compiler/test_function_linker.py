import pytest

from compiler.function_linker import FunctionImpl, FunctionLinker, FunctionLinkError


def test_resolves_builtin_coalesce():
    linker = FunctionLinker()
    impl = linker.resolve("coalesce")
    assert impl.render("plsql", ["a", "b"]) == "COALESCE(a, b)"


def test_unresolved_function_is_a_link_error():
    linker = FunctionLinker()
    with pytest.raises(FunctionLinkError):
        linker.resolve("not_a_real_function")


def test_project_function_overrides_builtin_for_same_name():
    project_coalesce = FunctionImpl(name="coalesce", target_templates={"plsql": "NVL({0}, {1})"})
    linker = FunctionLinker(project_functions={"coalesce": project_coalesce})
    impl = linker.resolve("coalesce")
    assert impl.render("plsql", ["a", "b"]) == "NVL(a, b)"


def test_missing_target_implementation_is_a_link_error():
    impl = FunctionImpl(name="only_python", target_templates={})
    with pytest.raises(FunctionLinkError):
        impl.render("plsql", ["a"])
