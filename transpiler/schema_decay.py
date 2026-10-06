"""Validation after a schema change: a validated rule the new schema invalidates goes back to review.

Loading an input or an output schema can make a rule wrong (its Source path is gone or has
another type, its Target field is gone or has another type). The check already says so, rule by
rule, against the schemas; a rule that has an error with the new schemas it did not have with the
old ones was invalidated by the change. If it was validated it becomes `validated: false,
needs_review: true`, with a note saying what the schema did, like the decay on a changed Source
or Expression. A rule already in review or never validated, and a rule the schema does not touch,
is left as it is."""

from __future__ import annotations

import datetime
import re
from typing import Any

from transpiler.check import Issue, check_functional
from transpiler.model import FieldRule, FunctionalFile, LoopRule, ObjectRule, Rule

Schema = dict[str, Any]

_STEP = re.compile(r"rules\[(\d+)\]")


def rule_at(file: FunctionalFile, path: str) -> Rule | None:
    """The rule an issue path (`rules[0].rules[1]`) names."""
    rules: list[Rule] = file.rules
    found: Rule | None = None
    for step in _STEP.findall(path):
        index = int(step)
        if index >= len(rules):
            return None
        found = rules[index]
        rules = found.rules if isinstance(found, ObjectRule | LoopRule) else []
    return found


def _errors(file: FunctionalFile, inp: Schema | None, out: Schema | None) -> list[Issue]:
    return [i for i in check_functional(file, inp, out) if i.severity == "error" and i.rule]


def review_after_schema_change(
    file: FunctionalFile,
    kind: str,
    old: tuple[Schema | None, Schema | None],
    new: tuple[Schema | None, Schema | None],
) -> list[dict[str, str]]:
    """Sends the validated rules of `file` that `new` invalidates (and `old` did not) to review,
    in place. `old` and `new` are the (input, output) schemas before and after loading `kind`.
    Gives what moved: `{"path", "message"}` per rule, the path as in the check's diagnostics."""
    before = {(i.rule, i.message) for i in _errors(file, *old)}
    caused: dict[str, list[str]] = {}
    for issue in _errors(file, *new):
        if (issue.rule, issue.message) not in before:
            caused.setdefault(issue.rule, []).append(issue.message)
    day = datetime.date.today().isoformat()
    moved: list[dict[str, str]] = []
    for path, messages in caused.items():
        rule = rule_at(file, path)
        if not isinstance(rule, FieldRule) or not rule.validation.validated:
            continue
        reason = "; ".join(dict.fromkeys(messages))
        note = f"the {kind} schema was loaded ({day}): {reason}"
        v = rule.validation
        v.validated, v.needs_review = False, True
        v.notes = f"{v.notes}\n{note}" if v.notes else note
        moved.append({"path": path, "message": reason})
    return moved
