from __mapping__ import *

__id__ = 'fused_lines'


@dataclass
class LineId:
    LineId: str


@dataclass
class LineAmount:
    LineAmount: number


def line_id_rule(itm: Any) -> LineId:
    return LineId(LineId=itm.id)


def line_amount_rule(itm: Any) -> LineAmount:
    return LineAmount(LineAmount=itm.price)


for itm in root.items:
    out.Ids.append(line_id_rule(itm))

for itm in root.items:
    if itm.status == "INACTIVE":
        continue
    out.Amounts.append(line_amount_rule(itm))
