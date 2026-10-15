"""`mapper import run`: one run of the import skill by an installed assistant (Claude Code or
Codex), and `mapper import providers`, which says which ones are installed.

The skill is provider-neutral (`skills/import-functional-spec/references/protocol.md`); this module
builds the prompt, starts the assistant non-interactively inside the project, follows what it does
(one JSON line per event on stdout, for the desktop tool), and, when it ends, checks the plan it
left: the schema, the two hashes (the model does not compute them) and the final status."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from cli.import_plan import PlanError

PROVIDERS = {"claude": "Claude Code", "codex": "Codex"}
MODES = (
    "import",
    "resume",
    "rerun_all",
    "rerun_partial",
    "revalue_version",
    "survey",  # a long document: classify its units, translate nothing (docs/import/BATCHES.md)
    "translate",  # one batch of those units
)
DOCUMENTS = "documents"
SKILL = "skills/import-functional-spec"


class RunError(Exception):
    """The run cannot start (no assistant, unknown mode, unreadable document)."""


def engine_root() -> Path:
    return Path(__file__).resolve().parent.parent


def skill_dir() -> Path:
    path = engine_root() / SKILL
    if not (path / "SKILL.md").is_file():
        raise RunError(f"the import skill is not installed ({path})")
    return path


def providers() -> list[dict[str, Any]]:
    """The assistants found on the PATH, with their version."""
    found: list[dict[str, Any]] = []
    standin = os.environ.get("J2JME_IMPORT_PROVIDER")
    if standin:  # tests and the headless shots: a program that plays the assistant
        return [{"id": "claude", "title": "Stand-in assistant", "path": standin, "version": None}]
    for key, title in PROVIDERS.items():
        exe = shutil.which(key)
        if exe is None:
            continue
        version: str | None = None
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            done = subprocess.run(
                [exe, "--version"], capture_output=True, text=True, timeout=20, check=False
            )
            shown = (done.stdout or done.stderr).strip().splitlines()
            version = shown[0] if shown else None
        found.append({"id": key, "title": title, "path": exe, "version": version})
    return found


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bring_document(project: Path, document: Path) -> str:
    """The document as a path inside the project (`import/documents/` when it lives elsewhere),
    so that the assistant reads nothing outside the project and the plan can be re-run later."""
    document = document.resolve()
    if not document.is_file():
        raise RunError(f"{document}: not a file")
    with contextlib.suppress(ValueError):
        return document.relative_to(project.resolve()).as_posix()
    target = project / "import" / DOCUMENTS / document.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or sha256_of(target) != sha256_of(document):
        shutil.copyfile(document, target)
    return target.relative_to(project).as_posix()


def bring_schema(project: Path, schema: Path, kind: str, mapping: str | None) -> str:
    """A JSON Schema the user names, as a path inside the project, where the assistant may read it.
    With the mapping known it takes the name the project looks for (`schemas/<mapping>_<kind>.schema.json`),
    unless another file is there already; else it goes to `import/schemas/`."""
    schema = schema.resolve()
    if not schema.is_file():
        raise RunError(f"{schema}: not a file")
    try:
        json.loads(schema.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RunError(f"{schema.name}: not a JSON file ({exc})") from exc
    with contextlib.suppress(ValueError):
        return schema.relative_to(project.resolve()).as_posix()
    data = schema.read_bytes()
    canonical = project / "schemas" / f"{mapping}_{kind}.schema.json" if mapping else None
    if canonical is not None and (not canonical.exists() or canonical.read_bytes() == data):
        target = canonical
    else:
        target = project / "import" / "schemas" / schema.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_bytes() != data:
        target.write_bytes(data)
    return target.relative_to(project).as_posix()


def build_prompt(
    document: str,
    mapping: str | None,
    profile: str | None,
    mode: str,
    rule_ids: list[str],
    skill: Path,
    input_schema: str | None = None,
    output_schema: str | None = None,
    batch: str | None = None,
) -> str:
    lines = [
        f"Follow the skill in {skill.as_posix()}/SKILL.md (read it first, and the files in its "
        "references/ folder as it says), exactly, for this run.",
        "",
        f"- document: {document}",
        "- project: the current directory",
        f"- mapping: {mapping or 'ask'}",
        f"- profile: {profile or 'ask'}",
        f"- mode: {mode}",
    ]
    if input_schema:
        lines.append(f"- input_schema: {input_schema}")
    if output_schema:
        lines.append(f"- output_schema: {output_schema}")
    if rule_ids:
        lines.append(f"- rule_ids: {', '.join(rule_ids)}")
    if batch:
        lines.append(f"- batch: {batch}")
    lines += [
        "",
        "Write only inside import/. `mapper` is on the PATH; run it from this directory. You cannot "
        "ask anything during this run: whatever needs an answer goes into the plan's `questions`. "
        "The wizard computes `document.sha256` and `profile.sha256` itself (write any value). "
        "Your last line is the JSON status line of references/protocol.md.",
    ]
    return "\n".join(lines)


@contextlib.contextmanager
def mapper_on_path(env: dict[str, str]) -> Iterator[None]:
    """A `mapper` command for the assistant's shell, whatever way this engine was started."""
    root = engine_root()
    folder = Path(tempfile.mkdtemp(prefix="j2jme-run-"))
    try:
        if os.name == "nt":
            # cmd / PowerShell find `mapper.cmd`; the Bash of Git for Windows, which Claude Code
            # uses there, only runs a file with no extension
            (folder / "mapper.cmd").write_text(
                f'@echo off\r\nset "PYTHONPATH={root};%PYTHONPATH%"\r\n"{sys.executable}" -m cli.main %*\r\n',
                encoding="utf-8",
            )
            (folder / "mapper").write_text(
                f'#!/bin/sh\nPYTHONPATH="{root.as_posix()}" exec "{Path(sys.executable).as_posix()}" -m cli.main "$@"\n',
                encoding="utf-8",
                newline="\n",
            )
        else:
            shim = folder / "mapper"
            shim.write_text(
                f'#!/bin/sh\nPYTHONPATH="{root}${{PYTHONPATH:+:$PYTHONPATH}}" exec "{sys.executable}" -m cli.main "$@"\n',
                encoding="utf-8",
            )
            shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
        env["PATH"] = str(folder) + os.pathsep + env.get("PATH", "")
        yield
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def command_for(
    provider: str,
    executable: str,
    prompt: str,
    skill: Path,
    allow: list[str] | None = None,
    deny: list[str] | None = None,
) -> list[str]:
    """The non-interactive command line. Writes are limited to `import/`; the only program the
    assistant may run is `mapper`, plus what the user allowed after a refusal (`allow`: Claude Code
    permission rules, as `denied_of` builds them)."""
    if provider == "claude":
        return [
            executable,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
            "--add-dir",
            str(skill),
            "--allowedTools",
            "Read",
            "Glob",
            "Grep",
            "Write(import/**)",
            "Edit(import/**)",
            "Bash(mapper *)",
            *(allow or []),
            *(["--disallowedTools", *deny] if deny else []),
        ]
    if provider == "codex":
        return [
            executable,
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
            "--add-dir",
            str(skill),
            prompt,
        ]
    raise RunError(f"unknown assistant '{provider}'")


