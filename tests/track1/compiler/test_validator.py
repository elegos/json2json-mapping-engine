import ast

import pytest

from compiler.validator import Validator, ValidatorError


def validate(source: str) -> None:
    Validator().validate(ast.parse(source))


def test_permits_well_formed_field_rule():
    validate(
        "from __mapping__ import *\n\n"
        "def order_id() -> str:\n"
        "    return root.id\n\n"
        "out.OrderId = order_id()\n"
    )


def test_permits_direct_out_assignment_without_wrapping_def():
    validate("from __mapping__ import *\n\nout.Amount = root.price * root.qty\n")


def test_permits_id_directive():
    validate("__id__ = 'order_event_48'\n")


@pytest.mark.parametrize(
    "source",
    [
        "import os\n",
        "from os import path\n",
        "x = 1\n",
        "class Foo:\n    def bar(self): pass\n",
        "def f() -> int:\n    return (lambda: 1)()\n",
        "def f():\n    yield 1\n",
        "async def f() -> int:\n    return 1\n",
        "def f() -> int:\n    global x\n    return 1\n",
        "def f() -> int:\n    try:\n        return 1\n    except Exception:\n        return 2\n",
        "def f() -> int:\n    with open('x') as fh:\n        return 1\n",
        "def f(*args) -> int:\n    return 1\n",
        "def f(**kwargs) -> int:\n    return 1\n",
        "def f() -> int:\n    return eval('1')\n",
        "def f(x) -> int:\n    return x\n",  # missing param annotation
        "def f(x: int):\n    return x\n",  # missing return annotation
    ],
)
def test_blocks_disallowed_constructs(source: str):
    with pytest.raises(ValidatorError):
        validate(source)


def test_blocks_local_assignment_outside_function_body():
    with pytest.raises(ValidatorError, match="per-field function body"):
        validate("from __mapping__ import *\n\nx = root.id\nout.Id = x\n")


def test_blocks_import_from_other_than_mapping_stub():
    with pytest.raises(ValidatorError):
        validate("from json import dumps\n")


def test_dataclass_output_type_permitted():
    validate(
        "from __mapping__ import *\n\n"
        "@dataclass\n"
        "class OrderLine:\n"
        "    order_id: int\n"
        "    amount: number\n"
    )


def test_dataclass_with_method_blocked():
    with pytest.raises(ValidatorError):
        validate(
            "from __mapping__ import *\n\n"
            "@dataclass\n"
            "class OrderLine:\n"
            "    order_id: int\n"
            "    def helper(self):\n        return 1\n"
        )
