from pathlib import Path

import pytest

from compiler.pipeline import compile_source
from compiler.schema_generator import resolve_schema_types
from transpiler.anchors import AnchorScope, LoopRef, resolve_anchors
from transpiler.expr import parse_block
from transpiler.ids import assign_ids, suggest_local_id, walk
from transpiler.model import (
    FieldRule,
    FnYamlError,
    LoopRule,
    apply_decay,
    parse_functional,
)
from transpiler.transpile import TranspileOptions, transpile_file, transpile_file_model

FIXTURES = Path(__file__).parent / "fixtures"


def model(rules: list[dict], **extra):
    return parse_functional({"id": "m", "rules": rules, **extra}, default_id="m")


def field(id_: str, expr: str, name: str = "F", type_: str = "str", **kw) -> dict:
    return {
        "id": id_,
        "kind": "field",
        "field": name,
        "type": type_,
        "transform": {"expression": expr},
        **kw,
    }


def loop(rules: list[dict], **kw) -> dict:
    return {
        "id": "lp",
        "kind": "loop",
        "label": "it",
        "source": "$.items[*]",
        "output": "$.Lines[*]",
        "rules": rules,
        **kw,
    }


def tr(rules: list[dict], **opt) -> str:
    return transpile_file_model(model(rules), TranspileOptions(**opt))


# -- golden + end-to-end through the compiler ---------------------------------


def test_fixture_matches_golden_map_py():
    text = transpile_file(FIXTURES / "order_event.fn.yaml")
    assert text == (FIXTURES / "order_event.map.py.golden").read_text()


def test_fixture_output_compiles_to_plsql():
    sql = compile_source(transpile_file(FIXTURES / "order_event.fn.yaml"), "x")
    assert (
        "fn_order_event_lin(p_root IN JSON_OBJECT_T, p_src IN JSON_OBJECT_T, p_index IN NUMBER"
        in sql
    )
    assert 'JSON_OBJECT_T(\'{"IT": "EUR", "US": "USD"}\')' in sql
    assert "ROUND(" in sql


# -- Stage 1: loader ----------------------------------------------------------


def test_loader_rejects_unknown_keys_with_path():
    with pytest.raises(FnYamlError, match=r"rules\[0\]: unknown key\(s\): typo"):
        model([{**field("a", "$.x"), "typo": 1}])


def test_loader_rejects_bad_type_and_manual_without_override():
    with pytest.raises(FnYamlError, match="'type' must be one of"):
        model([field("a", "$.x", type_="float")])
    with pytest.raises(FnYamlError, match="code_override is empty"):
        model([field("a", "$.x", transform={"status": "manual"})])


def test_decay_resets_validation_only_on_functional_change():
    old = model([field("a", "$.x", validation={"validated": True})]).rules[0]
    assert isinstance(old, FieldRule)
    same = model([field("a", "$.x", validation={"validated": True})]).rules[0]
    assert apply_decay(old, same).validation.validated is True  # type: ignore[arg-type]
    changed = model([field("a", "$.y", validation={"validated": True})]).rules[0]
    decayed = apply_decay(old, changed)  # type: ignore[arg-type]
    assert (decayed.validation.validated, decayed.validation.needs_review) == (False, True)
    override_only = model(
        [
            field(
                "a",
                "$.x",
                validation={"validated": True},
                transform={"expression": "$.x", "status": "manual", "code_override": "root.z"},
            )
        ]
    ).rules[0]
    assert apply_decay(old, override_only).validation.validated is True  # type: ignore[arg-type]


# -- ids ----------------------------------------------------------------------


def test_suggested_ids_abbreviate_and_index_on_collision():
    f = model(
        [
            {
                "kind": "field",
                "field": "SubObject",
                "type": "str",
                "transform": {"expression": "$.a"},
            },
            {"kind": "field", "field": "SubTwo", "type": "str", "transform": {"expression": "$.b"}},
            {
                "kind": "loop",
                "source": "$.l[*]",
                "output": "$.List[*]",
                "rules": [field("x", "@.a")],
            },
        ]
    )
    assign_ids(f)
    assert [r.id for r in f.rules] == ["sub", "sub2", "lis"]
    assert suggest_local_id(f.rules[2]) == "lis"
    assert [fq for fq, _ in walk(f.rules)] == ["sub", "sub2", "lis", "lis.x"]


