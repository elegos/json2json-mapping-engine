from cli.allowed import check_allowed, collect_constraints, unsupported_keywords
from transpiler.model import parse_functional


def _ff():
    return parse_functional(
        {
            "name": "m",
            "id": "m",
            "rules": [
                {
                    "kind": "loop",
                    "id": "l",
                    "source": "$.In[*]",
                    "output": "$.Orders[*]",
                    "rules": [
                        {
                            "kind": "field",
                            "id": "q",
                            "field": "Qty",
                            "type": "int",
                            "transform": {"expression": "@.q"},
                            "allowed": {"minimum": 0, "multipleOf": 5},
                        },
                        {
                            "kind": "field",
                            "id": "c",
                            "field": "Code",
                            "type": "str",
                            "transform": {"expression": "@.c"},
                            "allowed": {"pattern": "^[A-Z]{3}$", "minItems": 1},
                        },
                    ],
                }
            ],
        },
        "m",
    )


def test_collect_and_check_nested_loop():
    cons = collect_constraints(_ff())
    assert set(cons) == {("Orders", "Qty"), ("Orders", "Code")}
    out = {"Orders": [{"Qty": 10, "Code": "ABC"}, {"Qty": -3, "Code": "abc"}, {"Qty": None}]}
    assert check_allowed(out, cons) == [
        "Orders[1].Qty = -3: minimum 0",
        "Orders[1].Qty = -3: multipleOf 5",
        "Orders[1].Code = 'abc': pattern ^[A-Z]{3}$",
    ]


def test_unsupported_keywords_reported():
    assert unsupported_keywords(collect_constraints(_ff())) == [
        "Orders.Code: keyword 'minItems' is not supported on a scalar field (not evaluated)"
    ]


def test_other_keywords():
    cons = {("A",): {"multipleOf": 0.05, "const": 1.0}}
    assert check_allowed({"A": 0.1}, cons) == ["A = 0.1: const 1.0"]
    assert check_allowed({"A": 0.07}, {("A",): {"multipleOf": 0.05}}) == [
        "A = 0.07: multipleOf 0.05"
    ]
    assert check_allowed({"A": "2024-13-01"}, {("A",): {"format": "date"}}) == [
        "A = '2024-13-01': format date"
    ]
    any_of = {("A",): {"anyOf": [{"minimum": 10}, {"enum": [1]}], "not": {"const": 1}}}
    assert check_allowed({"A": 1}, any_of) == ["A = 1: not: value matches the forbidden schema"]
    assert check_allowed({"A": 5}, any_of) == ["A = 5: anyOf: no alternative matches"]
    assert check_allowed({"A": 2.5}, {("A",): {"type": "integer"}}) == ["A = 2.5: type integer"]