def _clip(text: str, size: int = 240) -> str:
    text = " ".join(text.split())
    return text if len(text) <= size else text[: size - 1] + "…"


def _text_blocks(content: Any) -> Iterator[str]:
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                yield str(block.get("text", ""))


def progress_of(provider: str, line: str) -> list[str]:
    """What a line of the assistant's own stream says, as short lines for the progress panel."""
    try:
        event = json.loads(line)
    except ValueError:
        return [_clip(line)] if line.strip() else []
    if not isinstance(event, dict):
        return []
    said: list[str] = []
    if provider == "claude":
        message = event.get("message")
        if event.get("type") == "assistant" and isinstance(message, dict):
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    said.append(_clip(str(block.get("text", ""))))
                elif block.get("type") == "tool_use":
                    arg = block.get("input") or {}
                    what = arg.get("file_path") or arg.get("command") or arg.get("pattern") or ""
                    said.append(_clip(f"{block.get('name')}: {what}"))
        return [s for s in said if s]
    item = event.get("item")
    if isinstance(item, dict) and event.get("type") == "item.completed":
        text = item.get("text") or item.get("command") or ""
        return [_clip(str(text))] if text else []
    return []


def final_text(provider: str, lines: list[str]) -> str:
    """The assistant's last words, where the status line is."""
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if provider == "claude" and event.get("type") == "result":
            return str(event.get("result") or "")
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            return str(item.get("text") or "")
    return ""


def _detail(arg: dict[str, Any]) -> str:
    return str(
        arg.get("command") or arg.get("file_path") or arg.get("pattern") or arg.get("path") or ""
    )


