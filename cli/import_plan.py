"""The commands that go from an import plan (`import/<mapping>/ir.json`) to rules in the project:
`assemble` builds the working `.fn.yaml` from the plan and checks it, `test` runs the plan's cases
against it, `apply` writes it into `mappings/functional/` (docs/import/IR.md).

The plan is the source of truth and these commands write only inside `import/<mapping>/` (and,
for `apply`, the one `.fn.yaml`): the skill proposes rules, this code puts them together, so that
nothing about the nesting or the file layout is left to the model."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import json
import os
import re
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cli import shared
from cli.build import FUNCTIONAL_DIR, resolve_schema_for, schema_file
from compiler.backends.python.backend import PythonBackend
from compiler.function_registry import all_functions
from compiler.pipeline import compile_unit
from transpiler.check import check_functional, schemas_for
from transpiler.model import FnYamlError, load_functional_file, parse_functional
from transpiler.serialize import write_functional
from transpiler.transpile import transpile_file_model

# rule states that go into the working copy: everything the user did not reject
EXCLUDED_STATES = {"rejected"}
# a check message that only says "the output schema needs a rule that the plan does not have yet"
# (a function gap, a missing lookup, a rule not proposed): a gap of the plan, not a defect of it
_GAP = re.compile(
    r"the output schema requires|required by the output schema|so the output schema must allow null"
)


class PlanError(Exception):
    """The plan cannot be used (missing, malformed, or its rules do not fit together)."""


def import_dir(project: Path, mapping: str) -> Path:
    return project / "import" / mapping


def plan_file(project: Path, mapping: str) -> Path:
    return import_dir(project, mapping) / "ir.json"


def work_file(project: Path, mapping: str) -> Path:
    return import_dir(project, mapping) / "work" / f"{mapping}.fn.yaml"


_HELD: dict[Path, list[int]] = {}  # lock file -> [owning thread, depth]
_GUARD = threading.RLock()


@contextlib.contextmanager
def locked(project: Path, mapping: str, wait: float = 60.0) -> Iterator[None]:
    """Exclusive use of a plan for a read-modify-write: several assistant runs and the desktop tool
    write the same `ir.json`. A lock file next to it (taken by creating it), re-entrant in the
    process; one older than `wait` seconds is taken to be left by a process that died."""
    lock = import_dir(project, mapping) / "ir.json.lock"
    me = threading.get_ident()
    with _GUARD:
        mine = _HELD.get(lock)
        if mine and mine[0] == me:
            mine[1] += 1
            try:
                yield
            finally:
                mine[1] -= 1
            return
    if not lock.parent.is_dir():
        raise PlanError(f"no import '{mapping}'")
    started = time.monotonic()
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            with contextlib.suppress(OSError):
                if time.time() - lock.stat().st_mtime > wait:
                    lock.unlink()
                    continue
            if time.monotonic() - started > wait:
                raise PlanError(f"{lock.name}: the plan is in use by another run") from None
            time.sleep(0.05)
    with _GUARD:
        _HELD[lock] = [me, 1]
    try:
        yield
    finally:
        with _GUARD:
            _HELD.pop(lock, None)
        with contextlib.suppress(OSError):
            lock.unlink()


def load_plan(project: Path, mapping: str) -> dict[str, Any]:
    path = plan_file(project, mapping)
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlanError(f"no plan for '{mapping}' ({path})") from exc
    except ValueError as exc:
        raise PlanError(f"{path}: not valid JSON ({exc})") from exc
    if not isinstance(plan, dict) or not isinstance(plan.get("rules"), list):
        raise PlanError(f"{path}: not an import plan")
    return plan


def save_plan(project: Path, mapping: str, plan: dict[str, Any]) -> None:
    path = plan_file(project, mapping)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _lookup_rules(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for table in plan.get("lookups") or []:
        # a table the document does not give is still written, named, with the entries there are
        # (none: it finds nothing until it is filled in); entries are never invented
        entries = table.get("entries") or {}
        kinds = {type(v).__name__ for v in entries.values()}
        out.append(
            {
                "id": f"lut_{str(table['name']).lower()}",
                "kind": "lookup",
                "label": table["name"],
                "type": "number" if entries and kinds <= {"int", "float"} else "str",
                "description": f"Table {table['name']} from the document.",
                "entries": entries,
            }
        )
    return out


def _validations_raw(plan: dict[str, Any], skipped: list[dict[str, Any]]) -> dict[str, Any]:
    """The `validations:` section of the plan: the checks the user did not reject, by side, and
    whether each side is also validated against its JSON Schema."""
    raw: dict[str, Any] = {}
    flags = plan.get("schema_validation") or {}
    for side in ("input", "output"):
        body: dict[str, Any] = {}
        if flags.get(side):
            body["schema"] = True
        checks = []
        for check in plan.get("validations") or []:
            if check["side"] != side:
                continue
            if (check.get("review") or {}).get("state") in EXCLUDED_STATES:
                skipped.append({"rule": check["id"], "reason": "rejected"})
                continue
            item = {
                k: check[k] for k in ("id", "expect", "code", "message", "action") if k in check
            }
            if check.get("interpretation"):
                item["description"] = check["interpretation"]
            checks.append(item)
        if checks:
            body["checks"] = checks
        if body:
            raw[side] = body
    return raw


def _in_cycle(rule_id: str, parents: dict[str, str | None]) -> bool:
    """Whether following `parent_rule` from `rule_id` comes back to a rule already seen (a rule
    that is its own parent, or a ring of rules): none of them would ever reach the top."""
    seen: set[str] = set()
    current: str | None = rule_id
    while current is not None and current in parents:
        if current in seen:
            return True
        seen.add(current)
        current = parents[current]
    return False


def build_tree(plan: dict[str, Any], mapping: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The raw `.fn.yaml` (lookups, then the rules nested under their `parent_rule`) and the plan
    rules left out, each with the reason."""
    top: list[dict[str, Any]] = _lookup_rules(plan)
    by_id: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    pending: list[tuple[str | None, dict[str, Any], str]] = []
    for rule in plan["rules"]:
        proposal = rule.get("proposal") or {}
        fn_rule = proposal.get("fn_rule")
        state = (rule.get("review") or {}).get("state", "pending")
        if state in EXCLUDED_STATES:
            skipped.append({"rule": rule["id"], "reason": "rejected"})
        elif not fn_rule:
            reason = "function_gap" if proposal.get("functions_missing") else "no_proposal"
            skipped.append({"rule": rule["id"], "reason": reason})
        else:
            fn = copy.deepcopy(fn_rule)
            if fn.get("kind", "field") != "field":
                # review state and requiredness live in the plan; only a field rule has them
                for key in ("validation", "required"):
                    fn.pop(key, None)
            if "id" not in fn:
                raise PlanError(f"rule '{rule['id']}': its fn_rule has no `id`")
            if fn["id"] in by_id:
                raise PlanError(f"two rules write the fn rule id '{fn['id']}'")
            by_id[fn["id"]] = fn
            pending.append((proposal.get("parent_rule"), fn, rule["id"]))
    parents = {fn["id"]: parent for parent, fn, _ in pending}
    for parent, fn, plan_id in pending:
        if parent is None:
            top.append(fn)
        elif _in_cycle(fn["id"], parents):
            skipped.append({"rule": plan_id, "reason": f"parent_rule '{parent}' makes a cycle"})
        elif parent in by_id:
            by_id[parent].setdefault("rules", []).append(fn)
        else:
            skipped.append({"rule": plan_id, "reason": f"parent_rule '{parent}' is not included"})
    raw: dict[str, Any] = {
        "name": (plan.get("mapping") or {}).get("name") or mapping,
        "id": mapping,
        "rules": top,
    }
    refs = {
        kind: (plan.get("schemas") or {}).get(kind, {}).get("path") for kind in ("input", "output")
    }
    if refs["input"] or refs["output"]:
        raw["schemas"] = {k: v for k, v in refs.items() if v}
    validations = _validations_raw(plan, skipped)
    if validations:
        raw["validations"] = validations
    return raw, skipped


