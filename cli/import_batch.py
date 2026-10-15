"""Importing a long document in batches (docs/import/BATCHES.md): what the assistant hands to the
code instead of rewriting the plan.

`queue` turns the survey's `units.json` into mechanical rules and batches, `add` checks a batch of
rules and merges it into `ir.json`, `ask` and `answers` are the live questions, `gaps` counts what
the engine is expected to lack. All of it works under the plan's lock (`import_plan.locked`), so
parallel runs and the desktop tool do not overwrite each other, and none of it knows a mapping: the
assistant classifies, this code does the bookkeeping."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

from cli import import_plan
from cli.import_plan import PlanError, import_dir, load_plan, locked, plan_file, save_plan
from cli.import_run import plan_errors, skill_dir

CLASSES = ("skip", "structure", "constant", "copy", "translate", "ask")
FIELD_TYPES = ("str", "int", "number", "bool", "date", "datetime")
# reasons that name something that is not a unit of the document (the same ones `SKILL.md` lists)
NOT_UNITS = ("header_or_title", "not_a_rule", "footnote_or_definition_used_by_a_rule")
BATCH_KEYS = ("rules", "validations", "lookups", "discrepancies", "tests")
DEFAULT_SIZE = 30
ZEROS = "0" * 64


def units_file(project: Path, mapping: str) -> Path:
    return import_dir(project, mapping) / "units.json"


def queue_file(project: Path, mapping: str) -> Path:
    return import_dir(project, mapping) / "queue.json"


def document_file(project: Path, mapping: str) -> Path:
    return import_dir(project, mapping) / "document.json"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _read(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlanError(f"no {what} ({path.name})") from exc
    except ValueError as exc:
        raise PlanError(f"{path.name}: not valid JSON ({exc})") from exc


def _write(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _schema() -> dict[str, Any]:
    return json.loads((skill_dir() / "references" / "ir.schema.json").read_text("utf-8"))


def _validator(definition: str) -> jsonschema.Draft202012Validator:
    schema = _schema()
    return jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]}
    )


# ---- evidence from the document ------------------------------------------------------------


def _row_of(cells: str | None) -> int | None:
    found = re.match(r"[A-Z]+(\d+)", cells or "")
    return int(found[1]) if found else None


def _rows_of(location: dict[str, Any]) -> range | None:
    cells = str(location.get("cells") or "")
    ends = [int(n) for n in re.findall(r"[A-Z]+(\d+)", cells)]
    if not ends:
        return None
    return range(min(ends), min(max(ends), min(ends) + 40) + 1)


def row_index(document: dict[str, Any]) -> dict[tuple[str, int], str]:
    """The text of each spreadsheet row, cells joined as `evidence.text` is written (empty cells
    and the copies a merged cell leaves left out), by (sheet, row number)."""
    index: dict[tuple[str, int], str] = {}
    for table in document.get("tables") or []:
        sheet = str((table.get("location") or {}).get("sheet") or "")
        for row in table["rows"]:
            cells = [c for c in row["cells"] if not c.get("continuation")]
            number = _row_of(((cells[0].get("location") or {}) if cells else {}).get("cells"))
            if number is not None:
                index[(sheet, number)] = " | ".join(c["text"] for c in cells if c["text"].strip())
    return index


def evidence_text(index: dict[tuple[str, int], str], locations: list[dict[str, Any]]) -> str | None:
    parts = []
    for location in locations:
        rows = _rows_of(location)
        if rows is None:
            return None
        parts += [t for n in rows if (t := index.get((str(location.get("sheet") or ""), n)))]
    return "\n".join(parts) if parts else None


def evidence_hash(evidence: dict[str, Any]) -> str:
    text = evidence["text"] + "".join(
        "\n" + c["text"] for c in evidence.get("inherited_context") or []
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _location_of_id(rule_id: str) -> dict[str, Any] | None:
    found = re.search(r"@(.+)!([A-Z]+\d+)$", rule_id)
    return {"sheet": found[1], "cells": found[2]} if found else None


def fill_rule(
    rule: dict[str, Any],
    index: dict[tuple[str, int], str],
    context: list[dict[str, Any]],
) -> None:
    """What the code knows better than the assistant: the evidence text and its hash (from the
    document, by location), the context every rule inherits, and the review state."""
    rule.setdefault("review", {"state": "pending"})
    evidence = rule.setdefault("evidence", {})
    if not evidence.get("locations"):
        derived = _location_of_id(str(rule.get("id", "")))
        if derived is None:
            raise PlanError(f"rule '{rule.get('id')}': no evidence location")
        evidence["locations"] = [derived]
    if not evidence.get("text"):
        found = evidence_text(index, evidence["locations"])
        if found is None:
            raise PlanError(
                f"rule '{rule.get('id')}': no evidence text, and the document has none at "
                f"{evidence['locations'][0]}"
            )
        evidence["text"] = found
    if context and "inherited_context" not in evidence:
        evidence["inherited_context"] = copy.deepcopy(context)
    if not evidence.get("sha256") or evidence["sha256"] == ZEROS:
        evidence["sha256"] = evidence_hash(evidence)


# ---- units ---------------------------------------------------------------------------------


def _reasons() -> list[str]:
    coverage = _schema()["properties"]["coverage"]["properties"]["not_imported"]["items"]
    return list(coverage["properties"]["reason"]["enum"])


def load_units(project: Path, mapping: str) -> dict[str, Any]:
    data = _read(units_file(project, mapping), "units.json (the survey writes it)")
    problems: list[str] = []
    if not isinstance(data, dict) or not isinstance(data.get("units"), list):
        raise PlanError("units.json: expected an object with a `units` list")
    reasons = _reasons()
    seen: set[str] = set()
    for n, unit in enumerate(data["units"]):
        label = f"unit {n} ({unit.get('id') if isinstance(unit, dict) else '?'})"
        if not isinstance(unit, dict) or not isinstance(unit.get("id"), str) or not unit["id"]:
            problems.append(f"{label}: no id")
            continue
        if unit["id"] in seen:
            problems.append(f"{label}: duplicate id")
        seen.add(unit["id"])
        kind = unit.get("class")
        if kind not in CLASSES:
            problems.append(f"{label}: class must be one of {', '.join(CLASSES)}")
        if not isinstance(unit.get("location"), dict):
            problems.append(f"{label}: no location")
        if kind in ("structure", "constant", "copy") and not unit.get("target"):
            problems.append(f"{label}: a {kind} unit needs a target")
        if kind == "constant" and "value" not in unit:
            problems.append(f"{label}: a constant needs a value")
        if kind == "copy" and not (unit.get("source") and unit.get("type") in FIELD_TYPES):
            problems.append(f"{label}: a copy needs a source and a type ({', '.join(FIELD_TYPES)})")
        if kind == "skip" and unit.get("reason") not in reasons:
            problems.append(f"{label}: reason must be one of {', '.join(reasons)}")
    if problems:
        raise PlanError("units.json: " + "; ".join(problems[:15]))
    return data


def _location_key(rule: dict[str, Any]) -> str | None:
    rule_id = str(rule.get("id", ""))
    return rule_id.split("@", 1)[1] if "@" in rule_id else None


def covered(plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The plan's rules by the unit they were written for (the location in their id)."""
    found: dict[str, list[dict[str, Any]]] = {}
    for rule in plan.get("rules") or []:
        key = _location_key(rule)
        if key:
            found.setdefault(key, []).append(rule)
    return found


