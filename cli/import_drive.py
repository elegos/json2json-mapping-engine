"""`mapper import run` for a document too long for one run: survey it, cut it into batches, have
several assistant runs translate them at once, read again what a late answer changed
(docs/import/BATCHES.md). A short document, or any mode but `import` / `resume`, is the single run
of `cli/import_run.py`."""

from __future__ import annotations

import json
import shutil
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from cli import import_batch
from cli.import_plan import PlanError, load_plan, locked, plan_file
from cli.import_run import (
    PROVIDERS,
    RunError,
    bring_document,
    bring_schema,
    build_prompt,
    command_for,
    denied_of,
    execute,
    find_plan,
    run,
    skill_dir,
    stamp_hashes,
    summarize,
)

# a document with more units than this is imported in batches
LONG_OVER = 80
# what a worker may not write: the plan is changed by `mapper import add`, which checks it
WORKER_DENY = ["Write(import/*/ir.json)", "Edit(import/*/ir.json)"]
ROUNDS = 3  # settling passes: answers that came while the batches ran


def count_units(document: Path) -> int:
    """About how many rules a document holds: table rows and paragraphs, not titles or noise."""
    from cli.docread import ExtractError, extract

    try:
        doc = extract(document)
    except ExtractError:
        return 0  # the run reports it
    rows = sum(max(len(t["rows"]) - 1, 0) for t in doc.get("tables") or [])
    text = sum(
        1
        for b in doc["blocks"]
        if b["kind"] in ("paragraph", "list_item", "code") and not b.get("noise")
    )
    return rows + text


def _existing(project: Path, mapping: str | None) -> bool:
    """Whether an import of this mapping already works in batches."""
    return bool(mapping) and (project / "import" / str(mapping) / "units.json").is_file()


def write_covered(project: Path, mapping: str) -> None:
    """The units a plan already has rules for, for a survey that goes on from them (an import
    begun by the single-run method)."""
    if not plan_file(project, mapping).is_file():
        return
    covered = sorted(import_batch.covered(load_plan(project, mapping)))
    path = project / "import" / mapping / "covered.json"
    path.write_text(json.dumps({"covered": covered}, indent=2) + "\n", encoding="utf-8")


def _worker(
    project: Path,
    mapping: str,
    entry: dict[str, Any],
    *,
    provider: str,
    executable: str,
    document: str,
    profile: str | None,
    schemas: dict[str, str],
    allow: list[str] | None,
    override: str | None,
    emit: Callable[[dict[str, Any]], None],
    cancelled: threading.Event,
) -> dict[str, Any]:
    skill = skill_dir()
    prompt = build_prompt(
        document,
        mapping,
        profile,
        "translate",
        entry.get("rework") or [],
        skill,
        schemas.get("input"),
        schemas.get("output"),
        batch=entry["id"],
    )
    command = (
        [executable, prompt]
        if override
        else command_for(provider, executable, prompt, skill, allow, WORKER_DENY)
    )
    emit({"event": "batch_started", "batch": entry["id"], "units": len(entry["units"])})
    lines, code = execute(project, provider, command, emit, cancelled, {"batch": entry["id"]})
    if cancelled.is_set():
        return {"batch": entry["id"], "status": "cancelled"}
    # a worker that tries to write the plan is refused on purpose: that is not for the user to allow
    denied = [
        d
        for d in denied_of(provider, lines)
        if not d["what"].replace("\\", "/").endswith("/ir.json")
    ]
    tail = " ".join(lines[-2:])[:300]
    error = f"exited with {code}: {tail}" if code != 0 else "the run ended with units untranslated"
    status = import_batch.settle_batch(project, mapping, entry["id"], error)
    out: dict[str, Any] = {"batch": entry["id"], "status": status}
    if denied:
        out["denied"] = denied
    if status != "done":
        out["error"] = error
    return out