def _fn_id_at(rules: list[dict[str, Any]], position: str) -> str:
    """The `id` of the rule a check diagnostic names by position (`rules[1].rules[0]`)."""
    named = re.match(r"validations\.(input|output)\.checks\[(\d+)\]", position)
    if named:
        return f"{named[1]}:{named[2]}"  # resolved by `assemble`, which has the checks
    name = position
    level = rules
    for index in re.findall(r"rules\[(\d+)\]", position):
        if int(index) >= len(level):
            return position
        node = level[int(index)]
        name, level = node["id"], node.get("rules", [])
    return name


def _assemble(project: Path, mapping: str) -> dict[str, Any]:
    """Write `import/<mapping>/work/<mapping>.fn.yaml` from the plan, check it with the project's
    schemas and functions, and record the result in each rule's `proposal.check`."""
    plan = load_plan(project, mapping)
    raw, skipped = build_tree(plan, mapping)
    try:
        tree = parse_functional(raw, mapping)
    except FnYamlError as exc:
        raise PlanError(f"the plan's rules do not make a valid file: {exc}") from exc
    target = work_file(project, mapping)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_functional(target, tree)
    with contextlib.chdir(project):
        inp, out = schemas_for(project, mapping, tree.schemas)
        issues = check_functional(tree, inp, out, all_functions(project))
    errors: dict[str, list[str]] = {}
    gaps: list[str] = []
    for issue in issues:
        if issue.severity != "error":
            continue
        if _GAP.search(issue.message):
            gaps.append(issue.message)
        else:
            errors.setdefault(_fn_id_at(raw["rules"], issue.rule or ""), []).append(issue.message)
    for key in [k for k in errors if ":" in k]:
        side, index = key.split(":")
        checks = (raw.get("validations") or {}).get(side, {}).get("checks", [])
        found = errors.pop(key)
        if int(index) < len(checks):
            errors.setdefault(checks[int(index)]["id"], []).extend(found)
    for check in plan.get("validations") or []:
        if not any(s["rule"] == check["id"] for s in skipped):
            found = errors.get(check["id"], [])
            check["check"] = {"ran": True, "ok": not found, "errors": found}
    included = 0
    for rule in plan["rules"]:
        proposal = rule.get("proposal") or {}
        fn_id = (proposal.get("fn_rule") or {}).get("id")
        if fn_id and not any(s["rule"] == rule["id"] for s in skipped):
            included += 1
            found = errors.get(fn_id, [])
            proposal["check"] = {"ran": True, "ok": not found, "errors": found}
    save_plan(project, mapping, plan)
    return {
        "ok": not errors,
        # required output fields no rule writes yet (their rules are skipped: see `skipped`); the
        # cases still run, without the output schema's checks
        "gaps": gaps,
        # the check can only vouch for paths and types against the schemas it found
        "schemas_found": {"input": inp is not None, "output": out is not None},
        "file": target.relative_to(project).as_posix(),
        "rules_included": included,
        "skipped": skipped,
        "diagnostics": [i.to_json() for i in issues],
    }