def test_duplicate_explicit_ids_are_an_error():
    f = model([field("a", "$.x", "A"), field("a", "$.y", "B")])
    with pytest.raises(FnYamlError, match="duplicate rule id"):
        assign_ids(f)


# -- Stage 2: anchors ---------------------------------------------------------


def _loops(*labels: str | None) -> AnchorScope:
    """Scope for rules nested len(labels) deep, named as inside a generated function."""
    n = len(labels)
    refs = tuple(
        LoopRef(
            label,
            "src" if n - 1 - i == 0 else f"src{n - 1 - i}",
            "index" if n - 1 - i == 0 else f"index{n - 1 - i}",
        )
        for i, label in enumerate(labels)
    )
    return AnchorScope(loops=refs)


def test_anchor_resolution_and_string_literals_are_untouched():
    scope = _loops("order")
    scope.lookups["cc"] = {"A": "EUR"}
    r = resolve_anchors(
        "@.a + @order.b + @1.c + $.d + @index + lookup(@.k, @cc) + 'x@y $z'", scope, "t"
    )
    assert r.text == (
        "src.a + src.b + src.c + root.d + index + lookup(src.k, {'A': 'EUR'}) + 'x@y $z'"
    )
    assert r.uses_index


def test_anchors_reach_outer_loops_by_position_and_label():
    scope = _loops("order", "line")
    r = resolve_anchors("@.p + @2.d + @order.d + @line.p + @index + @index.2", scope, "t")
    assert r.text == "src.p + src1.d + src1.d + src.p + index + index1"
    assert r.index_offsets == {0, 1}


@pytest.mark.parametrize("expr", ["@3.a", "@index.3", "@nope.a", "@0.a"])
def test_anchor_errors(expr: str):
    with pytest.raises(FnYamlError):
        resolve_anchors(expr, _loops("l1", "l2"), "t")


def test_at_outside_loop_is_an_error():
    with pytest.raises(FnYamlError, match="outside a loop"):
        resolve_anchors("@.a", AnchorScope(), "t")


# -- Stage 3: expression blocks -----------------------------------------------


def test_block_mangles_locals_and_returns_last_expression():
    b = parse_block("base = root.a\nbase * 2", "ord_lin", "t")
    import ast

    assert ast.unparse(ast.Module(b.stmts, [])) == "ord_lin_base = root.a\nreturn ord_lin_base * 2"
    assert b.is_simple


def test_block_control_flow_and_flags():
    b = parse_block("if root.a:\n    return Null\nelse:\n    return", "p", "t")
    assert b.returns_null and b.can_omit and not b.is_simple


def test_block_errors():
    with pytest.raises(FnYamlError, match="needs an 'else'"):
        parse_block("if root.a:\n    return 1", "p", "t")
    with pytest.raises(FnYamlError, match="reserved"):
        parse_block("root = 1\nroot", "p", "t")
    with pytest.raises(FnYamlError, match="unsupported statement"):
        parse_block("for x in root.a:\n    pass\n1", "p", "t")


# -- Stage 4-5: shape of the output -------------------------------------------


def test_top_level_field_uses_return_forms_and_annotation():
    text = tr(
        [
            field(
                "a",
                "if $.s == 'X':\n    return Null\nelse:\n    return $.v",
                type_="str",
                required=False,
            )
        ]
    )
    assert "def a(root: Any) -> str | None | Null:" in text
    assert "out.F = a(root)" in text
    compile_source(text, "m")  # and the compiler accepts it


def test_manual_code_override_is_passed_through_without_anchor_resolution():
    text = tr(
        [
            field(
                "a",
                "$.ignored",
                transform={"status": "manual", "code_override": "coalesce(root.x, 'd')"},
            )
        ]
    )
    assert "return coalesce(root.x, 'd')" in text


def test_loop_with_filter_and_sort():
    text = tr(
        [
            loop(
                [field("i", "@.id", "Id")],
                filter="@.st == 'A'",
                sort={"key": "@.price", "reverse": True},
            )
        ]
    )
    assert "for src in sorted(root.items, key='price', reverse=True):" in text
    assert "if src.st == 'A':" in text
    compile_source(text, "m")


