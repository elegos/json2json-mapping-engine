"""Stage 2 — Anchor Resolver (docs/ARCHITECTURE.md, §Scope anchors).

Rewrites the functional dialect into the developer dialect, textually:

    $           -> root
    @ / @1 / @<loop label>  -> src        (the nearest loop's item)
    @index      -> index
    @<lookup label>         -> the lookup's entries as a dict literal
    @.field / $.a.b         -> src.field / root.a.b   (the `.field` is untouched)

String literals are skipped, so `'user@example.com'` and `"$5"` survive.

Only one loop level exists in what the compiler can express today (nested
output loops need compiler work), so `@2`, `@index.2` and any outer-loop label
are errors that say so, rather than silently resolving to something.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from transpiler.model import FnYamlError

_ANCHOR = re.compile(r"\$|@(?:index(?:\.\d+)?(?![\w])|\d+|[A-Za-z_]\w*)?")


@dataclass
class AnchorScope:
    """What `@` can mean at the point being resolved."""

    loop_label: str | None = None  # None = not inside a loop
    in_loop: bool = False
    lookups: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class Resolved:
    text: str
    uses_index: bool = False
    uses_src: bool = False
    uses_root: bool = False


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

    def sub(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok == "$":
            out.uses_root = True
            return "root"
        name = tok[1:]
        if name == "":
            return _item(scope, where, out)
        if name.startswith("index"):
            if "." in name:
                raise FnYamlError(
                    f"{where}: '@{name}' — outer-loop indexes need nested loops, which the "
                    "compiler does not support yet"
                )
            if not scope.in_loop:
                raise FnYamlError(f"{where}: '@index' used outside a loop")
            out.uses_index = True
            return "index"
        if name.isdigit():
            if name != "1":
                raise FnYamlError(
                    f"{where}: '@{name}' — only one loop level is supported by the compiler today"
                )
            return _item(scope, where, out)
        if scope.in_loop and name == scope.loop_label:
            return _item(scope, where, out)
        if name in scope.lookups:
            return repr(scope.lookups[name])
        raise FnYamlError(f"{where}: unknown anchor '@{name}' (not a loop label or lookup)")

    chunks = []
    for is_str, chunk in _split_strings(text):
        chunks.append(chunk if is_str else _ANCHOR.sub(sub, chunk))
    out.text = "".join(chunks)
    return out


def _item(scope: AnchorScope, where: str, out: Resolved) -> str:
    if not scope.in_loop:
        raise FnYamlError(f"{where}: '@' used outside a loop (use '$' for the document root)")
    out.uses_src = True
    return "src"
