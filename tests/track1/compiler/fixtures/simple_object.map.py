from __mapping__ import *

__id__ = 'simple_object'


def order_id(root: Any) -> str:
    return root.id


out.OrderId = order_id(root)


def amount(root: Any) -> number:
    return root.price * root.qty


out.Amount = amount(root)


def discount_code(root: Any) -> str | None:
    return coalesce(root.discountCode, "NONE")


out.DiscountCode = discount_code(root)
