from __mapping__ import *

__id__ = 'lines_array'


@dataclass
class Line:
    LineId: str
    LineAmount: number


def line_rule(itm: Any) -> Line:
    return Line(LineId=itm.id, LineAmount=itm.price)


for itm in root.items:
    out.Lines.append(line_rule(itm))
