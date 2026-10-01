"""Review state of the rules of a file, beyond `validated` / `needs_review` (docs/ARCHITECTURE.md,
§Auto / Manual mode and §Rule validation):

- a *manual* rule keeps `transform.last_auto_version`, the code the transpiler generated when the
  developer took over; when what it generates now differs, the rule's functional side moved
  under the override (`stale_override`), and the developer decides between the new proposal and
  the override;
- a *validated* rule keeps `validation.functions`, a fingerprint of every function its
  expression called when it was validated; when one of them changed (or went away), the
  validation may no longer hold (`changed_functions`).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace

from compiler.function_registry import FunctionInfo
from transpiler.anchors import _split_strings
from transpiler.ids import assign_ids, walk
from transpiler.model import (
    FieldRule,
    FnYamlError,
    FunctionalFile,
    LoopRule,
    ObjectRule,
    Rule,
)
from transpiler.transpile import auto_proposals

_CALL = re.compile(r"(?<![\w.@$])([A-Za-z_]\w*)\s*\(")


def functions_used(text: str | None, functions: Mapping[str, FunctionInfo]) -> list[str]:
    """Names of the registered functions an expression calls (string literals skipped)."""
    code = "".join(chunk for is_string, chunk in _split_strings(text or "") if not is_string)
    return sorted({m[1] for m in _CALL.finditer(code) if m[1] in functions})


def fingerprints(rule: FieldRule, functions: Mapping[str, FunctionInfo]) -> dict[str, str]:
    """What `validation.functions` records: the functions the rule calls, with their hash."""
    text = rule.transform.code_override if rule.transform.status == "manual" else None
    names = functions_used(text if text is not None else rule.transform.expression, functions)
    return {n: functions[n].fingerprint for n in names}


def set_validated(
    rule: FieldRule, validated: bool, functions: Mapping[str, FunctionInfo]
) -> FieldRule:
    """The rule with `validated` set; validating records the fingerprints, un-validating
    forgets them."""
    v = replace(
        rule.validation,
        validated=validated,
        needs_review=False if validated else rule.validation.needs_review,
        functions=fingerprints(rule, functions) if validated else {},
    )
    return replace(rule, validation=v)


@dataclass
class RuleReview:
    path: str  # `rules[0].rules[1]`, as the check's diagnostics name a rule
    stale_override: bool = False
    proposal_error: str | None = None  # a manual rule whose auto code cannot be generated
    changed_functions: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "rule": self.path,
            "stale_override": self.stale_override,
            "proposal_error": self.proposal_error,
            "changed_functions": self.changed_functions,
        }


def _with_paths(rules: list[Rule], prefix: str = "") -> Iterator[tuple[str, Rule]]:
    for i, rule in enumerate(rules):
        path = f"{prefix}rules[{i}]"
        yield path, rule
        if isinstance(rule, ObjectRule | LoopRule):
            yield from _with_paths(rule.rules, f"{path}.")


def paths_by_id(file: FunctionalFile) -> dict[str, str]:
    """Fully-qualified rule id -> rule path."""
    assign_ids(file)
    paths = dict(_with_paths(file.rules))
    ids = [fq for fq, _ in walk(file.rules)]
    return dict(zip(ids, paths, strict=True))


def proposals_by_path(file: FunctionalFile) -> tuple[dict[str, str], dict[str, str]]:
    """`auto_proposals`, keyed by rule path."""
    by_id = paths_by_id(file)
    proposals, errors = auto_proposals(file)
    return (
        {by_id[fq]: text for fq, text in proposals.items()},
        {by_id[fq]: text for fq, text in errors.items()},
    )


def review(file: FunctionalFile, functions: Mapping[str, FunctionInfo]) -> list[RuleReview]:
    """The rules that need a look: only those with something to report are returned."""
    proposals, errors = proposals_by_path(file)
    found: list[RuleReview] = []
    for path, rule in _with_paths(file.rules):
        if not isinstance(rule, FieldRule):
            continue
        item = RuleReview(path)
        t = rule.transform
        if t.status == "manual":
            item.proposal_error = errors.get(path)
            item.stale_override = (
                t.last_auto_version is not None
                and path in proposals
                and proposals[path] != t.last_auto_version
            )
        if rule.validation.validated and rule.validation.functions:
            now = {n: f.fingerprint for n, f in functions.items()}
            item.changed_functions = sorted(
                n for n, h in rule.validation.functions.items() if now.get(n) != h
            )
        if item.stale_override or item.changed_functions:
            found.append(item)
    return found


# -- resolving a manual override (docs/ARCHITECTURE.md, §Auto / Manual mode) ------------------


def _field_at(file: FunctionalFile, path: str) -> FieldRule:
    rule = dict(_with_paths(file.rules)).get(path)
    if not isinstance(rule, FieldRule):
        raise FnYamlError(f"no field rule at {path!r}")
    return rule


def _proposal(file: FunctionalFile, path: str) -> str:
    proposals, errors = proposals_by_path(file)
    if path in proposals:
        return proposals[path]
    raise FnYamlError(errors.get(path, f"no auto code for {path!r}"))


def take_over(file: FunctionalFile, path: str) -> FunctionalFile:
    """auto -> manual: the override starts as the code the transpiler generates now, which is
    also remembered (`last_auto_version`) to tell later when it moved."""
    file = copy.deepcopy(file)
    rule = _field_at(file, path)
    if rule.transform.status == "manual":
        return file
    # the proposals are made for manual rules: look at this one as if it were already
    rule.transform.status, rule.transform.code_override = "manual", "0"
    code = _proposal(file, path)
    rule.transform.code_override = rule.transform.last_auto_version = code
    return file


def set_override(file: FunctionalFile, path: str, code: str) -> FunctionalFile:
    file = copy.deepcopy(file)
    rule = _field_at(file, path)
    if rule.transform.status != "manual":
        raise FnYamlError(f"{path}: the rule is not manual")
    if not code.strip():
        raise FnYamlError(f"{path}: the override cannot be empty (accept the auto code instead)")
    rule.transform.code_override = code
    return file


def accept_proposal(file: FunctionalFile, path: str) -> FunctionalFile:
    """manual -> auto: the override is dropped. The generated code is not the one that was
    validated, so the rule is flagged for review."""
    file = copy.deepcopy(file)
    rule = _field_at(file, path)
    if rule.transform.status != "manual":
        return file
    rule.transform.status = "auto"
    rule.validation.validated = False
    rule.validation.needs_review = True
    rule.transform.code_override = rule.transform.last_auto_version = None
    return file


def keep_override(file: FunctionalFile, path: str) -> FunctionalFile:
    """The override stays; what the transpiler generates now is the new baseline."""
    file = copy.deepcopy(file)
    rule = _field_at(file, path)
    if rule.transform.status != "manual":
        raise FnYamlError(f"{path}: the rule is not manual")
    rule.transform.last_auto_version = _proposal(file, path)
    return file


def proposal_view(file: FunctionalFile, path: str) -> dict[str, object]:
    """What the split pane shows for a manual rule."""
    rule = _field_at(file, path)
    proposals, errors = proposals_by_path(file)
    t = rule.transform
    return {
        "auto": proposals.get(path),
        "error": errors.get(path),
        "override": t.code_override,
        "last_auto_version": t.last_auto_version,
    }


def validate(
    file: FunctionalFile, path: str, validated: bool, functions: Mapping[str, FunctionInfo]
) -> FunctionalFile:
    """Set `validated` on the rule at `path` (see `set_validated`)."""
    file = copy.deepcopy(file)
    rule = _field_at(file, path)
    rule.validation = set_validated(rule, validated, functions).validation
    return file
