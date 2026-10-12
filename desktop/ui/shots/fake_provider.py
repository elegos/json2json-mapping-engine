#!/usr/bin/env python3
"""A stand-in for the import assistant (`J2JME_IMPORT_PROVIDER`), for the headless shots: prints
events like Claude Code's stream and leaves a plan for the tour project's `orders` schemas.
`import` writes a plan with open questions, `resume` reads the answers, `rerun_partial` reads the
notes. A document with `slow` in its name makes a run last a minute (to cancel it)."""

import json
import os
import pathlib
import sys
import time

prompt = sys.argv[1]


def field(name: str) -> str:
    for line in prompt.splitlines():
        if line.startswith(f"- {name}: "):
            return line.split(": ", 1)[1].strip()
    return ""


mode, document, rule_ids = field("mode"), field("document"), field("rule_ids")
delay = float(os.environ.get("J2JME_FAKE_DELAY", "0.25"))
mapping = "orders_import"
plan_path = pathlib.Path("import") / mapping / "ir.json"


def say(text: str) -> None:
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}), flush=True)
    time.sleep(delay)


def fn_rule(rid, field_name, type_, source=None, expression=None, parent=None):
    fn = {"id": rid, "kind": "field", "field": field_name, "type": type_}
    if source is not None:
        fn["source"] = source if isinstance(source, dict) else {"path": source}
    if expression:
        fn["transform"] = {"expression": expression}
    return fn


def rule(rid, location, text, target, interpretation, level, fn=None, parent=None, **more):
    out = {
        "id": f"{rid}@{location}",
        "evidence": {"locations": [{"sheet": "Mapping", "cells": location}], "text": text, "sha256": "0"},
        "target": {"path": target, "in_schema": True},
        "intent": more.pop("intent", "copy"),
        "interpretation": interpretation,
        "confidence": {"level": level, **more.pop("confidence", {})},
        "review": {"state": "pending"},
    }
    if fn is not None:
        out["proposal"] = {"fn_rule": fn}
        if parent:
            out["proposal"]["parent_rule"] = parent
    out.update(more)
    return out


