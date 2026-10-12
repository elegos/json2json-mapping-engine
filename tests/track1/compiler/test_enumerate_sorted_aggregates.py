from pathlib import Path

from compiler.pipeline import compile_file

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"


def test_enumerate_sorted_matches_golden_sql():
    sql = compile_file(FIXTURES / "enumerate_sorted.map.py")
    assert sql == (GOLDEN / "enumerate_sorted.sql").read_text()


def test_enumerate_binds_index_variable():
    sql = compile_file(FIXTURES / "enumerate_sorted.map.py")
    assert "v_i NUMBER := v_i_0 + 1;" in sql  # start=1


def test_sorted_lowers_to_native_insertion_sort_no_sql_context():
    sql = compile_file(FIXTURES / "enumerate_sorted.map.py")
    assert "compare_to" in sql
    assert ".put(" in sql and ", TRUE)" in sql
    assert "ORDER BY" not in sql  # native PL/SQL only, no SQL-context sort


def test_aggregates_matches_golden_sql():
    sql = compile_file(FIXTURES / "aggregates.map.py")
    assert sql == (GOLDEN / "aggregates.sql").read_text()


def test_max_compares_the_values_and_sum_uses_running_number_accumulator():
    sql = compile_file(FIXTURES / "aggregates.map.py")
    assert "v_aggval_0 > v_aggacc_0" in sql  # max: a missing value is skipped, as in SQL
    assert "v_aggacc_1 := v_aggacc_1 + v_aggval_1" in sql  # sum


def test_count_is_a_trivial_get_size_expression():
    sql = compile_file(FIXTURES / "aggregates.map.py")
    assert "v_srcroot.get_Array('items').get_size" in sql


def test_src_means_the_item_not_the_index_in_an_enumerate_loop():
    from compiler.pipeline import compile_source

    sql = compile_source(
        "from __mapping__ import *\n\n"
        "def rule(root: Any, src: Any, index: int) -> Line:\n"
        "    return Line(Pos=index, Id=src.id)\n\n"
        "for index, src in enumerate(root.items):\n"
        "    out.Lines.append(rule(root, src, index))\n".replace(
            "def rule", "@dataclass\nclass Line:\n    Pos: int\n    Id: str\n\n\ndef rule"
        ),
        "m",
    )
    assert "fn_m_rule(v_srcroot, v_src, v_index," in sql


def test_sorted_sorts_a_clone_not_the_source_array():
    from compiler.pipeline import compile_file

    sql = compile_file(FIXTURES / "enumerate_sorted.map.py")
    assert ".clone AS JSON_ARRAY_T)" in sql


def test_comparison_with_none_is_is_null():
    from compiler.pipeline import compile_source

    sql = compile_source(
        "from __mapping__ import *\n\n"
        "def a(root: Any) -> bool:\n    return root.x == None\n\n"
        "def b(root: Any) -> bool:\n    return root.x != None\n\n"
        "out.A = a(root)\nout.B = b(root)\n",
        "m",
    )
    assert "p_root.get_String('x') IS NULL" in sql or "IS NULL)" in sql
    assert "IS NOT NULL)" in sql
