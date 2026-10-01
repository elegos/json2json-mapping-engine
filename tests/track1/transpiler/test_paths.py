"""The `paths:` section: root override and path aliases."""

from __future__ import annotations

import pytest

from transpiler.check import check_functional
from transpiler.model import FieldRule, FnYamlError, PathsSection, parse_functional
from transpiler.paths import expand_paths, expand_text
from transpiler.serialize import functional_to_raw
from transpiler.transpile import transpile_file_model

PATHS = PathsSection(root="$.payload.list[0]", aliases={"metadata": "$.payload.metadata"})


def raw(paths: object = None, **extra: object) -> dict:
    data: dict = {
        "id": "t",
        "rules": [
            {
                "kind": "field",
                "id": "a",
                "field": "Id",
                "type": "str",
                "source": {"path": "$.id"},
                "transform": {"expression": 'lookup(@metadata.kind, @kinds, "?")'},
            },
            {"kind": "lookup", "label": "kinds", "entries": {"a": "A"}},
        ],
    }
    if paths is not None:
        data["paths"] = paths
    data.update(extra)
    return data


def test_one_pass_expansion() -> None:
    assert expand_text("$.a + @metadata.b + @root.c", PATHS) == (
        "$.payload.list[0].a + $.payload.metadata.b + $.c"
    )
    assert expand_text('"$.x @metadata" + $.y', PATHS) == '"$.x @metadata" + $.payload.list[0].y'
    assert expand_text("@item.sku + @.x + @index", PATHS) == "@item.sku + @.x + @index"
    assert expand_text("$.a", PathsSection()) == "$.a"
    assert expand_text("@root.a", PathsSection()) == "$.a"


def test_loader_reads_and_serializer_writes_the_section() -> None:
    file = parse_functional(
        raw({"root": "$.payload.list[0]", "aliases": {"metadata": "$.p.m"}}), "t"
    )
    assert file.paths.root == "$.payload.list[0]" and file.paths.aliases == {"metadata": "$.p.m"}
    assert functional_to_raw(file)["paths"] == {
        "root": "$.payload.list[0]",
        "aliases": {"metadata": "$.p.m"},
    }
    assert "paths" not in functional_to_raw(parse_functional(raw(), "t"))


@pytest.mark.parametrize(
    ("paths", "message"),
    [
        ({"root": "payload"}, "paths.root"),
        ({"root": "$.a[*]"}, "paths.root"),
        ({"aliases": {"root": "$.a"}}, "reserved"),
        ({"aliases": {"index": "$.a"}}, "reserved"),
        ({"aliases": {"kinds": "$.a"}}, "lookup"),
        ({"aliases": {"ok": "a.b"}}, "paths.aliases.ok"),
        ({"aliases": {"bad name": "$.a"}}, "not a valid alias"),
        ({"nope": 1}, "unknown"),
    ],
)
def test_loader_rejects(paths: dict, message: str) -> None:
    with pytest.raises(FnYamlError, match=message):
        parse_functional(raw(paths), "t")


def test_an_alias_cannot_share_a_loop_label() -> None:
    data = raw({"aliases": {"item": "$.a"}})
    data["rules"].append(
        {"kind": "loop", "label": "item", "source": "$.xs[*]", "output": "L[*]", "rules": []}
    )
    with pytest.raises(FnYamlError, match="label of a loop"):
        parse_functional(data, "t")


def test_expand_paths_leaves_the_original_alone() -> None:
    file = parse_functional(
        raw({"root": "$.payload.list[0]", "aliases": {"metadata": "$.p.m"}}), "t"
    )
    expanded = expand_paths(file)
    rule, again = file.rules[0], expanded.rules[0]
    assert isinstance(rule, FieldRule) and isinstance(again, FieldRule)
    assert rule.source_path == "$.id" and again.source_path == "$.payload.list[0].id"
    assert again.transform.expression == 'lookup($.p.m.kind, @kinds, "?")'
    assert rule.transform.expression == 'lookup(@metadata.kind, @kinds, "?")'


def test_check_resolves_aliases_against_the_input_schema() -> None:
    schema = {
        "type": "object",
        "properties": {
            "payload": {
                "type": "object",
                "properties": {
                    "metadata": {"type": "object", "properties": {"kind": {"type": "string"}}},
                    "list": {
                        "type": "array",
                        "items": {"type": "object", "properties": {"id": {"type": "string"}}},
                    },
                },
            }
        },
    }
    out = {"type": "object", "properties": {"Id": {"type": "string"}}, "required": ["Id"]}
    file = parse_functional(
        raw({"root": "$.payload.list[0]", "aliases": {"metadata": "$.payload.metadata"}}), "t"
    )
    assert [i for i in check_functional(file, schema, out) if i.severity == "error"] == []
    file.paths.aliases["metadata"] = "$.payload.nowhere"
    messages = [i.message for i in check_functional(file, schema, out)]
    assert any("alias 'metadata'" in m and "nowhere" in m for m in messages)


def test_transpile_applies_the_override() -> None:
    file = parse_functional(
        raw({"root": "$.payload", "aliases": {"metadata": "$.payload.metadata"}}), "t"
    )
    rule = file.rules[0]
    assert isinstance(rule, FieldRule)
    rule.transform.expression = "lookup(@metadata.kind, @kinds, $.id)"
    text = transpile_file_model(file)
    assert "lookup(root.payload.metadata.kind, {'a': 'A'}, root.payload.id)" in text


def test_check_reports_bad_names_and_paths_of_an_edited_section() -> None:
    file = parse_functional(raw(), "t")
    file.paths = PathsSection(
        root="payload", aliases={"kinds": "$.a", "root": "$.b", "ok": "$.c", "bad name": "$.d"}
    )
    messages = [i.message for i in check_functional(file) if i.rule == ""]
    assert any("root must be a path" in m for m in messages)
    assert any("'kinds' is also the name of a lookup" in m for m in messages)
    assert any("'root' is reserved" in m for m in messages)
    assert any("'bad name' is not a valid name" in m for m in messages)
    assert not any("'ok'" in m for m in messages)
