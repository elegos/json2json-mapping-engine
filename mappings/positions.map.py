from __mapping__ import *

# Array positions golden mapping (docs/ARCHITECTURE.md, §Paths section): a constant position
# in a document path, `root.a.list[0].id`. Every backend must read the same elements as Python
# (tests/golden/positions).


@dataclass
class Positions:
    First: str
    SecondQty: int | None
    LastTag: str | None
    Flagged: str


def first(root: Any) -> str:
    return root.tx.list[0].id


def second_qty(root: Any) -> int | None:
    return root.tx.list[1].qty


def last_tag(root: Any) -> str | None:
    return root.tx.tags[2]


def flagged(root: Any) -> str:
    return if_else(root.tx.list[0].flag, "T", "F")


out.First = first(root)
out.SecondQty = second_qty(root)
out.LastTag = last_tag(root)
out.Flagged = flagged(root)
