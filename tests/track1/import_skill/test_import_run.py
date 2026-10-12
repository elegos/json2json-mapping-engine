"""`mapper import run` with a stand-in for the assistant (`J2JME_IMPORT_PROVIDER`), and the
operations behind the import screens. The real assistants are tried by hand."""

from __future__ import annotations

import json
import stat
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from cli import import_ops, import_run
from cli.import_plan import PlanError

EXAMPLE = Path(__file__).parents[3] / "docs/import/examples/wb1_excerpt.ir.json"


def fake(tmp_path: Path, body: str) -> str:
    script = tmp_path / "fake_provider.py"
    script.write_text(
        f"import json, sys, pathlib\nprompt = sys.argv[1]\n{body}\n", encoding="utf-8"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    wrapper = tmp_path / "fake_provider.sh"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    return str(wrapper)


WRITES_PLAN = f"""
plan = json.loads(pathlib.Path({str(EXAMPLE)!r}).read_text())
doc = prompt.split("- document: ")[1].splitlines()[0]
plan["document"]["file"] = doc
pathlib.Path("import/reservation_task").mkdir(parents=True)
pathlib.Path("import/reservation_task/ir.json").write_text(json.dumps(plan))
print(json.dumps({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "reading"}}]}}}}))
print(json.dumps({{"type": "result", "result": "done\\n{{\\"status\\": \\"needs_answers\\"}}"}}))
"""


def project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "project"
    root.mkdir()
    document = tmp_path / "spec.txt"
    document.write_text("a rule\n", encoding="utf-8")
    return root, document


def run(
    root: Path, document: Path, override: str, **more: Any
) -> tuple[dict[str, Any], list[dict]]:
    events: list[dict] = []
    result = import_run.run(
        root, document, provider="claude", emit=events.append, override=override, **more
    )
    return result, events


def test_a_run_leaves_a_checked_plan_with_its_hashes(tmp_path: Path) -> None:
    root, document = project(tmp_path)
    result, events = run(root, document, fake(tmp_path, WRITES_PLAN))
    assert result["status"] == "needs_answers"
    assert result["mapping"] == "reservation_task"
    assert result["open_questions"] == 1
    assert [e["event"] for e in events][0] == "started"
    assert {"event": "progress", "text": "reading"} in events
    # the document was brought into the project and the plan points to it
    assert (root / "import/documents/spec.txt").is_file()
    plan = json.loads((root / "import/reservation_task/ir.json").read_text())
    assert plan["document"]["file"] == "import/documents/spec.txt"
    assert plan["document"]["sha256"] == import_run.sha256_of(root / "import/documents/spec.txt")
    assert import_ops.list_imports(root)[0]["state"] == "needs_answers"


def test_an_invalid_plan_is_a_failed_run_and_the_old_plan_stays(tmp_path: Path) -> None:
    root, document = project(tmp_path)
    (root / "import/m").mkdir(parents=True)
    (root / "import/m/ir.json").write_text('{"keep": 1}')
    body = "pathlib.Path('import/m/ir.json').write_text('{\"rules\": 1}')"
    result, _ = run(root, document, fake(tmp_path, body))
    assert result["status"] == "failed"
    assert result["details"]
    assert json.loads((root / "import/m/ir.json").read_text()) == {"keep": 1}


def test_a_run_that_fails_says_why(tmp_path: Path) -> None:
    root, document = project(tmp_path)
    body = 'print(json.dumps({"status": "failed", "error": "extractor_unavailable"}))'
    result, _ = run(root, document, fake(tmp_path, body))
    assert result == {"status": "failed", "error": "extractor_unavailable"}


def test_cancel_stops_the_assistant(tmp_path: Path) -> None:
    root, document = project(tmp_path)
    cancelled = threading.Event()
    threading.Timer(0.5, cancelled.set).start()
    result, _ = run(
        root, document, fake(tmp_path, "import time; time.sleep(60)"), cancelled=cancelled
    )
    assert result == {"status": "cancelled"}


def test_answers_notes_and_review_are_written_into_the_plan(tmp_path: Path) -> None:
    root, document = project(tmp_path)
    run(root, document, fake(tmp_path, WRITES_PLAN))
    shown = import_ops.read_plan(root, "reservation_task")
    assert shown["problems"] == []
    rule_id = shown["plan"]["rules"][0]["id"]
    import_ops.review(root, "reservation_task", "rule", rule_id, "accepted")
    question = import_ops.note(root, "reservation_task", rule_id, "use the other sheet")
    left = import_ops.answer(root, "reservation_task", [{"id": "q3", "skip": True}])
    assert left == {"open_questions": 0}
    assert import_ops.read_plan(root, "reservation_task")["state"] == "answered"
    plan = import_ops.read_plan(root, "reservation_task")["plan"]
    assert plan["rules"][0]["review"]["note"] == "use the other sheet"
    assert import_ops.read_plan(root, "reservation_task")["problems"] == []
    asked = {q["id"]: q for q in plan["questions"]}
    assert asked[question]["answer"] == "use the other sheet"
    assert asked["q3"]["status"] == "skipped_assumed_proposal"
    with pytest.raises(PlanError):
        import_ops.answer(root, "reservation_task", [{"id": "q3", "answer": " "}])
    with pytest.raises(PlanError):
        import_ops.read_plan(root, "../x")


def test_a_changed_document_marks_the_plan_stale(tmp_path: Path) -> None:
    root, document = project(tmp_path)
    run(root, document, fake(tmp_path, WRITES_PLAN))
    (root / "import/documents/spec.txt").write_text("changed\n", encoding="utf-8")
    assert import_ops.list_imports(root)[0]["stale"] == ["document"]
