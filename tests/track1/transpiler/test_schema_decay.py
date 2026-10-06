"""A validated rule the new schema invalidates goes back to review (`transpiler/schema_decay.py`)."""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.serve import serve
from transpiler.model import FieldRule, FunctionalFile, functional_to_dict, parse_functional
from transpiler.schema_decay import review_after_schema_change

OUT = {
    "type": "object",
    "properties": {
        "Id": {"type": "string"},
        "Total": {"type": "number"},
        "Note": {"type": "string"},
    },
}
IN = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "total": {"type": "number"},
        "note": {"type": "string"},
    },
}


def _field(
    name: str, source: str, *, validated: bool, review: bool = False, type_: str = "str"
) -> dict:
    return {
        "kind": "field",
        "id": name.lower(),
        "field": name,
        "type": type_,
        "source": {"path": source},
        "validation": {"validated": validated, "needs_review": review},
    }


def _file() -> FunctionalFile:
    return parse_functional(
        {
            "id": "t",
            "rules": [
                _field("Id", "$.id", validated=True),
                _field("Total", "$.total", validated=True, type_="number"),
                _field("Note", "$.note", validated=True),
            ],
        },
        "t",
    )


def _state(file: FunctionalFile) -> dict[str, tuple[bool, bool]]:
    return {
        r.field: (r.validation.validated, r.validation.needs_review)
        for r in file.rules
        if isinstance(r, FieldRule)
    }


def test_only_the_rules_the_new_schema_breaks_go_back_to_review() -> None:
    file = _file()
    gone = {**IN, "properties": {k: v for k, v in IN["properties"].items() if k != "total"}}
    moved = review_after_schema_change(file, "input", (IN, OUT), (gone, OUT))
    assert [m["path"] for m in moved] == ["rules[1]"]
    assert _state(file) == {"Id": (True, False), "Total": (False, True), "Note": (True, False)}
    note = file.rules[1].validation.notes  # type: ignore[union-attr]
    assert note is not None and "input schema was loaded" in note and "total" in note


def test_a_type_that_changed_counts_as_well_as_a_path_that_went() -> None:
    file = _file()
    retyped = {**OUT, "properties": {**OUT["properties"], "Total": {"type": "string"}}}
    moved = review_after_schema_change(file, "output", (IN, OUT), (IN, retyped))
    assert [m["path"] for m in moved] == ["rules[1]"]


def test_a_rule_in_review_or_never_validated_stays_as_it_is() -> None:
    file = parse_functional(
        {
            "id": "t",
            "rules": [
                _field("Id", "$.gone", validated=False, review=True),
                _field("Note", "$.gone2", validated=False),
            ],
        },
        "t",
    )
    assert review_after_schema_change(file, "input", (None, OUT), (IN, OUT)) == []
    assert _state(file) == {"Id": (False, True), "Note": (False, False)}


def test_an_error_the_old_schema_already_gave_is_not_the_change() -> None:
    file = _file()
    both = {**IN, "properties": {k: v for k, v in IN["properties"].items() if k != "note"}}
    assert review_after_schema_change(file, "input", (both, OUT), (both, OUT)) == []
    assert _state(file)["Note"] == (True, False)


def test_a_compatible_new_schema_moves_nothing() -> None:
    file = _file()
    wider = {**IN, "properties": {**IN["properties"], "extra": {"type": "string"}}}
    assert review_after_schema_change(file, "input", (IN, OUT), (wider, OUT)) == []


def test_loading_a_schema_answers_the_tree_with_the_rules_sent_back(tmp_path: Path) -> None:
    project = tmp_path / "p"
    (project / "schemas").mkdir(parents=True)
    (project / "schemas/t_input.schema.json").write_text(json.dumps(IN))
    (project / "schemas/t_output.schema.json").write_text(json.dumps(OUT))
    gone = {**IN, "properties": {k: v for k, v in IN["properties"].items() if k != "total"}}
    new = tmp_path / "new.json"
    new.write_text(json.dumps(gone))
    out = io.StringIO()
    request = {
        "id": 1,
        "op": "schema_import",
        "project": str(project),
        "stem": "t",
        "kind": "input",
        "source": str(new),
        "tree": functional_to_dict(_file()),
    }
    serve(io.StringIO(json.dumps(request) + "\n"), out)
    [answer] = [json.loads(line) for line in out.getvalue().splitlines()]
    assert answer["ok"] and [m["path"] for m in answer["moved"]] == ["rules[1]"]
    rules = answer["tree"]["rules"]
    assert [r["validation"]["needs_review"] for r in rules] == [False, True, False]
    assert (project / "schemas/t_input.schema.json").read_text() == json.dumps(gone)
