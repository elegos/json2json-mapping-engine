"""Stage 2 — Anchor Resolver (docs/ARCHITECTURE.md, §Scope anchors).

Rewrites the functional dialect into the developer dialect, textually:

    $                         -> root
    @ / @1 / @<nearest label> -> the nearest loop's item      (`src`)
    @2 / @<outer label>       -> the next loop out            (`src1`, `src2`, ...)
    @index / @index.2         -> that loop's position         (`index`, `index1`, ...)
    @<lookup label>           -> the lookup's entries as a dict literal
    @.field / $.a.b           -> src.field / root.a.b   (the `.field` is untouched)

String literals are skipped, so `'user@example.com'` and `"$5"` survive.

What each loop's item/index is *called* depends on the frame being resolved
for: inside a generated rule function they are `src`/`src1`/... (innermost
first); in the parent function's own `for` statement over a child loop's
elements, the child's item is `<id>_src`. The scope carries those names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from transpiler.model import FnYamlError

_ANCHOR = re.compile(r"\$|@(?:index(?:\.\d+)?(?![\w])|\d+|[A-Za-z_]\w*)?")


@dataclass(frozen=True)
class LoopRef:
    label: str | None
    item: str  # python name of this loop's current element
    index: str  # python name of this loop's position


@dataclass
class AnchorScope:
    """Enclosing loops, outermost first."""

    loops: tuple[LoopRef, ...] = ()
    lookups: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class Resolved:
    text: str
    index_offsets: set[int] = field(default_factory=set)  # 0 = nearest loop's index

    @property
    def uses_index(self) -> bool:
        return bool(self.index_offsets)


def _split_strings(text: str) -> list[tuple[bool, str]]:
    """[(is_string_literal, chunk)] — handles both quote styles and backslash
    escapes; an unterminated literal runs to the end (ast.parse reports it later)."""
    parts: list[tuple[bool, str]] = []
    buf: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"":
            if buf:
                parts.append((False, "".join(buf)))
                buf = []
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            parts.append((True, text[i : j + 1]))
            i = j + 1
        else:
            buf.append(ch)
            i += 1
    if buf:
        parts.append((False, "".join(buf)))
    return parts


def resolve_anchors(text: str, scope: AnchorScope, where: str) -> Resolved:
    out = Resolved(text="")
    depth = len(scope.loops)

    def nearest(offset: int, what: str) -> LoopRef:
        if depth == 0:
            raise FnYamlError(
                f"{where}: '{what}' used outside a loop (use '$' for the document root)"
            )
        if offset >= depth:
            raise FnYamlError(
                f"{where}: '{what}' reaches {offset + 1} loop(s) out, but only {depth} enclose this rule"
            )
        return scope.loops[depth - 1 - offset]

    def sub(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok == "$":
            return "root"
        name = tok[1:]
        if name == "":
            return nearest(0, "@").item
        if name.startswith("index"):
            offset = int(name.split(".", 1)[1]) - 1 if "." in name else 0
            if offset < 0:
                raise FnYamlError(f"{where}: '@{name}' — loops are counted from 1")
            ref = nearest(offset, f"@{name}")
            out.index_offsets.add(offset)
            return ref.index
        if name.isdigit():
            if int(name) < 1:
                raise FnYamlError(f"{where}: '@{name}' — loops are counted from 1")
            return nearest(int(name) - 1, f"@{name}").item
        for offset in range(depth):
            ref = scope.loops[depth - 1 - offset]
            if ref.label == name:
                return ref.item
        if name in scope.lookups:
            return repr(scope.lookups[name])
        raise FnYamlError(f"{where}: unknown anchor '@{name}' (not a loop label or lookup)")

    chunks = []
    for is_str, chunk in _split_strings(text):
        chunks.append(chunk if is_str else _ANCHOR.sub(sub, chunk))
    out.text = "".join(chunks)
    return out