def _doubtful(rule: dict[str, Any]) -> bool:
    confidence = rule.get("confidence") or {}
    return confidence.get("level") != "high" or bool(confidence.get("flags"))


def refresh_coverage(plan: dict[str, Any], units: dict[str, Any]) -> None:
    """`coverage` from the rules and the survey: a unit is imported (or with doubt) when a rule was
    written for it, not imported (with its reason) when the survey skipped it, and waiting when
    neither. Entries the plan had for what is not a unit of the survey stay; so do the rules of
    units it does not list (an import begun without a survey), counted as one unit each."""
    by_unit = covered(plan)
    imported = doubt = total = 0
    out: list[dict[str, Any]] = []
    for unit in units["units"]:
        rules = by_unit.get(unit["id"])
        if rules:
            total += 1
            bad = any(_doubtful(r) for r in rules)
            doubt += bad
            imported += not bad
        elif unit["class"] == "skip":
            entry = {"location": unit["location"], "reason": unit["reason"]}
            if unit.get("detail"):
                entry["detail"] = unit["detail"]
            out.append(entry)
            total += unit["reason"] not in NOT_UNITS
        else:
            total += 1
            out.append(
                {
                    "location": unit["location"],
                    "reason": "needs_user_input",
                    "detail": "not translated yet",
                }
            )
    listed = {u["id"] for u in units["units"]}
    for key, rules in by_unit.items():
        if key not in listed:
            total += 1
            bad = any(_doubtful(r) for r in rules)
            doubt += bad
            imported += not bad
    here = [u["location"] for u in units["units"]]
    for entry in (plan.get("coverage") or {}).get("not_imported") or []:
        waiting = entry.get("reason") == "needs_user_input" and "not translated" in entry.get(
            "detail", ""
        )
        if not waiting and entry.get("location") not in here:
            out.append(entry)
            total += entry.get("reason") not in NOT_UNITS
    plan["coverage"] = {
        "units_total": total,
        "imported": imported,
        "imported_with_doubt": doubt,
        "not_imported": out,
    }


