import pytest

from compiler.backends.plsql.builtins import BUILTIN_FUNCTIONS, BUILTIN_PYTHON_REFERENCE

# -- Python reference implementations (target-independent) --------------------


def test_coalesce_reference():
    ref = BUILTIN_PYTHON_REFERENCE["coalesce"]
    assert ref(None, "fallback") == "fallback"
    assert ref("value", "fallback") == "value"


def test_round_reference_is_half_up_not_bankers_rounding():
    ref = BUILTIN_PYTHON_REFERENCE["round"]
    # Python's builtin round(2.5) == 2 (banker's rounding) — the DSL's
    # `round` must be half-up per the architecture's financial convention.
    assert ref(2.5, 0) == 3.0
    assert ref(1.005, 2) == 1.01
    assert ref(-1.5, 0) == -2.0


def test_concat_reference():
    assert BUILTIN_PYTHON_REFERENCE["concat"]("a", " ", "b") == "a b"


def test_if_else_reference():
    ref = BUILTIN_PYTHON_REFERENCE["if_else"]
    assert ref(True, "x", "y") == "x"
    assert ref(False, "x", "y") == "y"


def test_split_first_reference():
    ref = BUILTIN_PYTHON_REFERENCE["split_first"]
    assert ref("a|b|c", "|") == "a"
    assert ref("a", "|") == "a"


def test_split_nth_reference():
    ref = BUILTIN_PYTHON_REFERENCE["split_nth"]
    assert ref("a;b;c", ";", 2) == "b"
    assert ref("a;b;c", ";", 99) is None
    assert ref("a;b;c", ";", 0) is None


def test_lookup_reference():
    ref = BUILTIN_PYTHON_REFERENCE["lookup"]
    assert ref("A", {"A": "EUR", "B": "USD"}) == "EUR"
    assert ref("Z", {"A": "EUR"}) is None
    assert ref("Z", {"A": "EUR"}, "USD") == "USD"


def test_parse_date_reference():
    ref = BUILTIN_PYTHON_REFERENCE["parse_date"]
    d = ref("2026-09-23", "YYYY-MM-DD")
    assert (d.year, d.month, d.day) == (2026, 9, 23)


# -- PL/SQL rendering ------------------------------------------------------------


@pytest.mark.parametrize(
    "name,args,expected",
    [
        ("coalesce", ["A", "B"], "COALESCE(A, B)"),
        ("round", ["A", "2"], "ROUND(A, 2)"),
        ("if_else", ["C", "A", "B"], "(CASE WHEN C THEN A ELSE B END)"),
        ("concat", ["A", "B", "C"], "(A || B || C)"),
    ],
)
def test_plsql_rendering(name: str, args: list[str], expected: str):
    assert BUILTIN_FUNCTIONS[name].render("plsql", args) == expected


def test_lookup_plsql_rendering_with_and_without_default():
    impl = BUILTIN_FUNCTIONS["lookup"]
    assert impl.render("plsql", ["A", "T"]) == "(CASE WHEN T.has(A) THEN T.get_String(A) ELSE NULL END)"
    assert (
        impl.render("plsql", ["A", "T", "'EUR'"])
        == "(CASE WHEN T.has(A) THEN T.get_String(A) ELSE 'EUR' END)"
    )


def test_split_nth_plsql_rendering_shape():
    rendered = BUILTIN_FUNCTIONS["split_nth"].render("plsql", ["S", "SEP", "2"])
    assert rendered.startswith("(CASE WHEN")
    assert "INSTR" in rendered and "SUBSTR" in rendered
