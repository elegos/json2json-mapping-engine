"""Rule id generation (docs/ARCHITECTURE.md, §Rule id generation).

Every rule has a *local* id. The fully-qualified id joins the local ids of a
rule and its ancestors with `.`; it is what identifies a rule uniquely within
a file. Generated identifiers (function names, local-variable prefixes, the
runtime error payload's `rule` key) are the fully-qualified id with `.`
replaced by `_` — a PL/SQL identifier cannot contain a dot.

Ids are stored in the `.fn.yaml`; a rule without one gets the deterministic
suggestion below (first three letters of its own path segment, lowercased,
`[]` stripped), with a numeric index appended to that segment on a sibling
collision (`sub`, `sub2`, `sub3`). Explicit ids are never renamed: a duplicate
explicit id is an error.
"""

from __future__ import annotations

import re

from transpiler.model import FieldRule, FnYamlError, FunctionalFile, LookupRule, Rule


def _segment(rule: Rule) -> str:
    if isinstance(rule, FieldRule):
        raw = rule.field
    elif isinstance(rule, LookupRule):
        raw = rule.label
    else:
        raw = rule.output.rstrip("]").removesuffix("[*").removesuffix("[").rsplit(".", 1)[-1]
    return raw


def suggest_local_id(rule: Rule) -> str:
    letters = re.sub(r"[^A-Za-z0-9]", "", _segment(rule))[:3].lower()
    return letters or "rul"


def _children(rule: Rule) -> list[Rule]:
    return getattr(rule, "rules", [])


def assign_ids(file: FunctionalFile) -> None:
    """Fill in missing ids (in place), then check uniqueness. Idempotent."""
    _assign_level(file.rules, "")
    idents: dict[str, str] = {}
    for fq, _rule in walk(file.rules):
        ident = fq.replace(".", "_")
        if ident in idents and idents[ident] != fq:
            raise FnYamlError(
                f"rules '{idents[ident]}' and '{fq}' collide once '.' becomes '_' "
                f"({ident}); rename one of the ids"
            )
        idents[ident] = fq


def _assign_level(rules: list[Rule], where: str) -> None:
    explicit = [r.id for r in rules if r.id is not None]
    dupes = sorted({i for i in explicit if explicit.count(i) > 1})
    if dupes:
        raise FnYamlError(f"{where or 'rules'}: duplicate rule id(s): {', '.join(dupes)}")
    taken = set(explicit)
    for rule in rules:
        if rule.id is None:
            base = suggest_local_id(rule)
            candidate, n = base, 2
            while candidate in taken:
                candidate = f"{base}{n}"
                n += 1
            rule.id = candidate
            taken.add(candidate)
    for rule in rules:
        _assign_level(_children(rule), f"{where}.{rule.id}".lstrip("."))


def walk(rules: list[Rule], prefix: str = ""):
    """Yield `(fully_qualified_id, rule)` depth-first."""
    for rule in rules:
        assert rule.id is not None, "call assign_ids first"
        fq = f"{prefix}.{rule.id}" if prefix else rule.id
        yield fq, rule
        yield from walk(_children(rule), fq)


def ident_of(fq_id: str) -> str:
    return fq_id.replace(".", "_")
