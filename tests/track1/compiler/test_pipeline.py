from pathlib import Path

from compiler.pipeline import compile_file, compile_source

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"


def test_simple_object_matches_golden_sql():
    sql = compile_file(FIXTURES / "simple_object.map.py")
    assert sql == (GOLDEN / "simple_object.sql").read_text()


def test_return_forms_matches_golden_sql():
    sql = compile_file(FIXTURES / "return_forms.map.py")
    assert sql == (GOLDEN / "return_forms.sql").read_text()


def test_builtins_showcase_matches_golden_sql():
    sql = compile_file(FIXTURES / "builtins_showcase.map.py")
    assert sql == (GOLDEN / "builtins_showcase.sql").read_text()


def test_twin_procedures_are_generated():
    sql = compile_file(FIXTURES / "simple_object.map.py")
    assert "PROCEDURE map_simple_object (" in sql
    assert "PROCEDURE map_simple_object_safe (" in sql
    assert "p_err OUT CLOB" in sql


def test_bare_return_sets_omitted_flag():
    sql = compile_file(FIXTURES / "return_forms.map.py")
    assert "p_omitted := TRUE;" in sql
    assert "p_omitted OUT BOOLEAN" in sql


def test_return_null_form():
    sql = compile_file(FIXTURES / "return_forms.map.py")
    assert "RETURN NULL;" in sql


def test_error_accumulation_and_raise_application_error():
    sql = compile_file(FIXTURES / "return_forms.map.py")
    assert "WHEN OTHERS THEN" in sql
    assert "RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());" in sql
    assert "v_shown < 20" in sql  # 20-entry truncation cap (§Runtime error semantics)


def test_id_directive_overrides_default_mapping_id():
    source = (
        "from __mapping__ import *\n\n"
        "__id__ = 'order_event_48'\n\n"
        "def order_id(root: Any) -> str:\n"
        "    return root.id\n\n"
        "out.OrderId = order_id(root)\n"
    )
    sql = compile_source(source, default_mapping_id="whatever_the_filename_was")
    assert "map_order_event_48" in sql
    assert "whatever_the_filename_was" not in sql


def test_dataclass_construction_and_array_append():
    sql = compile_file(FIXTURES / "lines_array.map.py")
    # Built in memory via .put(), never round-tripped through JSON_OBJECT()/
    # text — no RETURNING CLOB, no 4000-byte VARCHAR2 ceiling.
    assert "JSON_OBJECT(" not in sql
    assert "RETURNING CLOB" not in sql
    assert "v_line_rule__dc.put('LineId', p_itm.get_String('id'));" in sql
    assert "v_line_rule__dc.put('LineAmount', p_itm.get_Number('price'));" in sql
    assert "v_arr_Lines.append(v_result_line_rule);" in sql
    assert "v_out_obj.put('Lines', v_arr_Lines);" in sql


def test_lines_array_matches_golden_sql():
    sql = compile_file(FIXTURES / "lines_array.map.py")
    assert sql == (GOLDEN / "lines_array.sql").read_text()