def denied_of(provider: str, lines: list[str]) -> list[dict[str, str]]:
    """The calls the assistant was refused (Claude Code lists them in its `result` event), each with
    the permission `rule` that allows it, so that the user can allow them and run again."""
    if provider != "claude":
        return []
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            found: dict[str, dict[str, str]] = {}
            for item in event.get("permission_denials") or []:
                if not isinstance(item, dict):
                    continue
                arg = item.get("tool_input")
                arg = arg if isinstance(arg, dict) else {}
                tool = str(item.get("tool_name") or "")
                detail = _detail(arg)
                rule = f"{tool}({detail})" if detail else tool
                found.setdefault(rule, {"tool": tool, "what": _clip(detail or tool), "rule": rule})
            return list(found.values())
    return []


def status_line(text: str) -> dict[str, Any] | None:
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict) and "status" in parsed:
                return parsed
    return None


def plan_errors(plan: Any) -> list[str]:
    """Why the plan does not conform to `ir.schema.json` (empty when it does)."""
    import jsonschema

    schema = json.loads((skill_dir() / "references" / "ir.schema.json").read_text("utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(plan), key=lambda e: list(e.absolute_path))
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {_clip(e.message, 200)}"
        for e in errors[:20]
    ]


def profile_file(project: Path, name: str) -> Path:
    return project / "import" / "profiles" / f"{name}.profile.yaml"


HISTORY_KIND = {
    "import": "import",
    "resume": "import",
    "rerun_all": "rerun_all",
    "rerun_partial": "rerun_partial",
    "revalue_version": "revalue_for_version",
    "survey": "import",
    "translate": "import",
}


def stamp_hashes(
    project: Path, plan_path: Path, mode: str, provider: str, rule_ids: list[str]
) -> dict[str, Any]:
    """Set `document.sha256` and `profile.sha256` from the files (the model does not hash) and
    record the run in `history` (the screens tell answers given after the last run by it)."""
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    document = project / str(plan.get("document", {}).get("file", ""))
    if document.is_file():
        plan["document"]["sha256"] = sha256_of(document)
    name = (plan.get("profile") or {}).get("name")
    if name and profile_file(project, name).is_file():
        plan["profile"]["sha256"] = sha256_of(profile_file(project, name))
    entry: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "kind": HISTORY_KIND[mode],
        "provider": provider,
        "summary": mode,
    }
    if rule_ids:
        entry["rule_ids"] = rule_ids
    version = ((plan.get("document") or {}).get("version") or {}).get("resolved")
    if version:
        entry["document_version"] = version
    plan.setdefault("history", []).append(entry)
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return plan


def summarize(plan: dict[str, Any]) -> dict[str, Any]:
    questions = plan.get("questions") or []
    rules = plan.get("rules") or []
    return {
        "open_questions": sum(1 for q in questions if q.get("status", "open") == "open"),
        "rules": len(rules),
        "guesses": sum(1 for r in rules if r["confidence"]["level"] in ("low", "guess")),
    }


def find_plan(project: Path, since: float, hint: str | None) -> Path | None:
    if hint and (project / hint).is_file():
        return project / hint
    newest: tuple[float, Path] | None = None
    for candidate in (project / "import").glob("*/ir.json"):
        stamp = candidate.stat().st_mtime
        if stamp >= since and (newest is None or stamp > newest[0]):
            newest = (stamp, candidate)
    return newest[1] if newest else None


