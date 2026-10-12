from __mapping__ import *

# Rules that write into the root under a guard (`kind: object`, `output: $` in a functional): the
# mapping has no notion of alternative shapes, whoever writes it guards the rules of each shape.
# Every backend must agree (tests/golden/groups).


def post_op(root: Any) -> str:
    return "POST"


def post_name(root: Any) -> str:
    return upper(root.name)


def delete_op(root: Any) -> str:
    return "DELETE"


def the_id(root: Any) -> str:
    return root.id


if root.operation == "POST":
    out.operation = post_op(root)
    out.id = the_id(root)
    out.name = post_name(root)

if root.operation == "DELETE":
    out.operation = delete_op(root)
    out.id = the_id(root)
