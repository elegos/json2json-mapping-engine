from __mapping__ import *

__id__ = 'nested_output'


@dataclass
class Line:
    Pos: int
    LineId: str
    Price: number


@dataclass
class Tax:
    Rate: number


@dataclass
class Order:
    OrderId: str
    Tax: Tax
    Lines: list[Line]


def line_rule(root: Any, o: Any, l: Any, j: int) -> Line:
    return Line(Pos=j, LineId=l.id, Price=l.price)


def tax_rule(root: Any, o: Any) -> Tax:
    if o.taxRate != None:
        return Tax(Rate=o.taxRate)
    else:
        return


def order_rule(root: Any, o: Any) -> Order:
    lines = []
    for j, l in enumerate([l for l in sorted(o.lines, key="price") if l.active == True], start=1):
        lines.append(line_rule(root, o, l, j))
    return Order(OrderId=o.id, Tax=tax_rule(root, o), Lines=lines)


for o in root.orders:
    out.Orders.append(order_rule(root, o))
