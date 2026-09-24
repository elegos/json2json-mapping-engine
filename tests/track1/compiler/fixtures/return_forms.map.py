from __mapping__ import *

__id__ = 'return_forms'


def status_label() -> str | Null:
    if root.status == "ACTIVE":
        return "Active"
    elif root.status == "CANCELLED":
        return Null
    else:
        return


out.StatusLabel = status_label()


def risky_amount() -> number:
    return root.amount / root.divisor


out.RiskyAmount = risky_amount()
