from __mapping__ import *

__id__ = 'simple_object'


def order_id() -> str:
    return root.id


out.OrderId = order_id()


def amount() -> number:
    return root.price * root.qty


out.Amount = amount()


def discount_code() -> str | None:
    return coalesce(root.discountCode, "NONE")


out.DiscountCode = discount_code()
