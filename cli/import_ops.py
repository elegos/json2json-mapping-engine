"""What the desktop tool's import screens ask of `mapper serve`: the imports of a project, a plan
with what the screens need next to it, the answers and the review marks written back, and the
three plan commands (`assemble`, `test`, `apply`). A run of the assistant is not here: it is long
and has its own process (`cli/import_run.py`)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from cli import import_plan
from cli.import_plan import PlanError, load_plan, plan_file, save_plan
from cli.import_run import DOCUMENTS, plan_errors, profile_file, sha256_of

NOT_A_MAPPING = {"profiles", DOCUMENTS}
MAPPING_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")
STATES = ("pending", "accepted", "rejected")


def _check_id(mapping: str) -> str:
    if not MAPPING_ID.match(mapping) or mapping in NOT_A_MAPPING:
        raise PlanError(f"'{mapping}' is not a mapping id")
    return mapping


def stale(project: Path, plan: dict[str, Any]) -> list[str]:
    """Why the plan may no longer match its inputs: the document or the profile changed."""
    reasons: list[str] = []
    document = plan.get("document") or {}
    path = project / str(document.get("file", ""))
    if path.is_file() and document.get("sha256") and sha256_of(path) != document["sha256"]:
        reasons.append("document")
    name = (plan.get("profile") or {}).get("name")
    recorded = (plan.get("profile") or {}).get("sha256")
    changed = bool(name and recorded and profile_file(project, name).is_file())
    if changed and sha256_of(profile_file(project, str(name))) != recorded:
        reasons.append("profile")
    return reasons


def _at(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def unread_answers(plan: dict[str, Any]) -> bool:
    """Answers (or notes) given after the last run: the next run (`resume`) has not read them."""
    history = plan.get("history") or []
    last = _at(history[-1]["at"]) if history else None
    if last is None:
        return False
    for q in plan.get("questions") or []:
        given = _at(q["answered_at"]) if q.get("answered_at") else None
        if given and (given.tzinfo is None) == (last.tzinfo is None) and given > last:
            return True
    return False


def state_of(plan: dict[str, Any]) -> str:
    if any(q.get("status", "open") == "open" for q in plan.get("questions") or []):
        return "needs_answers"
    if unread_answers(plan):
        return "answered"
    included = [
        r
        for r in plan.get("rules") or []
        if (r.get("review") or {}).get("state") != "rejected"
        and (r.get("proposal") or {}).get("fn_rule")
    ]
    if included and all((r.get("review") or {}).get("state") == "applied" for r in included):
        return "applied"
    return "ready_for_review"


def list_imports(project: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for path in sorted((project / "import").glob("*/ir.json")):
        mapping = path.parent.name
        if mapping in NOT_A_MAPPING:
            continue
        try:
            plan = load_plan(project, mapping)
        except PlanError as exc:
            found.append({"mapping": mapping, "state": "broken", "error": str(exc)})
            continue
        rules = plan.get("rules") or []
        found.append(
            {
                "mapping": mapping,
                "state": state_of(plan),
                "document": (plan.get("document") or {}).get("file"),
                "version": ((plan.get("document") or {}).get("version") or {}).get("resolved"),
                "profile": (plan.get("profile") or {}).get("name"),
                "rules": len(rules),
                "guesses": sum(1 for r in rules if r["confidence"]["level"] in ("low", "guess")),
                "open_questions": sum(
                    1 for q in plan.get("questions") or [] if q.get("status", "open") == "open"
                ),
                "stale": stale(project, plan),
                "modified": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
            }
        )
    return found


def profiles(project: Path) -> list[dict[str, Any]]:
    """The project's profiles, to offer one when a document is imported."""
    found: list[dict[str, Any]] = []
    for path in sorted((project / "import" / "profiles").glob("*.profile.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError, yaml.YAMLError:
            data = {}
        found.append(
            {
                "name": path.name.removesuffix(".profile.yaml"),
                "description": data.get("description") if isinstance(data, dict) else None,
                "applies_to": data.get("applies_to", []) if isinstance(data, dict) else [],
            }
        )
    return found


def read_plan(project: Path, mapping: str) -> dict[str, Any]:
    plan = load_plan(project, _check_id(mapping))
    name = (plan.get("profile") or {}).get("name")
    profile = None
    if name and profile_file(project, name).is_file():
        profile = {"name": name, "text": profile_file(project, name).read_text(encoding="utf-8")}
    return {
        "plan": plan,
        "state": state_of(plan),
        "problems": plan_errors(plan),
        "stale": stale(project, plan),
        "profile": profile,
        "exists": (project / "mappings" / "functional" / f"{mapping}.fn.yaml").is_file(),
    }


def answer(project: Path, mapping: str, answers: list[dict[str, Any]]) -> dict[str, Any]:
    """`answers`: `{id, answer}` or `{id, skip: true}` (the proposal is taken, marked as such)."""
    plan = load_plan(project, _check_id(mapping))
    questions = {q["id"]: q for q in plan.get("questions") or []}
    now = datetime.now(UTC).isoformat(timespec="milliseconds")
    for given in answers:
        question = questions.get(given["id"])
        if question is None:
            raise PlanError(f"no question '{given['id']}'")
        if given.get("skip"):
            question.pop("answer", None)
            question["status"] = "skipped_assumed_proposal"
        else:
            text = str(given.get("answer", "")).strip()
            if not text:
                raise PlanError(f"question '{given['id']}': the answer is empty")
            question["answer"] = text
            question["status"] = "answered"
        question["answered_at"] = now
    save_plan(project, mapping, plan)
    return {
        "open_questions": sum(1 for q in questions.values() if q.get("status", "open") == "open")
    }


def _item(plan: dict[str, Any], kind: str, item_id: str) -> dict[str, Any]:
    key = "validations" if kind == "validation" else "rules"
    for item in plan.get(key) or []:
        if item["id"] == item_id:
            return item
    raise PlanError(f"no {kind} '{item_id}'")


def review(project: Path, mapping: str, kind: str, item_id: str, state: str) -> None:
    if state not in STATES:
        raise PlanError(f"unknown state '{state}'")
    plan = load_plan(project, _check_id(mapping))
    item = _item(plan, kind, item_id)
    if (item.get("review") or {}).get("state") == "applied":
        raise PlanError(f"'{item_id}' is applied already: change it in the mapping")
    item.setdefault("review", {})["state"] = state
    save_plan(project, mapping, plan)


def note(project: Path, mapping: str, rule_id: str, text: str) -> str:
    """The user's remark on a rule, as a question of scope `rule` that is already answered: the
    next run (`rerun_partial`, `rule_ids`) reads it like any answer."""
    text = text.strip()
    if not text:
        raise PlanError("the note is empty")
    plan = load_plan(project, _check_id(mapping))
    rule = _item(plan, "rule", rule_id)
    questions = plan.setdefault("questions", [])
    taken = {q["id"] for q in questions}
    number = 1
    while f"note_{number}" in taken:
        number += 1
    question_id = f"note_{number}"
    questions.append(
        {
            "id": question_id,
            "topic": "user_note",
            "text": f"Note on {rule_id}",
            "scope": "rule",
            "rule_ids": [rule_id],
            "answer": text,
            "answered_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "status": "answered",
        }
    )
    rule.setdefault("review", {"state": "pending"})["note"] = text
    save_plan(project, mapping, plan)
    return question_id


def command(project: Path, mapping: str, action: str, **kwargs: Any) -> dict[str, Any]:
    """`assemble`, `run_cases` or `apply` of `cli/import_plan.py`."""
    _check_id(mapping)
    if action not in ("assemble", "run_cases", "apply"):
        raise PlanError(f"unknown action '{action}'")
    plan_file(project, mapping)
    return getattr(import_plan, action)(project, mapping, **kwargs)
