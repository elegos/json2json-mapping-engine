"""Element selection by a predicate (docs/ARCHITECTURE.md, §Selecting one element).

An `object` rule may have a Source of the form `<list path>[<condition>]`:

    $.myList[discriminator = 'MY DISCRIMINATOR' and other = $.rootElement]

The object is built from the first element of the list for which the condition is true
(nothing is built when none is), and the rules inside read that element as `@`.
In the condition a bare name is a field of the candidate element, `=` is `==`, and `$`
is the document root.

The same condition can sit in the middle of a path read by a field (a Source, an expression, a
guard): `$.items[marker = 'TOTALS'].qty` is the `qty` of the first element that satisfies it
(nothing when none does). `find_selections` finds those in a text.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass

from transpiler.anchors import _split_strings
from transpiler.model import FnYamlError, FunctionalFile, LoopRule, ObjectRule, Rule

_KEYWORDS = frozenset(
    {"and", "or", "not", "in", "is", "if", "else", "True", "False", "None", "Null"}
)
_SINGLE_EQUALS = re.compile(r"(?<![=!<>])=(?!=)")
_BARE_NAME = re.compile(r"(?<![\w.@$])([A-Za-z_]\w*)(?!\w)(?!\s*\()")
_POSITION = re.compile(r"^\s*(\*|\d*)\s*$")


def split_selector(source: str) -> tuple[str, str] | None:
    """`$.a.list[cond]` -> (`$.a.list`, `cond`); None when the source has no condition
    (a plain path, or one ending in `[*]` / `[0]`)."""
    text = source.strip()
    if not text.endswith("]"):
        return None
    depth, start, quote = 0, -1, ""
    last: tuple[int, int] | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                last = (start, i)
        i += 1
    if last is None or last[1] != len(text) - 1 or depth != 0:
        return None
    condition = text[last[0] + 1 : last[1]]
    if _POSITION.match(condition):
        return None
    return text[: last[0]], condition.strip()


@dataclass(frozen=True)
class Selection:
    """`$.items[marker = 'TOTALS']` found in a text: where it is, the list path, the condition."""

    start: int
    end: int  # just after the `]`
    path: str
    condition: str


# the path a condition hangs from: an anchor and fields / positions, up to the `[`
_HEAD = re.compile(r"(?<![\w.$@])(?:\$|@(?:\d+|[A-Za-z_]\w*)?)(?:\.[A-Za-z_]\w*|\[(?:\*|\d+)?\])*$")


def _closing(text: str, start: int) -> int | None:
    """The index of the `]` that closes the `[` at `start` (strings and nesting aware)."""
    depth, quote, i = 0, "", start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def find_selections(text: str) -> list[Selection]:
    """The selections of `text`, left to right: a path followed by `[condition]` (not a
    position such as `[0]` or `[*]`). Text in quotes is not looked at; a bracket after anything
    but a `$` / `@` path (a subscript of a local variable) is not a selection."""
    found: list[Selection] = []
    quote, i = "", 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "[":
            close = _closing(text, i)
            if close is None:
                break
            inner = text[i + 1 : close]
            head = _HEAD.search(text[:i])
            if head and not _POSITION.match(inner):
                found.append(Selection(head.start(), close + 1, head.group(0), inner.strip()))
            i = close
        i += 1
    return found


def replace_selections(text: str, replacement: Callable[[Selection], str]) -> str:
    """`text` with each selection replaced by `replacement(selection)`."""
    out, at = [], 0
    for sel in find_selections(text):
        out += [text[at : sel.start], replacement(sel)]
        at = sel.end
    return "".join(out) + text[at:]


def normalize_condition(condition: str) -> str:
    """The condition in explicit form: `=` becomes `==` and a bare name `x` becomes `@.x`."""

    def chunk(text: str) -> str:
        text = _SINGLE_EQUALS.sub("==", text)

        def name(m: re.Match[str]) -> str:
            return m.group(0) if m.group(1) in _KEYWORDS else f"@.{m.group(1)}"

        return _BARE_NAME.sub(name, text)

    return "".join(s if is_str else chunk(s) for is_str, s in _split_strings(condition))


def qualify_selector(source: str, in_loop: bool) -> str:
    """The Source of a selecting object in explicit form: the list path gets its `$.` / `@.`
    and the condition its `@.` field prefixes."""
    from transpiler.model import qualify_source

    split = split_selector(source)
    if split is None:
        return source.strip()
    path, condition = split
    return f"{qualify_source(path, in_loop)}[{normalize_condition(condition)}]"


def lower_selectors(file: FunctionalFile) -> FunctionalFile:
    """A copy in which every selecting object is a `first` loop over the list, filtered by
    the condition: the element rules are generated as for a loop, and the result is its first
    element."""
    lowered = copy.deepcopy(file)

    def rewrite(rules: list[Rule]) -> list[Rule]:
        out: list[Rule] = []
        for rule in rules:
            if isinstance(rule, ObjectRule | LoopRule):
                rule.rules = rewrite(rule.rules)
            if isinstance(rule, ObjectRule) and rule.source:
                split = split_selector(rule.source)
                if split is None:
                    raise FnYamlError(f"'{rule.output}': the source of an object needs a condition")
                path, condition = split
                rule = LoopRule(
                    id=rule.id,
                    source=f"{path}[*]",
                    output=rule.output,
                    filter=condition,
                    description=rule.description,
                    rules=rule.rules,
                    first=True,
                )
            out.append(rule)
        return out

    lowered.rules = rewrite(lowered.rules)
    return lowered