# ---- merging a batch ------------------------------------------------------------------------


def _merge_rules(plan: dict[str, Any], rules: list[dict[str, Any]]) -> tuple[int, int]:
    existing = {r["id"]: i for i, r in enumerate(plan["rules"])}
    added = replaced = 0
    for rule in rules:
        if rule["id"] in existing:
            old = plan["rules"][existing[rule["id"]]]
            if (old.get("review") or {}).get("state") == "applied":
                raise PlanError(f"rule '{rule['id']}' is applied already")
            kept = old.get("review") or {}
            if kept.get("state") not in (None, "pending"):  # the user's decision stays
                rule["review"] = kept
            plan["rules"][existing[rule["id"]]] = rule
            replaced += 1
        else:
            plan["rules"].append(rule)
            added += 1
    return added, replaced


def _merge_others(plan: dict[str, Any], batch: dict[str, Any]) -> None:
    for key, ident in (("validations", "id"), ("tests", "id")):
        have = {x[ident]: i for i, x in enumerate(plan.setdefault(key, []))}
        for item in batch.get(key) or []:
            if item[ident] in have:
                plan[key][have[item[ident]]] = item
            else:
                plan[key].append(item)
    tables = {t["name"]: t for t in plan.setdefault("lookups", [])}
    for table in batch.get("lookups") or []:
        if table["name"] in tables:
            tables[table["name"]]["entries"] = {
                **(tables[table["name"]].get("entries") or {}),
                **(table.get("entries") or {}),
            }
            tables[table["name"]]["status"] = table.get("status", tables[table["name"]]["status"])
        else:
            plan["lookups"].append(table)
    known = {(d.get("kind"), d.get("detail")) for d in plan.get("discrepancies") or []}
    for found in batch.get("discrepancies") or []:
        if (found.get("kind"), found.get("detail")) not in known:
            plan.setdefault("discrepancies", []).append(found)


def _problems(batch: Any) -> list[str]:
    out: list[str] = []
    for key, definition in (
        ("rules", "rule"),
        ("validations", "validation"),
        ("discrepancies", "discrepancy"),
    ):
        validator = _validator(definition)
        for n, item in enumerate(batch.get(key) or []):
            label = item.get("id", n) if isinstance(item, dict) else n
            out += [
                f"{key} '{label}': {'/'.join(str(p) for p in e.absolute_path) or '(item)'}: {e.message[:160]}"
                for e in sorted(validator.iter_errors(item), key=lambda e: list(e.absolute_path))[
                    :5
                ]
            ]
    return out


