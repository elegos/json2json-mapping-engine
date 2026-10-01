"""Path aliases and the root override (docs/ARCHITECTURE.md, §Paths section).

A `.fn.yaml` may redefine what `$` means (`paths.root`) and name paths (`paths.aliases`).
The rules keep the text the user wrote; `expand_paths` returns a copy in which every
input path is spelled from the real document root, so the rest of the pipeline (check,
transpile) never sees an alias:

    $            -> paths.root  (or `$` when there is none)
    @root        -> $           (always the real document root)
    @<alias>     -> the alias's path

Output paths (`output:`) are not touched: they live in the output document.
"""

from __future__ import annotations

import copy
import re

from transpiler.anchors import _split_strings
from transpiler.model import (
    FieldRule,
    FunctionalFile,
    LoopRule,
    ObjectRule,
    PathsSection,
    Rule,
)

_TOKEN = re.compile(r"\$|@[A-Za-z_]\w*")


def expand_text(text: str | None, paths: PathsSection) -> str | None:
    """Rewrite `$`, `@root` and `@<alias>` in an expression or path (string literals are
    left alone). One pass: the text a token expands to is not scanned again."""
    if not text:
        return text

    def sub(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok == "$":
            return paths.root or "$"
        name = tok[1:]
        if name == "root":
            return "$"
        return paths.aliases.get(name, tok)

    return "".join(
        chunk if is_str else _TOKEN.sub(sub, chunk) for is_str, chunk in _split_strings(text)
    )


def _expand_rules(rules: list[Rule], paths: PathsSection) -> None:
    for rule in rules:
        if isinstance(rule, FieldRule):
            rule.source_path = expand_text(rule.source_path, paths)
            rule.transform.expression = expand_text(rule.transform.expression, paths)
            rule.transform.code_override = expand_text(rule.transform.code_override, paths)
        elif isinstance(rule, ObjectRule):
            rule.guard = expand_text(rule.guard, paths)
            _expand_rules(rule.rules, paths)
        elif isinstance(rule, LoopRule):
            rule.source = expand_text(rule.source, paths) or ""
            rule.filter = expand_text(rule.filter, paths)
            rule.sort_key = expand_text(rule.sort_key, paths)
            _expand_rules(rule.rules, paths)


def expand_paths(file: FunctionalFile) -> FunctionalFile:
    """A copy of `file` with root override and aliases applied to every input path."""
    expanded = copy.deepcopy(file)
    _expand_rules(expanded.rules, expanded.paths)
    return expanded
