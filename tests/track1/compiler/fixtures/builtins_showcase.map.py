from __mapping__ import *

__id__ = 'builtins_showcase'


def rounded_amount(root: Any) -> number:
    return round(root.amount, 2)


out.RoundedAmount = rounded_amount(root)


def full_name(root: Any) -> str:
    return concat(root.firstName, " ", root.lastName)


out.FullName = full_name(root)


def tier_label(root: Any) -> str:
    return if_else(root.score >= 90, "GOLD", "STANDARD")


out.TierLabel = tier_label(root)


def ref_first(root: Any) -> str:
    return split_first(root.ref, "|")


out.RefFirst = ref_first(root)


def ref_second(root: Any) -> str | None:
    return split_nth(root.ref, "|", 2)


out.RefSecond = ref_second(root)


def currency(root: Any) -> str | None:
    return lookup(root.countryCode, root.currencyTable, "EUR")


out.Currency = currency(root)


def shipped_on(root: Any) -> date:
    return parse_date(root.shippedOn, "YYYY-MM-DD")


out.ShippedOn = shipped_on(root)
