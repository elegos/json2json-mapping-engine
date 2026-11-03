"""`order by`: the one way a functional file says how a list is ordered, in a loop's `order_by`
and in the condition of a selection (`$.events[kind == 'K1' order by rank desc]`).

    <expression> [asc | desc] [nulls first | nulls last] {, <expression> ...}

The expression is any expression of the element (`@.f`, or a bare name where a selection writes
the element's fields). Ascending and nulls last are the defaults. An element whose key is
missing goes first or last as stated, whatever the direction; elements with equal keys keep the
order they have. Several keys order by the first, and by the next among equal ones."""

from __future__ import annotations

import re
from dataclasses import dataclass

# a trailing `asc | desc` and `nulls first | last`, in either order after the direction
_TAIL = re.compile(
    r"^(?P<expr>.*?)(?:\s+(?P<dir>asc|desc))?(?:\s+nulls\s+(?P<nulls>first|last))?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_ORDER_BY = re.compile(r"\border\s+by\b", re.IGNORECASE)


@dataclass(frozen=True)
class OrderKey:
    expr: str
    desc: bool = False
    nulls_first: bool = False

    def text(self) -> str:
        tail = (" desc" if self.desc else "") + (" nulls first" if self.nulls_first else "")
        return self.expr + tail


def split_top_level(text: str, sep: str = ",") -> list[str]:
    """`text` cut at `sep` outside brackets and quotes."""
    parts: list[str] = []
    depth, quote, start = 0, "", 0
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def parse_order_by(text: str) -> list[OrderKey]:
    """The keys of an `order by` list (without the words `order by`). Raises ValueError saying
    what is wrong."""
    keys: list[OrderKey] = []
    for part in split_top_level(text):
        found = _TAIL.match(part.strip())
        expr = (found["expr"] if found else part).strip()
        if not expr:
            raise ValueError("an order key needs an expression before asc / desc / nulls")
        if re.search(r"\s(?:asc|desc|nulls)\b[^()]*$", " " + expr, re.IGNORECASE):
            raise ValueError(
                f"'{part.strip()}': after the expression only asc | desc and nulls first | nulls last"
            )
        keys.append(
            OrderKey(
                expr,
                desc=bool(found and (found["dir"] or "").lower() == "desc"),
                nulls_first=bool(found and (found["nulls"] or "").lower() == "first"),
            )
        )
    if not keys:
        raise ValueError("order by needs at least one key")
    return keys


def format_order_by(keys: list[OrderKey]) -> str:
    return ", ".join(k.text() for k in keys)


def split_selection_order(condition: str) -> tuple[str, str | None]:
    """A selection's condition `cond order by <keys>`: the condition (possibly empty) and the keys
    text; the clause is looked for outside brackets and quotes."""
    depth, quote = 0, ""
    for i, ch in enumerate(condition):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0:
            found = _ORDER_BY.match(condition, i)
            if found and (i == 0 or condition[i - 1].isspace()):
                return condition[:i].strip(), condition[found.end() :].strip()
    return condition.strip(), None