def execute(
    project: Path,
    provider: str,
    command: list[str],
    emit: Callable[[dict[str, Any]], None],
    cancelled: threading.Event | None,
    tag: dict[str, Any] | None = None,
) -> tuple[list[str], int]:
    """Start the assistant in the project with `mapper` on its PATH and follow it: its lines, and
    its exit code. `tag` goes on every progress event (which worker said it)."""
    env = dict(os.environ)
    lines: list[str] = []
    with mapper_on_path(env):
        process = subprocess.Popen(
            command,
            cwd=project,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        def watch() -> None:
            while process.poll() is None:
                if cancelled is not None and cancelled.wait(0.3):
                    if process.poll() is None:
                        process.terminate()
                    return
                if cancelled is None:
                    return

        threading.Thread(target=watch, daemon=True).start()
        assert process.stdout is not None
        for raw in process.stdout:
            lines.append(raw.rstrip("\n"))
            for text in progress_of(provider, raw):
                emit({"event": "progress", "text": text, **(tag or {})})
        return lines, process.wait()


def run(
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
) -> dict[str, Any]:
    """One run. `override` (the `J2JME_IMPORT_PROVIDER` variable) is a program that stands in for the
    assistant: it gets the prompt as its only argument and prints lines like the assistant."""
    if mode not in MODES:
        raise RunError(f"unknown mode '{mode}'")
    skill = skill_dir()
    executable = override or shutil.which(provider)
    if executable is None:
        raise RunError(f"{PROVIDERS.get(provider, provider)} is not installed")
    relative = bring_document(project, document)
    schemas = {
        kind: bring_schema(project, path, kind, mapping)
        for kind, path in (("input", input_schema), ("output", output_schema))
        if path is not None
    }
    prompt = build_prompt(
        relative,
        mapping,
        profile,
        mode,
        rule_ids or [],
        skill,
        schemas.get("input"),
        schemas.get("output"),
    )
    command = (
        [executable, prompt]
        if override
        else command_for(provider, executable, prompt, skill, allow)
    )
    started = time.time() - 1
    backups: dict[Path, bytes] = {}
    for existing in (project / "import").glob("*/ir.json"):
        backups[existing] = existing.read_bytes()
    emit({"event": "started", "provider": provider, "document": relative})
    lines, code = execute(project, provider, command, emit, cancelled)

    def restore() -> None:
        for path, data in backups.items():
            path.write_bytes(data)

    if cancelled is not None and cancelled.is_set():
        restore()
        return {"status": "cancelled"}
    denied = denied_of(provider, lines)
    result = finish(project, provider, mode, rule_ids or [], lines, code, started, restore)
    if denied:
        result["denied"] = denied
    return result


def finish(
    project: Path,
    provider: str,
    mode: str,
    rule_ids: list[str],
    lines: list[str],
    code: int,
    started: float,
    restore: Callable[[], None],
) -> dict[str, Any]:
    """What the run left: the plan checked, or why it failed."""
    said = status_line(final_text(provider, lines)) or status_line("\n".join(lines))
    if code != 0 and not said:
        restore()
        tail = _clip(" ".join(lines[-3:]), 400)
        return {
            "status": "failed",
            "error": f"{PROVIDERS.get(provider, provider)} exited with {code}: {tail}",
        }
    if said and said.get("status") == "failed":
        restore()
        return {"status": "failed", "error": str(said.get("error") or "the run failed")}
    path = find_plan(project, started, said.get("ir") if said else None)
    if path is None:
        return {"status": "failed", "error": "the run left no plan (import/<mapping>/ir.json)"}
    try:
        plan = stamp_hashes(project, path, mode, provider, rule_ids or [])
    except (OSError, ValueError, KeyError) as exc:
        restore()
        return {"status": "failed", "error": f"{path.name}: {exc}"}
    errors = plan_errors(plan)
    if errors:
        # keep the invalid file next to the old plan for the user to see, and put the old one back
        rejected = path.with_name("ir.invalid.json")
        shutil.copyfile(path, rejected)
        restore()
        return {
            "status": "failed",
            "error": "the plan does not conform to ir.schema.json",
            "details": errors,
            "invalid": rejected.relative_to(project).as_posix(),
        }
    summary = summarize(plan)
    status = "needs_answers" if summary["open_questions"] else "ready_for_review"
    if mode == "survey":
        # a survey that classified the document goes on to the batches, with its questions open
        # in the backlog; one that could not, because it needs an answer first, stops
        surveyed = (path.parent / "units.json").is_file() and (said or {}).get(
            "status"
        ) != "needs_answers"
        status = "surveyed" if surveyed else "needs_answers"
    return {
        "status": status,
        "ir": path.relative_to(project).as_posix(),
        "mapping": plan["mapping"]["id"],
        **summary,
    }


def run_streaming(
    project: Path,
    document: Path,
    *,
    out: TextIO,
    watch_stdin: bool,
    **kwargs: Any,
) -> dict[str, Any]:
    """`run` writing its events as JSON lines on `out`; closing stdin (or a line `cancel`) cancels."""
    cancelled = threading.Event()
    if watch_stdin:

        def listen() -> None:
            for line in sys.stdin:
                if line.strip() == "cancel":
                    break
            cancelled.set()

        threading.Thread(target=listen, daemon=True).start()

    def emit(event: dict[str, Any]) -> None:
        out.write(json.dumps(event, ensure_ascii=False) + "\n")
        out.flush()

    from cli.import_drive import drive

    try:
        result = drive(
            project,
            document,
            emit=emit,
            cancelled=cancelled,
            override=os.environ.get("J2JME_IMPORT_PROVIDER") or None,
            **kwargs,
        )
    except (RunError, PlanError, OSError) as exc:
        result = {"status": "failed", "error": str(exc)}
    emit({"event": "done", **result})
    return result


__all__ = ["RunError", "providers", "run", "run_streaming"]
