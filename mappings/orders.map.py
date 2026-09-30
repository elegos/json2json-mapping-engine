from __mapping__ import *

# Example mapping, also the integration suite's fixture (tests/golden/orders).
# `@parallel` makes the PL/SQL backend emit the SQL-callable wrapper map_orders_fn.


@dataclass
class OrdersLine:
    Sku: str
    Qty: int


def order_id(root: Orders) -> str:
    return root.id


@parallel(degree=2)
def line(root: Orders, src: Ordersitem) -> OrdersLine:
    return OrdersLine(Sku=src.sku, Qty=src.qty)


out.OrderId = order_id(root)

for src in root.items:
    out.Lines.append(line(root, src))
