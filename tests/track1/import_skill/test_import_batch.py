"""Importing in batches: the survey's units, the mechanical rules, the queue, `add`, the live
questions. No assistant is involved: these are the commands it calls."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from cli import import_batch, import_ops
from cli.import_plan import PlanError, load_plan

EXAMPLE = Path(__file__).parents[3] / "docs/import/examples/wb1_excerpt.ir.json"
SHEET = "Mapping"


def cell(text: str, at: str) -> dict[str, Any]:
    return {"text": text, "location": {"cells": at}}


def location(row: int) -> dict[str, str]:
    return {"sheet": SHEET, "cells": f"A{row}:C{row}"}


ROWS = {
    1: ("Target", "Type", "Logic"),
    2: ("kind", "string", "Hardcoded: 'K'"),
    3: ("box", "object", "Parent Object"),
    4: ("box.x", "string", "Hardcoded: 'X'"),
    5: ("box.y", "string", "Direct from a"),
    6: ("a", "string", "from a"),
    7: ("b", "string", "from b"),
    8: ("c", "string", "from c"),
}


def unit(row: int, kind: str, **more: Any) -> dict[str, Any]:
    return {"id": f"{SHEET}!A{row}", "location": location(row), "class": kind, **more}


def make(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "schemas").mkdir(parents=True)
    string = {"type": "string"}
    (root / "schemas" / "demo_input.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"a": string, "b": string, "c": string},
            }
        )
    )
    (root / "schemas" / "demo_output.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "kind": string,
                    "a": string,
                    "b": string,
                    "c": string,
                    "box": {"type": "object", "properties": {"x": string, "y": string}},
                },
            }
        )
    )
    folder = root / "import" / "demo"
    folder.mkdir(parents=True)
    rows = [
        {"cells": [cell(t, f"{col}{n}") for t, col in zip(texts, "ABC", strict=True)]}
        for n, texts in ROWS.items()
    ]
    (folder / "document.json").write_text(
        json.dumps({"tables": [{"id": "t1", "location": {"sheet": SHEET}, "rows": rows}]})
    )
    plan = {
        "ir_version": 1,
        "mapping": {"id": "demo"},
        "document": json.loads(EXAMPLE.read_text())["document"],
        "schemas": {
            "input": {"origin": "provided", "path": "schemas/demo_input.schema.json"},
            "output": {"origin": "provided", "path": "schemas/demo_output.schema.json"},
        },
        "rules": [],
        "questions": [],
        "discrepancies": [],
    }
    (folder / "ir.json").write_text(json.dumps(plan))
    units = {
        "context": [{"kind": "root_path", "text": "Everything below is relative to the message"}],
        "units": [
            unit(1, "skip", reason="header_or_title"),
            unit(2, "constant", target="kind", value="K"),
            unit(3, "structure", target="box"),
            unit(4, "constant", target="box.x", value="X"),
            unit(5, "copy", target="box.y", source="$.a", type="str"),
            unit(6, "translate", target="a", needs=["a thing the engine lacks"]),
            unit(7, "translate", target="b", group="g", needs=["a thing the engine lacks"]),
            unit(8, "translate", target="c", group="g"),
        ],
    }
    (folder / "units.json").write_text(json.dumps(units))
    return root


def rule_for(row: int, target: str, source: str) -> dict[str, Any]:
    return {
        "id": f"{target}@{SHEET}!A{row}",
        "evidence": {"locations": [location(row)]},
        "target": {"path": f"$.{target}"},
        "intent": "copy",
        "interpretation": f"Copies {source}.",
        "proposal": {
            "fn_rule": {
                "id": target,
                "kind": "field",
                "field": target,
                "type": "str",
                "source": {"path": f"$.{source}"},
            }
        },
        "confidence": {"level": "high"},
        "review": {"state": "pending"},
    }


def batch_file(tmp_path: Path, name: str, **content: Any) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(content))
    return path


def test_the_queue_writes_the_mechanical_rules_and_cuts_the_rest_into_batches(
    tmp_path: Path,
) -> None:
    root = make(tmp_path)
    made = import_batch.queue(root, "demo", 2)
    assert made["mechanical"] == 4  # the box before what is inside it, in one call
    assert [b["units"] for b in made["batches"]] == [1, 2]
    plan = load_plan(root, "demo")
    ids = {r["id"] for r in plan["rules"]}
    assert ids == {
        "kind@Mapping!A2",
        "box@Mapping!A3",
        "box.x@Mapping!A4",
        "box.y@Mapping!A5",
    }
    inner = next(r for r in plan["rules"] if r["id"].startswith("box.y"))
    assert inner["proposal"]["parent_rule"] == "box"
    assert inner["proposal"]["check"]["ok"] is True
    # the evidence comes from the document, with its hash and the context every rule inherits
    assert inner["evidence"]["text"] == "box.y | string | Direct from a"
    assert len(inner["evidence"]["sha256"]) == 64
    assert inner["evidence"]["inherited_context"][0]["kind"] == "root_path"
    coverage = plan["coverage"]
    assert (coverage["units_total"], coverage["imported"]) == (7, 4)  # the header is no unit
    assert any(e["reason"] == "needs_user_input" for e in coverage["not_imported"])
    # the units of a group stay together
    assert [u["id"] for u in import_batch.batch_units(root, "demo", "b002")] == [
        "Mapping!A7",
        "Mapping!A8",
    ]
    assert made["pending_units"] == 3


def test_add_merges_a_batch_and_says_what_is_left(tmp_path: Path) -> None:
    root = make(tmp_path)
    import_batch.queue(root, "demo", 30)
    both = batch_file(tmp_path, "b1.json", rules=[rule_for(6, "a", "a"), rule_for(7, "b", "b")])
    done = import_batch.add(root, "demo", both, "b001")
    assert done["added"] == 2 and done["errors"] == {}
    assert done["missing_units"] == ["Mapping!A8"]
    assert (
        next(b for b in json.loads((root / "import/demo/queue.json").read_text())["batches"])[
            "status"
        ]
        == "pending"
    )

    last = batch_file(tmp_path, "b2.json", rules=[rule_for(8, "c", "c"), rule_for(6, "a", "a")])
    done = import_batch.add(root, "demo", last, "b001")
    assert (done["added"], done["replaced"], done["missing_units"]) == (1, 1, [])
    queue = json.loads((root / "import/demo/queue.json").read_text())
    assert queue["batches"][0]["status"] == "done"
    assert load_plan(root, "demo")["coverage"]["imported"] == 7
    assert import_batch.next_batch(root, "demo") is None


def test_a_rule_the_user_decided_on_keeps_its_review(tmp_path: Path) -> None:
    root = make(tmp_path)
    import_batch.add(root, "demo", batch_file(tmp_path, "b.json", rules=[rule_for(6, "a", "a")]))
    import_ops.review(root, "demo", "rule", "a@Mapping!A6", "accepted")
    import_batch.add(root, "demo", batch_file(tmp_path, "c.json", rules=[rule_for(6, "a", "a")]))
    assert load_plan(root, "demo")["rules"][0]["review"]["state"] == "accepted"


def test_a_batch_that_does_not_validate_changes_nothing(tmp_path: Path) -> None:
    root = make(tmp_path)
    before = (root / "import/demo/ir.json").read_bytes()
    broken = rule_for(6, "a", "a")
    del broken["interpretation"]
    with pytest.raises(PlanError, match="interpretation"):
        import_batch.add(root, "demo", batch_file(tmp_path, "x.json", rules=[broken]))
    with pytest.raises(PlanError, match="a batch is an object"):
        import_batch.add(root, "demo", batch_file(tmp_path, "y.json", questions=[]))
    twice = [rule_for(6, "a", "a"), rule_for(7, "a", "b")]  # two rules, one fn rule id
    with pytest.raises(PlanError, match="does not fit"):
        import_batch.add(root, "demo", batch_file(tmp_path, "z.json", rules=twice))
    assert (root / "import/demo/ir.json").read_bytes() == before
    assert not (root / "import/demo/ir.json.lock").exists()


def test_a_check_that_fails_is_reported_for_the_rule(tmp_path: Path) -> None:
    root = make(tmp_path)
    wrong = rule_for(6, "a", "nowhere")  # a path the input schema does not have
    done = import_batch.add(root, "demo", batch_file(tmp_path, "w.json", rules=[wrong]))
    assert "a@Mapping!A6" in done["errors"]


def test_questions_are_asked_once_and_read_back(tmp_path: Path) -> None:
    root = make(tmp_path)
    first = import_batch.ask(
        root,
        "demo",
        "Is the index 1-based?",
        topic="index_base",
        options=["1", "0"],
        proposal="1",
        rule_ids=["a@Mapping!A6"],
    )
    again = import_batch.ask(
        root, "demo", "is the index 1-based", topic="index_base", rule_ids=["b@Mapping!A7"]
    )
    assert again["id"] == first["id"] and again["existing"] and again["status"] == "open"
    other = import_batch.ask(root, "demo", "Which sheet holds the codes?", topic="lookup")
    assert other["id"] != first["id"]
    plan = load_plan(root, "demo")
    assert plan["questions"][0]["rule_ids"] == ["a@Mapping!A6", "b@Mapping!A7"]

    assert import_batch.answers(root, "demo")["open"] == [first["id"], other["id"]]
    import_ops.answer(root, "demo", [{"id": first["id"], "answer": "0"}])
    given = import_batch.answers(root, "demo")
    assert [a["answer"] for a in given["answers"]] == ["0"]
    assert (
        import_batch.ask(root, "demo", "Is the index 1-based?", topic="index_base")["answer"] == "0"
    )
    # a rule written before the answer needs to be read again, one written after it does not
    import_batch.queue(root, "demo", 30)
    everything = [rule_for(6, "a", "a"), rule_for(7, "b", "b"), rule_for(8, "c", "c")]
    import_batch.add(root, "demo", batch_file(tmp_path, "b.json", rules=everything), "b001")
    assert import_batch.rework(root, "demo") == []
    late = import_batch.ask(
        root, "demo", "What does a hold?", topic="a_topic", rule_ids=["a@Mapping!A6"]
    )
    import_ops.answer(root, "demo", [{"id": late["id"], "answer": "a text"}])
    assert import_batch.rework(root, "demo") == ["a@Mapping!A6"]
    made = import_batch.queue_rework(root, "demo", ["a@Mapping!A6"])
    assert made is not None and made["id"] == "r001" and made["units"] == ["Mapping!A6"]
    claimed = import_batch.next_batch(root, "demo")
    assert claimed is not None and claimed["id"] == "r001"
    with pytest.raises(PlanError):
        import_batch.ask(root, "demo", " ", topic="x")


def test_the_gaps_are_known_before_the_rules_are_written(tmp_path: Path) -> None:
    root = make(tmp_path)
    found = import_batch.gaps(root, "demo")
    assert found["expected"] == [
        {
            "need": "a thing the engine lacks",
            "units": 2,
            "examples": ["Mapping!A6", "Mapping!A7"],
        }
    ]


def test_a_bad_survey_is_refused_with_what_is_wrong(tmp_path: Path) -> None:
    root = make(tmp_path)
    units = json.loads((root / "import/demo/units.json").read_text())
    units["units"][1]["class"] = "magic"
    del units["units"][4]["source"]
    (root / "import/demo/units.json").write_text(json.dumps(units))
    with pytest.raises(PlanError) as caught:
        import_batch.queue(root, "demo")
    assert "class must be one of" in str(caught.value) and "a copy needs a source" in str(
        caught.value
    )


def test_parallel_writers_do_not_lose_each_others_questions(tmp_path: Path) -> None:
    root = make(tmp_path)
    failures: list[Exception] = []

    def writer(n: int) -> None:
        try:
            for k in range(5):
                import_batch.ask(root, "demo", f"question number {n} {k} zzz{n}{k}", topic=f"t{n}")
        except Exception as exc:  # noqa: BLE001
            failures.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert failures == []
    assert len(load_plan(root, "demo")["questions"]) == 20