def add(
    project: Path, mapping: str, batch_path: Path, batch_id: str | None = None
) -> dict[str, Any]:
    """Merge a batch of rules (and validations, lookups, discrepancies, tests) into the plan, fill
    what the code knows (evidence, hashes), and check the result with `assemble`. A batch that does
    not validate, or whose rules do not fit together, changes nothing."""
    batch = _read(batch_path, "batch file")
    if not isinstance(batch, dict) or not batch or not set(batch) <= set(BATCH_KEYS):
        raise PlanError(f"a batch is an object with some of: {', '.join(BATCH_KEYS)}")
    with locked(project, mapping):
        path = plan_file(project, mapping)
        before = path.read_bytes() if path.exists() else None
        plan = load_plan(project, mapping)
        document = document_file(project, mapping)
        index = row_index(_read(document, "document.json")) if document.exists() else {}
        units = load_units(project, mapping) if units_file(project, mapping).exists() else None
        context = (units or {}).get("context") or []
        rules = copy.deepcopy(batch.get("rules") or [])
        for rule in rules:
            fill_rule(rule, index, context)
        batch = {**batch, "rules": rules}
        problems = _problems(batch)
        if problems:
            raise PlanError("the batch does not validate: " + "; ".join(problems[:12]))
        added, replaced = _merge_rules(plan, rules)
        _merge_others(plan, batch)
        found = plan_errors(plan)
        if found:
            raise PlanError("the plan would not validate: " + "; ".join(found[:8]))
        save_plan(project, mapping, plan)
        try:
            built = import_plan.assemble(project, mapping)
        except PlanError as exc:
            if before is not None:
                path.write_bytes(before)
            raise PlanError(f"the batch does not fit the plan: {exc}") from exc
        plan = load_plan(project, mapping)
        if units is not None:
            refresh_coverage(plan, units)
            save_plan(project, mapping, plan)
        ids = {r["id"] for r in rules}
        errors = {
            r["id"]: r["proposal"]["check"]["errors"][:3]
            for r in plan["rules"]
            if r["id"] in ids and not ((r.get("proposal") or {}).get("check") or {"ok": True})["ok"]
        }
        missing = _finish_batch(project, mapping, batch_id, plan)
    return {
        "ok": True,
        "batch": batch_id,
        "added": added,
        "replaced": replaced,
        "rules": len(plan["rules"]),
        "errors": errors,
        "gaps": built["gaps"][:5],
        "skipped": [s for s in built["skipped"] if s["rule"] in ids],
        "missing_units": missing,
    }


def _finish_batch(
    project: Path, mapping: str, batch_id: str | None, plan: dict[str, Any]
) -> list[str]:
    """Mark the batch done when every unit of it has a rule; else say which have none."""
    file = queue_file(project, mapping)
    if batch_id is None or not file.exists():
        return []
    queue = _read(file, "queue.json")
    by_unit = covered(plan)
    for entry in queue["batches"]:
        if entry["id"] == batch_id:
            missing = [u for u in entry["units"] if u not in by_unit]
            if not missing:  # else it stays with the worker, who adds the rest
                entry["status"] = "done"
                entry["finished_at"] = _now()
                _write(file, queue)
            return missing
    raise PlanError(f"no batch '{batch_id}' in queue.json")


# ---- mechanical units and the queue -----------------------------------------------------------


def _norm_target(target: str) -> str:
    target = target.strip()
    return target[2:] if target.startswith("$.") else target.lstrip("$")


def _fn_id(target: str, taken: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", target.replace("[*]", "")).strip("_") or "rule"
    if base[0].isdigit():
        base = f"r_{base}"
    name, n = base, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    return name


def _containers(plan: dict[str, Any]) -> dict[str, str]:
    """The `object` / `loop` rules of the plan by the path they write, for a field to nest in."""
    found: dict[str, str] = {}
    for rule in plan["rules"]:
        fn = (rule.get("proposal") or {}).get("fn_rule") or {}
        if fn.get("kind") in ("object", "loop"):
            found[_norm_target((rule.get("target") or {}).get("path", ""))] = fn["id"]
    return found


def _taken_ids(plan: dict[str, Any]) -> set[str]:
    return {
        fn["id"]
        for r in plan["rules"]
        if (fn := (r.get("proposal") or {}).get("fn_rule")) and "id" in fn
    }


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int | float):
        return json.dumps(value)
    return json.dumps(str(value), ensure_ascii=False)


