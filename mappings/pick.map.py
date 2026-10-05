from __mapping__ import *

# Picked-element golden mapping (docs/ARCHITECTURE.md, §Reading a field of a selected element): a
# field read from the first list element that satisfies a condition, nothing when none does.
# Every backend must agree (tests/golden/pick). Shape as generated from
#   Total:    source $.items[marker = 'TOTALS'].qty
#   Currency: source @totals.cur         (paths.aliases.totals = $.items[marker = 'TOTALS'])
#   Missing:  source $.items[marker = 'NOPE'].cur
#   Lines[*]: Price = $.prices[sku = @2.sku].price      (the condition reads the line as @2)
# The element is looked for once in each rule, however many times the rule reads it; the one
# that finds nothing is an empty object, so that reading a field of it gives nothing.


@dataclass
class LinesItem:
    Sku: str
    Price: number | None


def pick_items(root: Any) -> Any:
    found = []
    for item in root.items:
        if not (item.marker == "TOTALS"):
            continue
        found.append(item)
    if found:
        return found[0]
    return {}


def pick_nope(root: Any) -> Any:
    found = []
    for item in root.items:
        if not (item.marker == "NOPE"):
            continue
        found.append(item)
    if found:
        return found[0]
    return {}


def pick_prices(root: Any, src: Any) -> Any:
    found = []
    for price in root.prices:
        if not (price.sku == src.sku):
            continue
        found.append(price)
    if found:
        return found[0]
    return {}


def total(root: Any) -> number:
    total_items_pick = pick_items(root)
    return total_items_pick.qty


def currency(root: Any) -> str:
    currency_items_pick = pick_items(root)
    return currency_items_pick.cur


def missing(root: Any) -> str | None:
    missing_items_pick = pick_nope(root)
    return missing_items_pick.cur


def line(root: Any, src: Any) -> LinesItem:
    line_prices_pick = pick_prices(root, src)
    return LinesItem(Sku=src.sku, Price=line_prices_pick.price)


out.Total = total(root)
out.Currency = currency(root)
out.Missing = missing(root)
for src in root.lines:
    out.Lines.append(line(root, src))
