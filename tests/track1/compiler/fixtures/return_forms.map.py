from __mapping__ import *

__id__ = 'return_forms'


def status_label(root: Any) -> str | Null:
    if root.status == "ACTIVE":
        return "Active"
    elif root.status == "CANCELLED":
        return Null
    else:
        return


out.StatusLabel = status_label(root)


def risky_amount(root: Any) -> number:
    return root.amount / root.divisor


out.RiskyAmount = risky_amount(root)