def drive(
    project: Path,
    document: Path,
    *,
    provider: str,
    mode: str = "import",
    mapping: str | None = None,
    profile: str | None = None,
    rule_ids: list[str] | None = None,
    input_schema: Path | None = None,
    output_schema: Path | None = None,
    emit: Callable[[dict[str, Any]], None],
    cancelled: threading.Event | None = None,
    override: str | None = None,
    allow: list[str] | None = None,
    concurrency: int = 2,
    size: int = import_batch.DEFAULT_SIZE,
    long_over: int = LONG_OVER,
) -> dict[str, Any]:
    """The run the desktop tool starts. Events: `started`, `progress`, then for a long document
    `surveyed`, `queue`, `batch_started`, `batch` and `settling`; the result is the final status."""
    cancel = cancelled or threading.Event()
    single = {
        "provider": provider,
        "mapping": mapping,
        "profile": profile,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "emit": emit,
        "cancelled": cancel,
        "override": override,
        "allow": allow,
    }
    batched = mode in ("import", "resume") and (
        _existing(project, mapping) or count_units(document) > long_over
    )
    if not batched:
        return run(project, document, mode=mode, rule_ids=rule_ids, **single)

    executable = override or shutil.which(provider)
    if executable is None:
        raise RunError(f"{PROVIDERS.get(provider, provider)} is not installed")
    relative = bring_document(project, document)
    if not _existing(project, mapping):
        if mapping:
            write_covered(project, mapping)
        surveyed = run(project, document, mode="survey", **{**single, "rule_ids": None})
        if surveyed["status"] != "surveyed":
            return surveyed
        mapping = surveyed["mapping"]
        emit({"event": "surveyed", "mapping": mapping})
    assert mapping is not None
    schemas = {
        kind: bring_schema(project, path, kind, mapping)
        for kind, path in (("input", input_schema), ("output", output_schema))
        if path is not None
    }
    made = import_batch.queue(project, mapping, size)
    emit({"event": "queue", "mapping": mapping, **made})
    gap = import_batch.gaps(project, mapping)
    if gap["expected"]:
        emit({"event": "gaps", **gap})

    stop = threading.Event()  # set by a refusal: more runs would only be refused too
    results: list[dict[str, Any]] = []
    guard = threading.Lock()
    denied: dict[str, dict[str, str]] = {}

    def emit_safe(event: dict[str, Any]) -> None:
        with guard:
            emit(event)

    def loop() -> None:
        while not cancel.is_set() and not stop.is_set():
            entry = import_batch.next_batch(project, mapping)
            if entry is None:
                return
            result = _worker(
                project,
                mapping,
                entry,
                provider=provider,
                executable=executable,
                document=relative,
                profile=profile,
                schemas=schemas,
                allow=allow,
                override=override,
                emit=emit_safe,
                cancelled=cancel,
            )
            if result["status"] == "cancelled":
                import_batch.release_batch(project, mapping, entry["id"])
                return
            for item in result.get("denied") or []:
                denied[item["rule"]] = item
            if result.get("denied") and result["status"] != "done":
                stop.set()
            results.append(result)
            plan = load_plan(project, mapping)
            emit_safe(
                {
                    "event": "batch",
                    "batch": entry["id"],
                    "status": result["status"],
                    "error": result.get("error"),
                    **summarize(plan),
                }
            )

    for settling in range(ROUNDS):
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            for future in [pool.submit(loop) for _ in range(max(1, concurrency))]:
                future.result()
        if cancel.is_set() or stop.is_set():
            break
        late = import_batch.rework(project, mapping)
        if not late or settling == ROUNDS - 1:
            break
        import_batch.queue_rework(project, mapping, late)
        emit({"event": "settling", "rules": len(late)})

    return _finish(project, mapping, provider, cancel, denied)


def _finish(
    project: Path,
    mapping: str,
    provider: str,
    cancel: threading.Event,
    denied: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """The status of the whole import, from what is in the plan and the queue."""
    if cancel.is_set():
        for entry in json.loads(import_batch.queue_file(project, mapping).read_text("utf-8"))[
            "batches"
        ]:
            if entry["status"] == "running":
                import_batch.release_batch(project, mapping, entry["id"])
        return {"status": "cancelled"}
    queue = json.loads(import_batch.queue_file(project, mapping).read_text("utf-8"))
    left = [b for b in queue["batches"] if b["status"] != "done"]
    with locked(project, mapping):
        path = plan_file(project, mapping)
        plan = stamp_hashes(project, path, "translate", provider, [])
    out: dict[str, Any] = {
        "ir": path.relative_to(project).as_posix(),
        "mapping": mapping,
        "batches": {"total": len(queue["batches"]), "left": len(left)},
        **summarize(plan),
    }
    if left:
        errors = {b.get("error") for b in left if b.get("error")}
        out["status"] = "failed"
        out["error"] = (
            f"{len(left)} batch(es) did not finish"
            + (f": {sorted(errors)[0]}" if errors else "")
            + "; run again to continue from them"
        )
    else:
        out["status"] = "needs_answers" if out["open_questions"] else "ready_for_review"
    if denied:
        out["denied"] = list(denied.values())
    return out


__all__ = ["PlanError", "RunError", "count_units", "drive", "find_plan"]
