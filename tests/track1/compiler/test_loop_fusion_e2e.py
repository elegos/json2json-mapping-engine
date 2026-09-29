from pathlib import Path

from compiler.pipeline import compile_file, compile_source

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"


def test_fused_lines_matches_golden_sql():
    sql = compile_file(FIXTURES / "fused_lines.map.py")
    assert sql == (GOLDEN / "fused_lines.sql").read_text()


def test_fused_lines_has_exactly_one_generated_loop():
    sql = compile_file(FIXTURES / "fused_lines.map.py")
    # map_<id> and map_<id>_safe each embed one copy of the body.
    assert sql.count("FOR v_i_") == 2


def test_filter_survives_fusion_as_a_per_branch_guard():
    sql = compile_file(FIXTURES / "fused_lines.map.py")
    assert "IF (NOT (v_itm.get_String('status') = 'INACTIVE')) THEN" in sql


def test_disabling_loop_fusion_keeps_two_separate_loops():
    sql = compile_file(FIXTURES / "fused_lines.map.py", loop_fusion=False)
    assert sql.count("FOR v_i_") == 4


def test_parallel_conflict_raises_by_default():
    source = (
        "from __mapping__ import *\n\n"
        "@parallel(degree=2)\n"
        "def rule_a(x: Any) -> str:\n"
        "    return x.id\n\n"
        "@parallel(degree=4)\n"
        "def rule_b(x: Any) -> str:\n"
        "    return x.id\n\n"
        "for a in root.items:\n"
        "    out.X.append(rule_a(a))\n"
        "for b in root.items:\n"
        "    out.Y.append(rule_b(b))\n"
    )
    import pytest

    from compiler.loop_fusion import LoopFusionError

    with pytest.raises(LoopFusionError):
        compile_source(source, default_mapping_id="parallel_conflict")


def test_parallel_conflict_resolved_by_config():
    source = (
        "from __mapping__ import *\n\n"
        "@parallel(degree=2)\n"
        "def rule_a(x: Any) -> str:\n"
        "    return x.id\n\n"
        "@parallel(degree=4)\n"
        "def rule_b(x: Any) -> str:\n"
        "    return x.id\n\n"
        "for a in root.items:\n"
        "    out.X.append(rule_a(a))\n"
        "for b in root.items:\n"
        "    out.Y.append(rule_b(b))\n"
    )
    sql = compile_source(source, default_mapping_id="parallel_conflict", parallel_conflict="max")
    assert sql.count("FOR v_i_") == 2