def first_plan() -> dict:
    lines = rule(
        "Lines", "A8:F8", "Lines | each item of the order", "$.Lines[*]",
        "One line per item of the order.", "high",
        {"id": "lines", "kind": "loop", "label": "line", "index_start": 1, "source": "$.items[*]", "output": "Lines[*]"},
        intent="loop",
    )
    rules = [
        rule("OrderId", "A2:F2", "OrderId | Y | id", "$.OrderId", "The order id, unchanged.", "high",
             fn_rule("oid", "OrderId", "str", "$.id")),
        rule("MapVersion", "A3:F3", "MapVersion | Y | constant 3", "$.MapVersion", "The version of the mapping: 3.",
             "high", fn_rule("ver", "MapVersion", "int", {"constant": 3}), intent="constant"),
        rule("Channel", "A4:F4", "Channel | N | metadata.source", "$.Channel", "Where the order came from.", "high",
             fn_rule("chan", "Channel", "str", "$.metadata.source")),
        rule("Warehouse", "A5:F5", "Warehouse | N | third element of ref, split on comma", "$.Warehouse",
             "The third element of the comma separated reference.", "medium",
             fn_rule("wh", "Warehouse", "str", "$.ref", 'split_nth(value, ",", 3)'),
             intent="expression",
             assumptions=[{"topic": "index_base", "assumed": "1-based: 'third' is index 3", "basis": "guess", "question_id": "q_index"}],
             confidence={"reasons": ["the document never says whether elements are counted from 0 or 1"],
                         "flags": ["unconfirmed_convention"]},
             back_translation="The third comma separated element of ref (counting from 1)."),
        rule("Currency", "A6:F6", "Currency | N | currency of the country (table in sheet Countries)", "$.Currency",
             "The currency of the order's country, from the countries table.", "guess",
             intent="lookup",
             confidence={"reasons": ["the countries table is not in the document"], "flags": ["missing_lookup"]}),
        lines,
        rule("Sku", "B9:F9", "Sku | Y | sku", "$.Lines[*].Sku", "The item's sku.", "high",
             fn_rule("sku", "Sku", "str", "@.sku"), parent="lines"),
        rule("Qty", "B10:F10", "Qty | Y | qty", "$.Lines[*].Qty", "The item's quantity.", "high",
             fn_rule("qty", "Qty", "int", "@.qty"), parent="lines"),
        rule("Family", "B11:F11", "Family | Y | first letters of the sku", "$.Lines[*].Family",
             "The family of the item: read as the first two letters of the sku, in upper case.", "low",
             fn_rule("fam", "Family", "str", "@.sku", "upper(value)"), parent="lines", intent="expression",
             assumptions=[{"topic": "family_length", "assumed": "all of the sku, upper case", "basis": "guess", "question_id": "q_family"}],
             confidence={"reasons": ["\"first letters\" does not say how many"], "flags": ["ambiguous"]}),
    ]
    rules[4]["proposal"] = {"functions_missing": [{"needed": "lookup in a table the document does not contain"}]}
    return {
        "ir_version": 1,
        "mapping": {"id": mapping, "name": "Orders (imported)"},
        "document": {"file": document, "sha256": "0", "format": "xlsx", "language": "en",
                     "version": {"resolved": "2.1", "origin": "version_sheet",
                                 "candidates": [{"origin": "file_name", "value": "2.1"}, {"origin": "version_sheet", "value": "2.1"}]}},
        "profile": {"name": "orders-sheet", "sha256": "0", "origin": "new"},
        "schemas": {"input": {"origin": "provided", "path": "schemas/orders_input.schema.json", "confirmed": True},
                    "output": {"origin": "provided", "path": "schemas/orders_output.schema.json", "confirmed": True}},
        "lookups": [{"name": "countryCurrency", "status": "missing", "location": {"sheet": "Mapping", "cells": "F6"}}],
        "validations": [
            {"id": "country_given", "side": "input", "expect": "$.country", "code": "REQ-1", "message": "The country is mandatory.",
             "action": "reject",
             "evidence": {"locations": [{"sheet": "Mapping", "cells": "A14"}], "text": "Reject the order when the country is empty.", "sha256": "0"},
             "interpretation": "An order without a country is refused.", "confidence": {"level": "high"}, "review": {"state": "pending"}},
            {"id": "has_items", "side": "input", "expect": "count($.items) > 0", "code": "REQ-2", "message": "The order has no items.",
             "action": "warn",
             "evidence": {"locations": [{"sheet": "Mapping", "cells": "A15"}], "text": "Report orders without items.", "sha256": "0"},
             "interpretation": "An order with no items is reported, not refused.", "confidence": {"level": "medium", "reasons": ["\"report\" could also mean reject"], "flags": ["ambiguous"]},
             "review": {"state": "pending"}},
        ],
        "rules": rules,
        "questions": [
            {"id": "q_index", "topic": "index_base", "scope": "profile",
             "text": "Are positions in the document counted from 0 or from 1?",
             "proposal": "1-based", "options": ["0-based", "1-based"],
             "evidence": [{"text": "Warehouse | N | third element of ref, split on comma", "location": {"sheet": "Mapping", "cells": "A5:F5"}}],
             "rule_ids": ["Warehouse@A5:F5"], "status": "open"},
            {"id": "q_currency", "topic": "country_currency", "scope": "mapping",
             "text": "Sheet Countries is cited but not in the file. Which countries and currencies does the table hold?",
             "proposal": "IT, FR and DE map to EUR; anything else to N/A",
             "evidence": [{"text": "Currency | N | currency of the country (table in sheet Countries)", "location": {"sheet": "Mapping", "cells": "A6:F6"}}],
             "rule_ids": ["Currency@A6:F6"], "status": "open"},
            {"id": "q_family", "topic": "family_length", "scope": "rule",
             "text": "How many letters of the sku make the family?",
             "proposal": "2", "options": ["1", "2", "3"],
             "evidence": [{"text": "Family | Y | first letters of the sku", "location": {"sheet": "Mapping", "cells": "B11:F11"}}],
             "rule_ids": ["Family@B11:F11"], "status": "open"},
        ],
        "discrepancies": [
            {"kind": "schema_field_not_mapped", "severity": "info", "detail": "The output schema has a Customer object the document does not mention.", "paths": ["$.Customer"]},
            {"kind": "enum_mismatch", "severity": "warning", "detail": "The document says Qty is a decimal, the input schema says integer.", "rule_ids": ["Qty@B10:F10"], "paths": ["$.items[*].qty"]},
        ],
        "coverage": {"units_total": 11, "imported": 7, "imported_with_doubt": 3,
                     "not_imported": [{"location": {"sheet": "Mapping", "cells": "A1:F1"}, "reason": "header_or_title"},
                                      {"location": {"sheet": "Mapping", "cells": "A17"}, "reason": "removed_in_document", "detail": "struck through"}]},
        "tests": [
            {"id": "case1", "origin": {"sheet": "Examples", "cells": "A1:D6"}, "trust": "paired_in_document",
             "input": {"id": "O-1", "country": "IT", "ref": "a,b,W7", "metadata": {"source": "web"}, "parties": [], "currencies": {},
                       "items": [{"sku": "ab1", "qty": 2, "total": 4.5}]},
             "expected": {"OrderId": "O-1", "Warehouse": "W7", "Channel": "web", "MapVersion": 3,
                          "Lines": [{"Sku": "ab1", "Qty": 2}]}, "partial": True,
             "rule_ids": ["OrderId@A2:F2", "Warehouse@A5:F5"]},
        ],
    }


