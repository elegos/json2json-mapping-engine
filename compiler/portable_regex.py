"""The patterns of `matches(text, pattern)`: a small subset of regular expressions that Python's
`re` and Oracle's `REGEXP_LIKE` read the same way, so that the same mapping gives the same result on
every backend (the dialect exception of `regexp_replace` / `regexp_group` does not reach it).

The whole text must fit the pattern. Allowed: literal characters, `.`, `[...]` (characters and
`a-z` ranges, with a leading `^` to negate; no escapes and no `[:class:]` inside), `( ... )` groups,
`|`, the quantifiers `* + ? {n} {n,} {n,m}`, and `\\` before a metacharacter. Not allowed: `^` and
`$` (the text is always matched whole), `\\d \\w \\s \\b`, back-references, `(?...)`, lazy or possessive
quantifiers: what they mean is not the same in both dialects."""

from __future__ import annotations

import re

_META = set(".[]()|*+?{}\\^$-/")
_BRACES = re.compile(r"\{(\d+)(,(\d*))?\}")


def portable_regex_error(pattern: str) -> str | None:
    """Why `pattern` is not in the portable subset; None when it is."""
    if pattern == "":
        return "the pattern is empty"
    depth = 0
    i = 0
    previous = ""  # "atom" after something a quantifier may follow, "quant" after one
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            nxt = pattern[i + 1 : i + 2]
            if nxt == "" or nxt not in _META:
                return (
                    f"'\\{nxt}' is not portable: write the characters out ([0-9], [A-Za-z]) "
                    "instead of \\d \\w \\s \\b or a back-reference"
                )
            i += 2
            previous = "atom"
        elif ch == "[":
            end = i + 1
            if pattern[end : end + 1] == "^":
                end += 1
            if pattern[end : end + 1] == "]":
                return "an empty character class"
            while end < len(pattern) and pattern[end] != "]":
                if pattern[end] in "\\[":
                    return "a character class holds characters and ranges only (no \\ and no [:class:])"
                end += 1
            if end >= len(pattern):
                return "a [ is never closed"
            i = end + 1
            previous = "atom"
        elif ch == "(":
            if pattern[i + 1 : i + 2] == "?":
                return "(?...) groups are not portable"
            depth += 1
            i += 1
            previous = ""
        elif ch == ")":
            if previous == "":
                return "an empty group or alternative"
            depth -= 1
            if depth < 0:
                return "a ) with no ( before it"
            i += 1
            previous = "atom"
        elif ch in "*+?":
            if previous != "atom":
                return f"'{ch}' repeats nothing"
            i += 1
            previous = "quant"
            if pattern[i : i + 1] in ("?", "+"):
                return "lazy and possessive quantifiers are not portable"
        elif ch == "{":
            found = _BRACES.match(pattern, i)
            if found is None or previous != "atom":
                return "a { that is not a quantifier {n}, {n,} or {n,m}"
            low, high = int(found[1]), found[3]
            if high not in (None, "") and int(high) < low:
                return "a quantifier with its limits the wrong way round"
            i = found.end()
            previous = "quant"
            if pattern[i : i + 1] in ("?", "+"):
                return "lazy and possessive quantifiers are not portable"
        elif ch in "^$":
            return "^ and $ are not needed (the whole text is matched) and not portable"
        elif ch == "|":
            if previous == "":
                return "an empty alternative"
            i += 1
            previous = ""
        elif ch in "]}":
            return f"'{ch}' with nothing to close: write \\{ch} for the character itself"
        else:  # . or a literal
            i += 1
            previous = "atom"
    if depth != 0:
        return "a ( is never closed"
    if previous == "":
        return "an empty alternative"
    return None
