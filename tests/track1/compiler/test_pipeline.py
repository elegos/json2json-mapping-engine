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


def test_twin_procedures_are_generated():
    sql = compile_file(FIXTURES / "simple_object.map.py")
    assert "PROCEDURE map_simple_object (" in sql
    assert "PROCEDURE map_simple_object_safe (" in sql
    assert "p_err OUT CLOB" in sql


def test_bare_return_raises_omit_exception():
    sql = compile_file(FIXTURES / "return_forms.map.py")
    assert "RAISE e_field_omitted;" in sql


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
        "def order_id() -> str:\n"
        "    return root.id\n\n"
        "out.OrderId = order_id()\n"
    )
    sql = compile_source(source, default_mapping_id="whatever_the_filename_was")
    assert "map_order_event_48" in sql
    assert "whatever_the_filename_was" not in sql
