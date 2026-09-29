from compiler.pipeline import compile_source

_SOURCE = (
    "from __mapping__ import *\n\n"
    "@dataclass\n"
    "class Line:\n"
    "    Id: str\n\n"
    "{decorator}"
    "def line(root: Any, src: Any) -> Line:\n"
    "    return Line(Id=src.id)\n\n"
    "for src in root.items:\n"
    "    out.Lines.append(line(root, src))\n"
)


def test_parallel_rule_adds_a_sql_callable_parallel_enable_wrapper():
    text = compile_source(_SOURCE.format(decorator="@parallel(degree=4)\n"), "m")
    spec, body = text.split("CREATE OR REPLACE PACKAGE BODY")
    assert "FUNCTION map_m_fn (p_src IN CLOB) RETURN CLOB PARALLEL_ENABLE;" in spec
    assert "map_m(p_src, v_out);" in body
    assert "@parallel declared by: line (degree=4)" in body
    assert "/*+ PARALLEL(4) */" in body


def test_positional_degree_is_the_same_as_keyword():
    keyword = compile_source(_SOURCE.format(decorator="@parallel(degree=4)\n"), "m")
    positional = compile_source(_SOURCE.format(decorator="@parallel(4)\n"), "m")
    assert positional == keyword


def test_no_wrapper_without_parallel():
    assert "map_m_fn" not in compile_source(_SOURCE.format(decorator=""), "m")
