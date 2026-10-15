"""A long document imported in batches by `drive`, with a program that stands in for the assistant:
the survey writes the units, the workers translate a batch each through the same commands the real
assistant calls."""

from __future__ import annotations

import json
import shutil
import stat
import sys
import threading
from pathlib import Path
from typing import Any

from cli import import_drive
from cli.import_plan import load_plan
from tests.track1.import_skill.test_import_batch import make

ROOT = Path(__file__).resolve().parents[3]

FAKE = """
import json, pathlib, shutil, sys
sys.path.insert(0, {root!r})
from cli import import_batch
prompt = sys.argv[1]
def line(key):
    return prompt.split("- " + key + ": ")[1].splitlines()[0]
mode = line("mode")
print(json.dumps({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": mode}}]}}}}), flush=True)
project = pathlib.Path.cwd()
if mode == "survey":
    shutil.copytree({source!r}, project / "import" / "demo")
    status = {{"status": "ready_for_review"}}
else:
    mapping, batch = line("mapping"), line("batch")
    info = import_batch.batch_info(project, mapping, batch)
    {worker}
    status = {{"status": "ready_for_review"}}
print(json.dumps({{"type": "result", "result": "done\\n" + json.dumps(status)}}), flush=True)
"""

TRANSLATE = """rules = []
    for unit in info["units"]:
        target = unit["target"]
        rules.append({
            "id": f"{target}@" + unit["id"],
            "evidence": {"locations": [unit["location"]]},
            "target": {"path": "$." + target},
            "intent": "copy",
            "interpretation": "Copies it.",
            "proposal": {"fn_rule": {"id": target, "kind": "field", "field": target, "type": "str",
                                      "source": {"path": "$." + target}}},
            "confidence": {"level": "high"},
            "review": {"state": "pending"},
        })
    path = project / "import" / mapping / f"{batch}.batch.json"
    path.write_text(json.dumps({"rules": rules}))
    print(json.dumps(import_batch.add(project, mapping, path, batch)), file=sys.stderr)"""


def fake(tmp_path: Path, source: Path, worker: str) -> str:
    script = tmp_path / "fake.py"
    script.write_text(FAKE.format(root=str(ROOT), source=str(source), worker=worker))
    wrapper = tmp_path / "fake.sh"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    return str(wrapper)


def start(tmp_path: Path, worker: str) -> tuple[Path, Path, str]:
    source = make(tmp_path / "source") / "import" / "demo"
    shutil.rmtree(source / "queue.json", ignore_errors=True)
    root = tmp_path / "project"
    shutil.copytree(tmp_path / "source" / "project" / "schemas", root / "schemas")
    document = tmp_path / "spec.txt"
    document.write_text("a\n\nb\n\nc\n", encoding="utf-8")
    return root, document, fake(tmp_path, source, worker)


def drive(root: Path, document: Path, override: str, **more: Any) -> tuple[dict, list[dict]]:
    events: list[dict] = []
    result = import_drive.drive(
        root,
        document,
        provider="claude",
        emit=events.append,
        override=override,
        long_over=0,
        size=2,
        **more,
    )
    return result, events


def test_a_long_document_is_surveyed_queued_and_translated_in_batches(tmp_path: Path) -> None:
    root, document, program = start(tmp_path, TRANSLATE)
    result, events = drive(root, document, program, concurrency=2)
    assert result["status"] == "ready_for_review", result
    assert result["mapping"] == "demo" and result["rules"] == 7
    assert result["batches"] == {"total": 2, "left": 0}
    kinds = [e["event"] for e in events]
    assert kinds.index("surveyed") < kinds.index("queue") < kinds.index("batch_started")
    assert kinds.count("batch") == 2
    plan = load_plan(root, "demo")
    assert plan["coverage"]["imported"] == 7 and plan["coverage"]["units_total"] == 7
    assert plan["history"][-1]["kind"] == "import"
    assert not (root / "import/demo/ir.json.lock").exists()


def test_a_run_that_ends_without_its_batch_is_tried_again_then_fails(tmp_path: Path) -> None:
    root, document, program = start(tmp_path, "pass")
    result, events = drive(root, document, program, concurrency=1)
    assert result["status"] == "failed"
    assert "batch(es) did not finish" in result["error"]
    queue = json.loads((root / "import/demo/queue.json").read_text())
    assert [b["status"] for b in queue["batches"]] == ["failed", "failed"]
    assert all(b["attempts"] == 2 for b in queue["batches"])
    # going on later takes up the failed batches again once they are given back
    for b in queue["batches"]:
        b["status"] = "pending"
        b["attempts"] = 0
    (root / "import/demo/queue.json").write_text(json.dumps(queue))
    program = fake(tmp_path, tmp_path / "source" / "project" / "import" / "demo", TRANSLATE)
    result, _ = drive(root, document, program, mode="resume", mapping="demo")
    assert result["status"] == "ready_for_review" and result["rules"] == 7


def test_cancelling_gives_the_batches_back(tmp_path: Path) -> None:
    root, document, program = start(tmp_path, "import time; time.sleep(30)")
    cancel = threading.Event()
    threading.Timer(2.5, cancel.set).start()
    events: list[dict] = []
    result = import_drive.drive(
        root, document, provider="claude", emit=events.append, override=program,
        cancelled=cancel, long_over=0, size=2, concurrency=2,
    )  # fmt: skip
    assert result == {"status": "cancelled"}
    queue = json.loads((root / "import/demo/queue.json").read_text())
    assert {b["status"] for b in queue["batches"]} == {"pending"}


def test_a_refusal_stops_the_workers_and_is_reported(tmp_path: Path) -> None:
    refused = (
        'print(json.dumps({"type": "result", "result": "x", "permission_denials": '
        '[{"tool_name": "Bash", "tool_input": {"command": "python x.py"}}]}), flush=True); sys.exit(0)'
    )
    root, document, program = start(tmp_path, refused)
    result, events = drive(root, document, program, concurrency=1)
    assert result["status"] == "failed"
    assert result["denied"] == [
        {"tool": "Bash", "what": "python x.py", "rule": "Bash(python x.py)"}
    ]
    assert [e["event"] for e in events].count("batch_started") == 1  # no second run to be refused


def test_a_short_document_is_a_single_run(tmp_path: Path) -> None:
    root, document, program = start(tmp_path, TRANSLATE)
    events: list[dict] = []
    import_drive.drive(
        root, document, provider="claude", emit=events.append, override=program, long_over=999
    )
    kinds = [e["event"] for e in events]
    assert "started" in kinds and "queue" not in kinds and "surveyed" not in kinds
