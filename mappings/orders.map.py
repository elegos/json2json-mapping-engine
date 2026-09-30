from __mapping__ import *

# Example mapping, also the integration suite's fixture (tests/golden/orders).
# `@parallel` makes the PL/SQL backend emit the SQL-callable wrapper map_orders_fn.
# `split_first`, `split_nth` and `lookup` are built-ins kept in the functions package
# (J2JME_FUNCTIONS).
# `unit_price` is a nested rule call: when it fails (zero quantity) only the line's `Unit`
# is left out, the line itself is kept and the failure is reported under `unit_price`.


@dataclass
class OrdersLine:
    Sku: str
    Qty: int
    Family: str
    Unit: number | None


def unit_price(src: Ordersitem) -> number | None:
    return src.total / src.qty


def order_id(root: Orders) -> str:
    return root.id


@parallel(degree=2)
def line(root: Orders, src: Ordersitem) -> OrdersLine:
    return OrdersLine(Sku=src.sku, Qty=src.qty, Family=split_first(src.sku, "-"), Unit=unit_price(src))




def currency(root: Orders) -> str | None:
    return lookup(root.country, root.currencies, "N/A")


def warehouse(root: Orders) -> str | None:
    return split_nth(root.ref, ",", 2)


out.OrderId = order_id(root)
out.Currency = currency(root)
out.Warehouse = warehouse(root)

for src in root.items:
    out.Lines.append(line(root, src))