def resume(plan: dict) -> dict:
    answers = {q["id"]: q for q in plan["questions"]}
    for r in plan["rules"]:
        if r["id"].startswith("Warehouse") and answers.get("q_index", {}).get("status") != "open":
            ans = answers["q_index"].get("answer", "1-based")
            index = "2" if ans.startswith("0") else "3"
            r["proposal"]["fn_rule"]["transform"]["expression"] = f'split_nth(value, ",", {index})'
            r["confidence"] = {"level": "high"}
            r["assumptions"] = [{"topic": "index_base", "assumed": ans, "basis": "user_answer", "question_id": "q_index"}]
        if r["id"].startswith("Currency") and answers.get("q_currency", {}).get("status") != "open":
            r["proposal"] = {"fn_rule": fn_rule("cur", "Currency", "str", "$.country", 'lookup(value, @countryCurrency, "N/A")')}
            r["confidence"] = {"level": "medium", "reasons": ["the table comes from an answer, not from the document"]}
            r["review"]["state"] = "pending"
    if answers.get("q_currency", {}).get("status") != "open":
        plan["lookups"] = [{"name": "countryCurrency", "status": "partial", "entries": {"IT": "EUR", "FR": "EUR", "DE": "EUR"}}]
    return plan


def partial(plan: dict, ids: list[str]) -> dict:
    for r in plan["rules"]:
        if r["id"] in ids:
            note = r.get("review", {}).pop("note", None)
            r["confidence"] = {"level": "medium", "reasons": [f"re-read with the note: {note}"]}
            r["review"] = {"state": "pending"}
    for q in plan["questions"]:
        if q["topic"] == "user_note" and q["rule_ids"][0] in ids:
            q["text"] = q["text"] + " (read)"
    return plan


say(f"Reading {document}")
say("Extracting the tables (mapper import extract)")
if "slow" in document:
    time.sleep(60)
plan_path.parent.mkdir(parents=True, exist_ok=True)
if mode == "import" or not plan_path.exists():
    say("Found one mapping; discovering conventions")
    plan = first_plan()
else:
    plan = json.loads(plan_path.read_text())
    say("Reading the answers")
    plan = partial(plan, rule_ids.split(", ")) if mode == "rerun_partial" else resume(plan)
say("Writing the plan")
plan_path.write_text(json.dumps(plan, indent=2))
pathlib.Path("import/profiles").mkdir(parents=True, exist_ok=True)
pathlib.Path("import/profiles/orders-sheet.profile.yaml").write_text(
    "name: orders-sheet\ndescription: One sheet, one row per target field\nconventions:\n"
    "  - topic: index_base\n    value: 1-based\n    basis: user_answer\n    confirmed: false\n"
)
open_questions = sum(1 for q in plan["questions"] if q.get("status", "open") == "open")
status = "needs_answers" if open_questions else "ready_for_review"
print(json.dumps({"type": "result", "result": "Done.\n" + json.dumps(
    {"status": status, "ir": str(plan_path), "open_questions": open_questions, "rules": len(plan["rules"]), "guesses": 2})}), flush=True)