def test_loop_with_sort_index_and_start():
    text = tr(
        [
            loop(
                [field("p", "@index", "Pos", "int"), field("i", "@.id", "Id")],
                sort={"key": "@.price", "reverse": True},
                index_start=1,
            )
        ]
    )
    assert (
        "for index, src in enumerate(sorted(root.items, key='price', reverse=True), start=1):"
        in text
    )
    assert "def lp(root: Any, src: Any, index: int) -> LinesItem:" in text
    compile_source(text, "m")


def test_filter_with_index_filters_before_enumerate():
    text = tr(
        [
            loop(
                [field("p", "@index", "Pos", "int"), field("i", "@.id", "Id")],
                filter="@.st == 'A'",
                sort={"key": "@.price"},
                index_start=1,
            )
        ]
    )
    assert (
        "for index, src in enumerate([src for src in sorted(root.items, key='price') "
        "if src.st == 'A'], start=1):"
    ) in text
    assert "continue" not in text
    compile_source(text, "m")


def test_index_parameter_only_when_referenced():
    text = tr([loop([field("i", "@.id", "Id")])])
    assert "def lp(root: Any, src: Any) -> LinesItem:" in text
    assert "enumerate" not in text


def test_two_loops_over_same_source_are_fused_when_enabled():
    rules = [
        loop([field("a", "@.x", "X")], id="l1", output="$.A[*]"),
        loop([field("b", "@.y", "Y")], id="l2", output="$.B[*]", label="other"),
    ]
    fused = tr(rules)
    assert fused.count("for src in root.items:") == 1
    assert "loop_fusion=on" in fused
    unfused = tr(rules, loop_fusion=False)
    assert unfused.count("for src in root.items:") == 2
    assert "loop_fusion=off" in unfused


def test_format_wraps_with_round_or_trunc():
    r = [field("a", "$.v", "V", "number", format="0.00")]
    assert "return round(root.v, 2)" in tr(r)
    assert "return trunc(root.v, 2)" in tr(r, format_choice="truncate")
    r[0]["choices"] = {"format": "truncate"}
    assert "return trunc(root.v, 2)" in tr(r)
    assert "return round(root.v, 0)" in tr([field("a", "$.v", "V", "number", format="0")])


def _num(fmt=None, multiple=None, **kw):
    extra = {"allowed": {"multipleOf": multiple}} if multiple is not None else {}
    if fmt:
        extra["format"] = fmt
    return [field("a", "$.v", "V", "number", **extra, **kw)]


def test_multiple_of_snaps_with_visible_comment():
    text = tr(_num(multiple=0.05))
    assert "# V: multipleOf 0.05 (choices.multipleOf = round)" in text
    assert "return round(root.v / 0.05, 0) * 0.05" in text
    assert "return trunc(root.v / 0.05, 0) * 0.05" in tr(
        _num(multiple=0.05), multiple_of_choice="truncate"
    )
    rule = _num(multiple=0.05, choices={"multipleOf": "truncate"})
    assert "trunc(root.v / 0.05, 0) * 0.05" in tr(rule)  # rule beats project default


def test_multiple_of_then_format_when_compatible():
    text = tr(_num("0.00", 0.05))
    assert "return round(round(root.v / 0.05, 0) * 0.05, 2)" in text


def test_multiple_of_format_conflict_needs_a_decision():
    with pytest.raises(FnYamlError, match="choices.conflicts.format\\+multipleOf"):
        tr(_num("0.00", 0.001))
    key = "format+multipleOf"
    only = tr(_num("0.00", 0.001, choices={"conflicts": {key: "multipleOf_only"}}))
    assert "return round(root.v / 0.001, 0) * 0.001" in only
    fmt = tr(_num("0.00", 0.001, choices={"conflicts": {key: "format_only"}}))
    assert (
        "return round(root.v, 2)" in fmt
        and "0.001" not in fmt.replace("# ", "")[fmt.index("return") :]
    )
    both = tr(_num("0.00", 0.001, choices={"conflicts": {key: "both"}}))
    assert "round(round(root.v / 0.001, 0) * 0.001, 2)" in both


