from __mapping__ import *

__id__ = 'enumerate_sorted'


@dataclass
class Line:
    Position: int
    LineId: str
    Price: number


def line_rule(idx: int, itm: Any) -> Line:
    return Line(Position=idx, LineId=itm.id, Price=itm.price)


for i, itm in enumerate(sorted(root.items, key="price"), start=1):
    out.Lines.append(line_rule(i, itm))