def _type_of(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    return "number" if isinstance(value, float) else "str"


def mechanical_rule(
    unit: dict[str, Any], plan: dict[str, Any], containers: dict[str, str], taken: set[str]
) -> dict[str, Any] | None:
    """The rule for a unit the survey classified as `structure`, `constant` or `copy`; `None` when
    the container it belongs in does not exist yet (the assistant gets the unit instead)."""
    target = _norm_target(unit["target"])
    head, _, last = target.rpartition(".")
    parent = containers.get(head) if head else None
    if head and parent is None:
        return None
    name = last.replace("[*]", "")
    fn_id = _fn_id(target, taken)
    kind = unit["class"]
    if kind == "structure":
        if last.endswith("[*]"):  # a loop needs a source: the assistant writes it
            return None
        fn: dict[str, Any] = {"id": fn_id, "kind": "object", "output": name}
        what, intent = f"The object {target}, which the document only implies.", "structure"
    elif kind == "constant":
        value = unit["value"]
        fn = {
            "id": fn_id,
            "kind": "field",
            "field": name,
            "type": unit.get("type") if unit.get("type") in FIELD_TYPES else _type_of(value),
            "transform": {"expression": _literal(value)},
        }
        what, intent = (
            f"Always writes the constant {json.dumps(value, ensure_ascii=False)}.",
            "constant",
        )
    else:
        fn = {
            "id": fn_id,
            "kind": "field",
            "field": name,
            "type": unit["type"],
            "source": {"path": unit["source"]},
        }
        what, intent = f"Copies {unit['source']}.", "copy"
    if unit.get("required") is False and kind != "structure":
        fn["required"] = False
    fn["description"] = unit.get("detail") or what
    proposal: dict[str, Any] = {"fn_rule": fn, "functions_used": []}
    if parent:
        proposal["parent_rule"] = parent
    rule = {
        "id": f"{target}@{unit['id']}",
        "evidence": {"locations": [unit["location"]]},
        "target": {"path": f"$.{target}"},
        "intent": intent,
        "interpretation": what,
        "assumptions": [
            {
                "topic": "classified",
                "assumed": f"read as a plain {kind}",
                "basis": "document_evidence",
            }
        ],
        "proposal": proposal,
        "confidence": {"level": "high"},
        "review": {"state": "pending"},
    }
    taken.add(fn_id)
    if fn["kind"] == "object":
        containers[target] = fn_id
    return rule


def _batches(units: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    """Units that belong together (a `group`, else neighbours) cut into batches of about `size`."""
    buckets: list[list[dict[str, Any]]] = []
    by_group: dict[str, list[dict[str, Any]]] = {}
    run: list[dict[str, Any]] | None = None
    for unit in units:
        group = unit.get("group")
        if group:
            if group not in by_group:
                by_group[group] = []
                buckets.append(by_group[group])
            by_group[group].append(unit)
            run = None
        else:
            if run is None:
                run = []
                buckets.append(run)
            run.append(unit)
    order = {u["id"]: n for n, u in enumerate(units)}
    out: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for bucket in buckets:
        for start in range(0, len(bucket), size):
            piece = bucket[start : start + size]
            if current and len(current) + len(piece) > size:
                out.append(current)
                current = []
            current += piece
    if current:
        out.append(current)
    return [sorted(b, key=lambda u: order[u["id"]]) for b in out]


def queue(project: Path, mapping: str, size: int = DEFAULT_SIZE) -> dict[str, Any]:
    """Take the survey's units: write the rules of the mechanical ones, and cut the others the plan
    does not cover yet into batches (`queue.json`). Run again after more units or answers: batches
    done or running stay, the waiting ones are cut again."""
    if size < 1:
        raise PlanError("the batch size must be at least 1")
    with locked(project, mapping):
        units = load_units(project, mapping)
        plan = load_plan(project, mapping)
        document = document_file(project, mapping)
        index = row_index(_read(document, "document.json")) if document.exists() else {}
        context = units.get("context") or []
        have = covered(plan)
        containers, taken = _containers(plan), _taken_ids(plan)
        pending = [u for u in units["units"] if u["id"] not in have and u["class"] != "skip"]
        made: list[dict[str, Any]] = []
        for _ in range(8):  # a container made in one pass is the parent of the next
            this_pass = []
            for unit in list(pending):
                if unit["class"] in ("structure", "constant", "copy"):
                    rule = mechanical_rule(unit, plan, containers, taken)
                    if rule is not None:
                        fill_rule(rule, index, context)
                        this_pass.append(rule)
                        pending.remove(unit)
            if not this_pass:
                break
            _merge_rules(plan, this_pass)
            made += this_pass
        waiting = pending
        if made:
            found = plan_errors(plan)
            if found:
                raise PlanError("the mechanical rules would not validate: " + "; ".join(found[:8]))
            save_plan(project, mapping, plan)
            import_plan.assemble(project, mapping)
            plan = load_plan(project, mapping)
        refresh_coverage(plan, units)
        save_plan(project, mapping, plan)
        old = (
            _read(queue_file(project, mapping), "queue.json")
            if queue_file(project, mapping).exists()
            else {"batches": []}
        )
        kept = [b for b in old["batches"] if b["status"] in ("done", "running")]
        busy = {u for b in kept for u in b["units"]}
        numbered = max(
            [int(b["id"][1:]) for b in kept if b["id"][1:].isdigit() and b["id"][0] == "b"] or [0]
        )
        fresh = []
        for chunk in _batches(
            [u for u in waiting if u["id"] not in busy and u["class"] != "ask"], size
        ):
            numbered += 1
            fresh.append(
                {
                    "id": f"b{numbered:03d}",
                    "units": [u["id"] for u in chunk],
                    "groups": sorted({u["group"] for u in chunk if u.get("group")}),
                    "status": "pending",
                }
            )
        data = {"size": size, "batches": kept + fresh, "updated": _now()}
        _write(queue_file(project, mapping), data)
    return {
        "units": len(units["units"]),
        "mechanical": len(made),
        "waiting_for_answers": [u["id"] for u in waiting if u["class"] == "ask"],
        "batches": [
            {"id": b["id"], "units": len(b["units"]), "status": b["status"]}
            for b in data["batches"]
        ],
        "pending_units": sum(len(b["units"]) for b in fresh),
    }


def next_batch(project: Path, mapping: str, claim: bool = True) -> dict[str, Any] | None:
    """The first waiting batch, marked running (what a worker takes), or `None` when none waits."""
    with locked(project, mapping):
        file = queue_file(project, mapping)
        if not file.exists():
            return None
        data = _read(file, "queue.json")
        for entry in data["batches"]:
            if entry["status"] == "pending":
                if claim:
                    entry["status"] = "running"
                    entry["started_at"] = _now()
                    _write(file, data)
                return entry
    return None


def release_batch(project: Path, mapping: str, batch_id: str, status: str = "pending") -> None:
    """Give a batch back (a run that died or was cancelled)."""
    with locked(project, mapping):
        file = queue_file(project, mapping)
        data = _read(file, "queue.json")
        for entry in data["batches"]:
            if entry["id"] == batch_id and entry["status"] == "running":
                entry["status"] = status
        _write(file, data)


def batch_units(project: Path, mapping: str, batch_id: str) -> list[dict[str, Any]]:
    """The survey's description of the units of a batch (what the worker translates)."""
    queue_data = _read(queue_file(project, mapping), "queue.json")
    wanted = next((b["units"] for b in queue_data["batches"] if b["id"] == batch_id), None)
    if wanted is None:
        raise PlanError(f"no batch '{batch_id}' in queue.json")
    by_id = {u["id"]: u for u in load_units(project, mapping)["units"]}
    return [by_id[u] for u in wanted if u in by_id]


def batch_info(project: Path, mapping: str, batch_id: str) -> dict[str, Any]:
    """What a worker needs for its batch: the units with the text of their rows, the rules it is to
    read again (a `rework` batch), and the context every rule inherits."""
    queue_data = _read(queue_file(project, mapping), "queue.json")
    entry = next((b for b in queue_data["batches"] if b["id"] == batch_id), None)
    if entry is None:
        raise PlanError(f"no batch '{batch_id}' in queue.json")
    document = document_file(project, mapping)
    index = row_index(_read(document, "document.json")) if document.exists() else {}
    units = []
    for item in batch_units(project, mapping, batch_id):
        text = evidence_text(index, [item["location"]])
        units.append({**item, **({"text": text} if text else {})})
    plan = load_plan(project, mapping)
    out: dict[str, Any] = {
        "id": batch_id,
        "units": units,
        "context": load_units(project, mapping).get("context") or [],
        # the `object` / `loop` rules there are, by target path: the `parent_rule` of a rule in one
        "containers": _containers(plan),
    }
    if entry.get("rework"):
        out["rework"] = [r for r in plan["rules"] if r["id"] in entry["rework"]]
    return out


# ---- live questions --------------------------------------------------------------------------


def _words(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


def _similar(a: str, b: str) -> bool:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return a.strip().lower() == b.strip().lower()
    return len(wa & wb) / len(wa | wb) >= 0.8


def ask(
    project: Path,
    mapping: str,
    text: str,
    *,
    topic: str = "other",
    scope: str = "mapping",
    options: list[str] | None = None,
    proposal: str | None = None,
    rule_ids: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Add a question to the plan now (the desktop tool shows it while the run goes on). One
    already asked about the same thing (same topic, nearly the same words) is returned instead, and
    gets the new rules: `existing` is true, with its answer if it has one."""
    if scope not in ("profile", "mapping", "rule"):
        raise PlanError("scope is one of profile, mapping, rule")
    if not text.strip():
        raise PlanError("the question is empty")
    with locked(project, mapping):
        plan = load_plan(project, mapping)
        questions = plan.setdefault("questions", [])
        for q in questions:
            if q.get("topic") == topic and _similar(q["text"], text):
                merged = sorted({*(q.get("rule_ids") or []), *(rule_ids or [])})
                if merged:
                    q["rule_ids"] = merged
                save_plan(project, mapping, plan)
                return {
                    "id": q["id"],
                    "existing": True,
                    "status": q.get("status", "open"),
                    "answer": q.get("answer"),
                }
        taken = {q["id"] for q in questions}
        slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_") or "q"
        number = 1
        while f"q_{slug}_{number}" in taken:
            number += 1
        question: dict[str, Any] = {
            "id": f"q_{slug}_{number}",
            "topic": topic,
            "text": text.strip(),
            "scope": scope,
            "status": "open",
        }
        for key, value in (
            ("options", options),
            ("proposal", proposal),
            ("rule_ids", rule_ids),
            ("evidence", evidence),
        ):
            if value:
                question[key] = value
        questions.append(question)
        save_plan(project, mapping, plan)
    return {"id": question["id"], "existing": False, "status": "open", "answer": None}


def answers(project: Path, mapping: str, rule_id: str | None = None) -> dict[str, Any]:
    """The questions answered so far (and skipped ones, which are read as their proposal), with
    the rules each one touches; with a rule, only the ones that touch it."""
    plan = load_plan(project, mapping)
    given = []
    for q in plan.get("questions") or []:
        status = q.get("status", "open")
        if status == "open" or (q.get("topic") == "user_note" and rule_id is None):
            continue
        if rule_id and rule_id not in (q.get("rule_ids") or []):
            continue
        given.append(
            {
                "id": q["id"],
                "topic": q["topic"],
                "scope": q["scope"],
                "question": q["text"],
                "answer": q.get("answer") if status == "answered" else q.get("proposal"),
                "skipped": status != "answered",
                "rule_ids": q.get("rule_ids") or [],
            }
        )
    open_ = [q["id"] for q in plan.get("questions") or [] if q.get("status", "open") == "open"]
    return {"answers": given, "open": open_}


def _when(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def rework(project: Path, mapping: str) -> list[str]:
    """Rules to read again: the ones a question lists as depending on it, written (their batch
    finished) before the answer came. A rule written after the answer has read it."""
    file = queue_file(project, mapping)
    if not file.exists():
        return []
    finished: dict[str, datetime] = {}
    for entry in _read(file, "queue.json")["batches"]:
        when = _when(entry.get("finished_at", "")) if entry["status"] == "done" else None
        if when is None:
            continue
        for unit in entry["units"]:
            finished[unit] = max(when, finished.get(unit, when))
    plan = load_plan(project, mapping)
    by_id = {r["id"]: r for r in plan["rules"]}
    stale: set[str] = set()
    for q in plan.get("questions") or []:
        given = _when(q.get("answered_at", ""))
        if given is None or q.get("topic") == "user_note":
            continue
        for rule_id in q.get("rule_ids") or []:
            unit = _location_key(by_id[rule_id]) if rule_id in by_id else None
            if unit in finished and finished[unit] < given:
                stale.add(rule_id)
    return sorted(stale)


def queue_rework(project: Path, mapping: str, rule_ids: list[str]) -> dict[str, Any] | None:
    """Put the rules to read again into a batch of their own (`rework` names them); `None` when
    there are none."""
    if not rule_ids:
        return None
    with locked(project, mapping):
        file = queue_file(project, mapping)
        data = _read(file, "queue.json")
        by_id = {r["id"]: r for r in load_plan(project, mapping)["rules"]}
        units = sorted({u for r in rule_ids if (u := _location_key(by_id.get(r, {})))})
        number = 1 + sum(1 for b in data["batches"] if b["id"].startswith("r"))
        entry = {
            "id": f"r{number:03d}",
            "units": units,
            "rework": rule_ids,
            "groups": [],
            "status": "pending",
        }
        data["batches"].append(entry)
        _write(file, data)
    return entry


def settle_batch(project: Path, mapping: str, batch_id: str, error: str, attempts: int = 2) -> str:
    """A run ended without finishing its batch: back to waiting, until it has been tried
    `attempts` times, then failed with the reason. Returns the new status."""
    with locked(project, mapping):
        file = queue_file(project, mapping)
        data = _read(file, "queue.json")
        for entry in data["batches"]:
            if entry["id"] == batch_id and entry["status"] != "done":
                entry["attempts"] = entry.get("attempts", 0) + 1
                entry["status"] = "pending" if entry["attempts"] < attempts else "failed"
                entry["error"] = error
                _write(file, data)
                return str(entry["status"])
    return "done"


# ---- the engine's gaps, known early ------------------------------------------------------------


def gaps(project: Path, mapping: str) -> dict[str, Any]:
    """What the survey expects the engine to lack (`needs` of the units), counted with the rows
    that wait for each, and the function gaps the plan already has."""
    needs: dict[str, list[str]] = {}
    if units_file(project, mapping).exists():
        for unit in load_units(project, mapping)["units"]:
            for need in unit.get("needs") or []:
                needs.setdefault(need.strip().lower(), []).append(unit["id"])
    plan = load_plan(project, mapping)
    missing: Counter[str] = Counter()
    where: dict[str, list[str]] = {}
    for rule in plan["rules"]:
        proposal = rule.get("proposal") or {}
        for item in proposal.get("functions_missing") or []:
            name = (
                str(item.get("needed") or item.get("name")) if isinstance(item, dict) else str(item)
            )
            missing[name] += 1
            where.setdefault(name, []).append(rule["id"])
    return {
        "expected": [
            {"need": k, "units": len(v), "examples": v[:5]}
            for k, v in sorted(needs.items(), key=lambda kv: -len(kv[1]))
        ],
        "function_gaps": [
            {"needed": k, "rules": n, "examples": where[k][:5]} for k, n in missing.most_common()
        ],
    }