def test_invalid_choices_rejected():
    with pytest.raises(FnYamlError):
        tr(_num("0.00", choices={"format": "up"}))
    with pytest.raises(FnYamlError):
        tr(_num(choices={"bogus": 1}))
    with pytest.raises(FnYamlError):
        tr(_num(multiple=0))


def test_object_with_guard_omits_via_bare_return():
    text = tr(
        [
            {
                "id": "o",
                "kind": "object",
                "output": "$.Disc",
                "guard": "$.rate != None",
                "rules": [field("r", "$.rate", "Rate", "number")],
            }
        ]
    )
    assert "def o(root: Any) -> Disc | None:" in text
    assert "        return\n" in text
    assert "out.Disc = o(root)" in text
    compile_source(text, "m")


def test_input_schema_types_the_parameters():
    schema = resolve_schema_types(
        {
            "title": "Ev",
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"id": {"type": "string"}}},
                }
            },
        },
        "Ev",
    )
    text = transpile_file_model(model([loop([field("i", "@.id", "Id")])]), input_schema=schema)
    assert "def lp(root: Ev, src: Evitem) -> LinesItem:" in text
    compile_source(text, "m", input_schema=schema)  # the type checker accepts the annotations


# -- nested output --------------------------------------------------------------


def inner_loop(rules: list[dict], **kw) -> dict:
    return {
        "id": "sub",
        "kind": "loop",
        "label": "ln",
        "source": "@.lines[*]",
        "output": "@.Rows[*]",
        "rules": rules,
        **kw,
    }


def obj(rules: list[dict], **kw) -> dict:
    return {"id": "ob", "kind": "object", "output": "@.Tax", "rules": rules, **kw}


def test_nested_loop_builds_a_list_in_the_parent_function():
    text = tr([loop([field("i", "@.id", "Id"), inner_loop([field("l", "@.sku", "Sku")])])])
    assert "def lp_sub(root: Any, src1: Any, src: Any) -> RowsItem:" in text
    assert "def lp(root: Any, src: Any) -> LinesItem:" in text
    assert "lp_sub_list = []" in text
    assert "for lp_sub_src in src.lines:" in text
    assert "lp_sub_list.append(lp_sub(root, src, lp_sub_src))" in text
    assert "Rows=lp_sub_list" in text
    # children before parents: the compiler needs callee-before-caller order
    assert text.index("def lp_sub(") < text.index("def lp(")
    compile_source(text, "m")


def test_inner_fields_reach_the_outer_element_and_both_positions():
    text = tr(
        [
            loop(
                [
                    inner_loop(
                        [
                            field("o", "@2.id", "OrderId"),
                            field("p", "@index", "Pos", "int"),
                            field("q", "@index.2", "OrderPos", "int"),
                        ],
                        sort={"key": "@.sku"},
                    )
                ],
                index_start=1,
            )
        ]
    )
    assert (
        "def lp_sub(root: Any, src1: Any, src: Any, index1: int, index: int) -> RowsItem:" in text
    )
    # the parent needs its own position only because a descendant reads it
    assert "def lp(root: Any, src: Any, index: int) -> LinesItem:" in text
    assert "for lp_sub_index, lp_sub_src in enumerate(sorted(src.lines, key='sku')):" in text
    assert "lp_sub(root, src, lp_sub_src, index, lp_sub_index)" in text
    assert "for index, src in enumerate(root.items, start=1):" in text
    compile_source(text, "m")


def test_nested_loop_filter_sees_the_child_element_and_the_outer_one():
    text = tr(
        [
            loop(
                [
                    inner_loop(
                        [field("l", "@.sku", "Sku")],
                        filter="@.qty > @2.minQty",
                    )
                ]
            )
        ]
    )
    assert "if not lp_sub_src.qty > src.minQty:" in text
    compile_source(text, "m")


def test_nested_loop_with_filter_and_index_filters_before_enumerate():
    text = tr(
        [
            loop(
                [
                    inner_loop(
                        [field("p", "@index", "Pos", "int")], filter="@.qty > 0", index_start=1
                    )
                ]
            )
        ]
    )
    assert (
        "for lp_sub_index, lp_sub_src in enumerate([lp_sub_src for lp_sub_src in src.lines "
        "if lp_sub_src.qty > 0], start=1):"
    ) in text
    compile_source(text, "m")


