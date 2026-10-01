"""Review state of the rules of a file, beyond `validated` / `needs_review` (docs/ARCHITECTURE.md,
§Auto / Manual mode and §Rule validation):

- a *manual* rule keeps `transform.last_auto_version`, the code the transpiler generated when the
  developer took over; when what it generates now differs, the rule's functional side moved
  under the override (`stale_override`), and the developer decides between the new proposal and
  the override (a *manual* rule is the developer's business, so this is a developer-mode signal only).
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from dataclasses import dataclass

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


@dataclass
class RuleReview:
    path: str  # `rules[0].rules[1]`, as the check's diagnostics name a rule
    stale_override: bool = False
    proposal_error: str | None = None  # a manual rule whose auto code cannot be generated

    def to_json(self) -> dict[str, object]:
        return {
            "rule": self.path,
            "stale_override": self.stale_override,
            "proposal_error": self.proposal_error,
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


def review(file: FunctionalFile) -> list[RuleReview]:
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
        if item.stale_override:
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


def demote_invalid(file: FunctionalFile, error_paths: set[str]) -> tuple[FunctionalFile, list[str]]:
    """On save: a validated rule the check finds errors in goes back to review. Returns the file
    and the ids (or paths) of the rules demoted."""
    file = copy.deepcopy(file)
    demoted: list[str] = []
    for path, rule in _with_paths(file.rules):
        if isinstance(rule, FieldRule) and rule.validation.validated and path in error_paths:
            rule.validation.validated, rule.validation.needs_review = False, True
            demoted.append(rule.id or path)
    return file, demoted