def assemble(project: Path, mapping: str) -> dict[str, Any]:
    with locked(project, mapping):
        return _assemble(project, mapping)


def _load_module(files: dict[str, str], module_name: str, folder: Path) -> Any:
    for name, text in files.items():
        (folder / name).write_text(text)
    for stale in [m for m in sys.modules if m == "j2jme_runtime" or m.startswith("map_")]:
        del sys.modules[stale]
    sys.path.insert(0, str(folder))
    try:
        spec = importlib.util.spec_from_file_location(module_name, folder / f"{module_name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(folder))


def _compile_runner(project: Path, mapping: str, folder: Path, output_checked: bool = True) -> Any:
    """The compiled `map_<mapping>_safe` of the working copy (Python backend). Without
    `output_checked` the compiler does not hold the rules to the output schema (required fields
    that no rule writes yet)."""
    tree = load_functional_file(work_file(project, mapping))
    refs = tree.schemas
    source = transpile_file_model(
        tree, None, resolve_schema_for(mapping, "input", refs), f"{mapping}.fn.yaml"
    )
    backend = PythonBackend({})
    texts = {
        kind: schema_file(mapping, kind, refs).read_text()
        for kind in ("input", "output")
        if schema_file(mapping, kind, refs).is_file()
    }
    unit = compile_unit(
        source, mapping, backend, resolve_schema_for(mapping, "input", refs),
        resolve_schema_for(mapping, "output", refs) if output_checked else None,
        schema_texts=texts,
    )  # fmt: skip
    module = _load_module(backend.assemble([unit]), f"map_{mapping}", folder)
    return getattr(module, f"map_{mapping}_safe")


def _contains(actual: Any, expected: Any) -> bool:
    """Whether `actual` holds everything `expected` says (a partial expected output): the objects'
    keys given must match, a list has the same length and each element holds the one given."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and _contains(actual[k], v) for k, v in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_contains(a, e) for a, e in zip(actual, expected, strict=True))
        )
    return bool(actual == expected)


def _verdict(case: dict[str, Any], result: tuple[Any, ...]) -> tuple[str, str]:
    """`pass` / `fail` / `error` and why, for one run of a case. A case expects an output, or (for
    a mapping that validates) the codes of the checks that reject the message."""
    actual, errors, *rest = result
    report = rest[0] if rest else []
    rejected = sorted(i["code"] for i in report if i["action"] == "reject")
    warned = sorted(i["code"] for i in report if i["action"] == "warn")
    if "expected_rejected" in case:
        want = sorted(case["expected_rejected"])
        if rejected != want:
            return "fail", f"rejected by {rejected}, expected {want}"
    elif rejected:
        return "fail", f"rejected by {rejected}"
    if "expected_warnings" in case and warned != sorted(case["expected_warnings"]):
        return "fail", f"warnings {warned}, expected {sorted(case['expected_warnings'])}"
    if "expected_rejected" in case:
        return "pass", ""
    if errors:
        return "error", "; ".join(f"{e['rule']}: {e['cause']}" for e in errors)
    if "expected" not in case:
        return "pass", ""
    same = (
        _contains(actual, case["expected"]) if case.get("partial") else actual == case["expected"]
    )
    if same:
        return "pass", ""
    return "fail", f"expected {json.dumps(case['expected'])}, got {json.dumps(actual)}"


def _run_each(
    runner: Any, cases: list[dict[str, Any]], plan: dict[str, Any], summary: dict[str, int]
) -> None:
    for case in cases:
        try:
            case["result"], case["detail"] = _verdict(
                case, runner(json.loads(json.dumps(case["input"])))
            )
        except Exception as exc:  # the mapping itself failed to run
            case["result"], case["detail"] = "error", f"{type(exc).__name__}: {exc}"
        summary[case["result"]] += 1
        if case["result"] != "pass":
            plan.setdefault("discrepancies", []).append(
                {
                    "kind": "sample_contradicts_rule",
                    "severity": "warning",
                    "detail": f"case '{case['id']}' ({case['trust']}): {case['detail']}",
                    "rule_ids": case.get("rule_ids", []),
                }
            )


def _run_cases(project: Path, mapping: str) -> dict[str, Any]:
    """Run the plan's cases (those with an `input` and an `expected`) on the Python backend against
    the working copy, and record `result` / `detail` on each; a failing case also becomes a
    `sample_contradicts_rule` discrepancy. The working copy is rebuilt first."""
    built = _assemble(project, mapping)
    plan = load_plan(project, mapping)
    cases = [
        t
        for t in plan.get("tests") or []
        if "input" in t and ("expected" in t or "expected_rejected" in t)
    ]
    summary = {"pass": 0, "fail": 0, "error": 0, "not_run": 0}
    if not built["rules_included"] and not plan.get("validations"):
        for case in plan.get("tests") or []:
            case["result"], case["detail"] = "not_run", "the plan has no rule yet"
        save_plan(project, mapping, plan)
        return {**built, "cases": len(cases), **summary, "not_run": len(plan.get("tests") or [])}
    if not built["ok"]:
        for case in plan.get("tests") or []:
            case["result"], case["detail"] = "not_run", "the working copy does not check"
        save_plan(project, mapping, plan)
        return {**built, "cases": len(cases), **summary, "not_run": len(plan.get("tests") or [])}
    try:
        with contextlib.chdir(project), tempfile.TemporaryDirectory() as tmp:
            runner = _compile_runner(project, mapping, Path(tmp), output_checked=not built["gaps"])
            _run_each(runner, cases, plan, summary)
    except Exception as exc:  # the working copy checks but does not compile (or is empty)
        why = f"it does not compile: {type(exc).__name__}: {exc}"
        for case in plan.get("tests") or []:
            case["result"], case["detail"] = "not_run", why
        plan.setdefault("discrepancies", []).append(
            {
                "kind": "other",
                "severity": "warning",
                "detail": f"the cases could not run, {why}",
                "rule_ids": [],
            }
        )
        save_plan(project, mapping, plan)
        return {
            **built,
            "cases": len(cases),
            **summary,
            "not_run": len(plan.get("tests") or []),
            "compile_error": why,
        }
    summary["not_run"] = len(plan.get("tests") or []) - len(cases)
    save_plan(project, mapping, plan)
    return {**built, "cases": len(cases), **summary}


def _apply(project: Path, mapping: str, force: bool = False) -> dict[str, Any]:
    """Write the working copy to `mappings/functional/<mapping>.fn.yaml` and mark the included
    rules `applied`. Refuses when the file exists (unless `force`) or the working copy has errors."""
    built = _assemble(project, mapping)
    if not built["ok"]:
        raise PlanError(
            "the working copy does not check; fix the plan first (`mapper import assemble`)"
        )
    if built["gaps"] and not force:
        raise PlanError(
            f"{len(built['gaps'])} required output field(s) have no rule yet ({built['gaps'][0]}); "
            "the file would not check in the project. Pass --force to write it anyway"
        )
    destination = project / FUNCTIONAL_DIR / f"{mapping}.fn.yaml"
    if destination.exists() and not force:
        raise PlanError(f"{destination.relative_to(project)} exists; pass --force to replace it")
    plan = load_plan(project, mapping)
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = work_file(project, mapping).read_text(encoding="utf-8")
    fd, tmp_name = tempfile.mkstemp(dir=destination.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    Path(tmp_name).replace(destination)
    skipped = {s["rule"] for s in built["skipped"]}
    for rule in plan["rules"]:
        if rule["id"] not in skipped and (rule.get("proposal") or {}).get("fn_rule"):
            rule.setdefault("review", {})["state"] = "applied"
    save_plan(project, mapping, plan)
    shared.seen(project, destination.relative_to(project).as_posix())
    return {
        "ok": True,
        "file": destination.relative_to(project).as_posix(),
        "applied": built["rules_included"],
        "skipped": built["skipped"],
    }


def run_cases(project: Path, mapping: str) -> dict[str, Any]:
    with locked(project, mapping):
        return _run_cases(project, mapping)


def apply(project: Path, mapping: str, force: bool = False) -> dict[str, Any]:
    with locked(project, mapping):
        return _apply(project, mapping, force)


__all__ = ["PlanError", "apply", "assemble", "load_plan", "locked", "run_cases"]
