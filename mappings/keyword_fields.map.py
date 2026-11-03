from __mapping__ import *

# A field named like a Python keyword (`return`, `from`), read as `root["return"]` (what the
# transpiler writes for `$.return.number`). Every backend must agree (tests/golden/keyword_fields).


def number(root: Any) -> str:
    return root["return"].number


out.Number = number(root)


def from_a(root: Any) -> number:
    return count(i for i in root["return"].items if i["from"] == "A")


out.FromA = from_a(root)
