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


def test_max_uses_compare_to_and_sum_uses_running_number_accumulator():
    sql = compile_file(FIXTURES / "aggregates.map.py")
    assert "compare_to(v_aggacc_0) > 0" in sql  # max
    assert "v_aggacc_1 := v_aggacc_1 + " in sql  # sum


def test_count_is_a_trivial_get_size_expression():
    sql = compile_file(FIXTURES / "aggregates.map.py")
    assert "v_srcroot.get_Array('items').get_size" in sql
