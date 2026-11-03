from __mapping__ import *

# Nothing to write versus an explicit null, golden mapping (docs/ARCHITECTURE.md, §Return
# semantics): a value that is `None` is not written, `Null` is written as a null, whatever the
# route to the output (a rule, a direct assignment, a field of an object, an element of a list,
# an aggregate with nothing to aggregate). Every backend must agree (tests/golden/null_forms).


@dataclass
class Box:
    Kept: str
    Gone: str | None
    Nulled: str | Null


def none_rule(root: Any) -> str | None:
    return root.missing


def null_rule(root: Any) -> str | Null:
    return Null


def number_none(root: Any) -> number | None:
    return root.n + 1


def box(root: Any) -> Box:
    return Box(Kept="k", Gone=root.missing, Nulled=Null)


def biggest(root: Any) -> number | None:
    return max(i.v for i in root.items if i.ok)


def total(root: Any) -> number:
    return sum(i.v for i in root.items if i.ok)


out.NoneRule = none_rule(root)
out.NullRule = null_rule(root)
out.NumberNone = number_none(root)
out.Direct = root.missing
out.DirectNull = Null
out.Box = box(root)
out.Biggest = biggest(root)
out.Total = total(root)


def looked(root: Any) -> str:
    return lookup(root.kind, {}, "unknown")


out.Looked = looked(root)
