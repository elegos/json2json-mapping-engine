from __mapping__ import *

__id__ = 'aggregates'


def max_price(root: Any) -> number:
    return max(root.items, "price")


out.MaxPrice = max_price(root)


def total_price(root: Any) -> number:
    return sum(root.items, "price")


out.TotalPrice = total_price(root)


out.ItemCount = count(root.items)