def test_object_inside_a_loop_is_a_call_and_may_be_omitted_by_its_guard():
    text = tr(
        [
            loop(
                [
                    field("i", "@.id", "Id"),
                    obj([field("r", "@.taxRate", "Rate", "number")], guard="@.taxRate != None"),
                ]
            )
        ]
    )
    assert "def lp_ob(root: Any, src: Any) -> Tax | None:" in text
    assert "Tax=lp_ob(root, src)" in text
    assert "Tax: Tax | None" in text
    compile_source(text, "m")


def test_object_inside_object_and_deep_nesting():
    text = tr(
        [
            {
                "id": "o1",
                "kind": "object",
                "output": "$.Hdr",
                "rules": [
                    field("a", "$.a", "A"),
                    {
                        "id": "o2",
                        "kind": "object",
                        "output": "@.Inner",
                        "rules": [field("b", "$.b", "B")],
                    },
                ],
            }
        ]
    )
    assert "def o1_o2(root: Any) -> Inner:" in text
    assert "Inner=o1_o2(root)" in text
    compile_source(text, "m")


def test_three_level_nesting_compiles():
    text = tr(
        [
            loop(
                [
                    inner_loop(
                        [
                            {
                                "id": "leaf",
                                "kind": "loop",
                                "label": "lf",
                                "source": "@.parts[*]",
                                "output": "@.Parts[*]",
                                "rules": [
                                    field("x", "@.n", "N"),
                                    field("y", "@3.id", "OrderId"),
                                ],
                            }
                        ]
                    )
                ]
            )
        ]
    )
    assert "def lp_sub_leaf(root: Any, src2: Any, src1: Any, src: Any) -> PartsItem:" in text
    assert "OrderId=src2.id" in text
    compile_source(text, "m")


def test_typed_nested_params_follow_the_input_schema():
    schema = resolve_schema_types(
        {
            "title": "Ev",
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "lines": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {"sku": {"type": "string"}},
                                },
                            },
                        },
                    },
                }
            },
        },
        "Ev",
    )
    rules = [loop([field("i", "@.id", "Id"), inner_loop([field("l", "@.sku", "Sku")])])]
    text = transpile_file_model(model(rules), input_schema=schema)
    assert "def lp(root: Ev, src: Evitem) -> LinesItem:" in text or "src: Evitem" in text
    assert "def lp_sub(root: Ev, src1: Evitem, src: Evitemline)" in text
    compile_source(text, "m", input_schema=schema)


# -- limits of what the compiler can express ---------------------------------


@pytest.mark.parametrize(
    "rules, message",
    [
        ([loop([field("a", "@.x")], source="@.sub[*]")], "outside a loop"),
        ([loop([field("a", "@.x")], output="$.A.B[*]")], "one field of the enclosing element"),
        ([loop([field("a", "@2.x")])], "only 1 enclose"),
        ([field("a", "@index")], "outside a loop"),
        (
            [loop([field("a", "if @.x:\n    return 1\nelse:\n    return 2")])],
            "no if/return/Null",
        ),
        ([loop([])], "at least one member"),
        ([loop([field("a", "@.x")], sort={"key": "$.a + 1"})], "sort key"),
        ([loop([field("a", "@.x")], filter="@index > 1")], "filter cannot reference @index"),
        (
            [loop([field("a", "@.x"), field("b", "@.y", "F")])],
            "duplicate output field",
        ),
    ],
)
def test_unsupported_shapes_fail_with_a_clear_error(rules, message):
    with pytest.raises(FnYamlError, match=message):
        tr(rules)


def test_loop_rule_is_dataclass():
    assert isinstance(model([loop([field("a", "@.x")])]).rules[0], LoopRule)


def test_nested_fixture_matches_golden_and_compiles():
    text = transpile_file(FIXTURES / "nested.fn.yaml")
    assert text == (FIXTURES / "nested.map.py.golden").read_text()
    compile_source(text, "nested")
